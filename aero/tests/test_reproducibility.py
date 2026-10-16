"""Reproducibility of generated artifacts.

Plan §8 verification requires *same inputs -> same XML*.  The toolchain is
deterministic except for the generation timestamp, which is pinned via the
reproducible-builds convention (SOURCE_DATE_EPOCH).  These tests assert:

  * generated_utc() honours SOURCE_DATE_EPOCH and falls back to wall clock,
  * running the table-fit and XML generation twice with identical inputs and
    a pinned timestamp produces byte-identical outputs (no hidden 'now' or
    ordering nondeterminism).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from src import _clock


def _pin(epoch: str) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc) \
        .isoformat(timespec="seconds")


def test_generated_utc_uses_source_date_epoch():
    with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "1700000000"}, clear=False):
        assert _clock.generated_utc() == _pin("1700000000")


def test_generated_utc_accepts_iso_input():
    with mock.patch.dict(os.environ,
                         {"SOURCE_DATE_EPOCH": "2026-01-01T00:00:00"}, clear=False):
        assert _clock.generated_utc() == "2026-01-01T00:00:00+00:00"


def test_generated_utc_falls_back_to_now():
    with mock.patch.dict(os.environ, {}, clear=False):
        ts = _clock.generated_utc()
        dt = datetime.fromisoformat(ts)
        assert dt.year >= 2020
        assert dt.tzinfo is not None  # explicit UTC


def test_rejects_bad_epoch():
    with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "not-a-date"}, clear=False):
        with pytest.raises(ValueError):
            _clock.generated_utc()


def _sample_rows():
    """A couple of normalized-DB-shaped rows across alpha and beta."""
    rows = []
    for a in (-4.0, 0.0, 4.0, 8.0, 12.0, 16.0):
        rows.append({"case_id": f"a{a:+.0f}", "alpha_deg": a, "beta_deg": 0.0,
                     "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                     "CD": 0.02, "CL": 0.05 + 0.03 * a, "Cm_pitch": -0.01 - 0.3 * a,
                     "CY": 0.0, "Cl_roll": 0.0, "Cn_yaw": 0.0})
    for b in (-10.0, -5.0, 0.0, 5.0, 10.0):
        rows.append({"case_id": f"b{int(b):+03d}", "alpha_deg": 0.0, "beta_deg": b,
                     "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                     "CD": 0.02, "CL": 0.05, "Cm_pitch": -0.01,
                     "CY": 0.15 * b, "Cl_roll": 0.12 * b, "Cn_yaw": 0.06 * b})
    return rows


def _axes_conf():
    return {
        "DRAG": {"independent_var": "alpha", "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "SIDE": {"independent_var": "beta", "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "LIFT": {"independent_var": "alpha", "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "PITCH": {"independent_var": "alpha", "factors": ["qbar", "Sw", "cbar"], "output_units": "lbf-ft"},
        "YAW": {"independent_var": "beta", "factors": ["qbar", "Sw", "bw"], "output_units": "lbf-ft"},
        "ROLL": {"independent_var": "beta", "factors": ["qbar", "Sw", "bw"], "output_units": "lbf-ft"},
    }


def _table_to_axis():
    return {"CL": "LIFT", "CD": "DRAG", "CY": "SIDE",
            "Cm_pitch": "PITCH", "Cn_yaw": "YAW", "Cl_roll": "ROLL"}


def _envelope():
    return {"LIFT": (-1.0, 15.0), "DRAG": (-1.0, 15.0), "PITCH": (-1.0, 15.0),
            "SIDE": (-10.0, 10.0), "YAW": (-10.0, 10.0), "ROLL": (-10.0, 10.0)}


def _geometry():
    return {"reference": {"S_ref_m2": 0.2, "b_ref_m": 0.8, "cbar_ref_m": 0.25}}


def _js_config():
    return {"property_map": {"qbar": "aero/qbar-psf", "Sw": "metrics/Sw-sqft",
                             "bw": "metrics/bw-ft", "cbar": "metrics/cbarw-ft",
                             "alpha": "aero/alpha-rad", "beta": "aero/beta-rad"},
            "axes": _axes_conf(), "table_to_axis": _table_to_axis()}


def test_table_fit_and_xml_reproducible(tmp_path, monkeypatch):
    from src.fit_aero_tables import build_tables
    from src.generate_jsbsim_xml import generate_xml

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

    rows = _sample_rows()
    tables1 = build_tables(rows, _axes_conf(), _table_to_axis(), envelope=_envelope())
    tables2 = build_tables(rows, _axes_conf(), _table_to_axis(), envelope=_envelope())

    assert tables1 == tables2, "identical rows must fit identical tables"
    assert tables1["generated"] == _pin("1700000000")

    template_dir = Path(__file__).resolve().parent.parent / "templates"
    xml1 = generate_xml(tables1, _js_config(), _geometry(),
                        template_dir=str(template_dir))
    xml2 = generate_xml(tables2, _js_config(), _geometry(),
                        template_dir=str(template_dir))
    assert xml1 == xml2, "identical tables must render identical XML"
    # deterministic timestamp rendered into the XML comment
    assert _pin("1700000000") in xml1
