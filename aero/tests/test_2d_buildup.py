"""2D build-up end-to-end tests: grids, fitting, validation, XML, comparison.

These tests exercise the 2-DIMENSIONAL paths of the aero toolchain without
touching the session pipeline fixture (which stays on the default 10-case 1D
matrix so the original golden tests remain green):

  * grid expansion: config/cfd_case_matrix.yaml ``grids:`` blocks expand into
    deterministic per-case lists (product of the swept axes) with the
    per-case schema defaulting un-swept controls to 0.
  * model_coefficients: the analytic sample physics must reduce EXACTLY to the
    original 1D formulas at zero beta / zero controls.
  * 2D fit: build_tables emits ``dim: "2d"`` surfaces over (alpha, beta) for
    lateral axes and (alpha, delta_e) for longitudinal axes, recovering the
    analytic ground truth; lateral axes also gain 1D control-derivative
    tables (aileron/rudder); 1D fallback when the inner axis spans one value.
  * 2D validation: validate_tables accepts complete 2D grids and rejects
    malformed ones, and validates control terms too.
  * 2D XML: generate_xml emits the build-up as a <sum> of independent
    <table>s inside the single qbar*Sw*len product: the gridded 2D baseline
    (lookup="row" + lookup="column", FGTable2 gridded tableData) plus a 1D
    table per control term.
  * 2D comparison: compare evaluates 2D tables with JSBSim FGTable2 bilinear
    semantics (row-outer, column-inner), limited to in-model DB rows; a
    hand-computed value pins the bilinear.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.cfd_matrix import expand_grids, resolve_cases
from src.compare_jsbsim_cfd import compare
from src.fit_aero_tables import build_tables, evaluate_table, evaluate_table_2d
from src.generate_jsbsim_xml import generate_xml
from src.validate_tables import validate_tables

# make_sample_force_coeffs is on sys.path via tests/conftest.py (SCRIPTS)
from make_sample_force_coeffs import model_coefficients  # noqa: E402

# ---------------------------------------------------------------------------
# analytic ground truth helpers
# ---------------------------------------------------------------------------

LAT_ALPHA = [-4.0, 0.0, 4.0, 8.0, 12.0, 16.0]
LAT_BETA = [-10.0, -5.0, 0.0, 5.0, 10.0]
LON_ALPHA = [-4.0, 0.0, 4.0, 8.0, 12.0, 16.0]
LON_DELTA_E = [-8.0, 0.0, 8.0]
CTRL_DELTA_A = [-10.0, 0.0, 10.0]
CTRL_DELTA_R = [-15.0, 0.0, 15.0]


def _row(cid, a, b, de, da, dr, coeffs: dict) -> dict:
    return {"case_id": cid, "alpha_deg": a, "beta_deg": b,
            "delta_e_deg": de, "delta_a_deg": da, "delta_r_deg": dr,
            "CD": coeffs["CD"], "CY": coeffs["CY"], "CL": coeffs["CL"],
            "Cl_roll": coeffs["Cl_roll"], "Cm_pitch": coeffs["Cm_pitch"],
            "Cn_yaw": coeffs["Cn_yaw"]}


def lateral_rows() -> list[dict]:
    """Complete (alpha x beta) grid at zero controls."""
    rows = []
    for a in LAT_ALPHA:
        for b in LAT_BETA:
            m = model_coefficients(a, b)
            rows.append(_row(f"lat_a{a:+.0f}_b{b:+.0f}", a, b, 0.0, 0.0, 0.0, m))
    return rows


def control_rows() -> list[dict]:
    """Aileron + rudder scans at the neutral state (alpha=beta=0) so the
    lateral build-up gains 1D control-derivative terms."""
    rows = []
    for da in CTRL_DELTA_A:
        m = model_coefficients(0.0, 0.0, delta_a_deg=da)
        rows.append(_row(f"da{da:+.0f}", 0.0, 0.0, 0.0, da, 0.0, m))
    for dr in CTRL_DELTA_R:
        m = model_coefficients(0.0, 0.0, delta_r_deg=dr)
        rows.append(_row(f"dr{dr:+.0f}", 0.0, 0.0, 0.0, 0.0, dr, m))
    return rows


def longitudinal_rows() -> list[dict]:
    """Complete (alpha x delta_e) grid at zero beta / roll / yaw controls."""
    rows = []
    for a in LON_ALPHA:
        for de in LON_DELTA_E:
            m = model_coefficients(a, 0.0, delta_e_deg=de)
            rows.append(_row(f"lon_a{a:+.0f}_de{de:+.0f}", a, 0.0, de, 0.0, 0.0, m))
    return rows


def lateral_axes_conf() -> dict:
    return {
        "SIDE": {"independent_var": "beta", "row_var": "alpha", "col_var": "beta",
                 "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "ROLL": {"independent_var": "beta", "row_var": "alpha", "col_var": "beta",
                 "factors": ["qbar", "Sw", "bw"], "output_units": "lbf-ft"},
        "YAW": {"independent_var": "beta", "row_var": "alpha", "col_var": "beta",
                "factors": ["qbar", "Sw", "bw"], "output_units": "lbf-ft"},
    }


def longitudinal_axes_conf() -> dict:
    return {
        "LIFT": {"independent_var": "alpha", "col_var": "delta_e",
                 "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "DRAG": {"independent_var": "alpha", "col_var": "delta_e",
                 "factors": ["qbar", "Sw"], "output_units": "lbf"},
        "PITCH": {"independent_var": "alpha", "col_var": "delta_e",
                  "factors": ["qbar", "Sw", "cbar"], "output_units": "lbf-ft"},
    }


def all_axes_conf() -> dict:
    return {**lateral_axes_conf(), **longitudinal_axes_conf()}


def table_to_axis() -> dict:
    return {"CL": "LIFT", "CD": "DRAG", "CY": "SIDE",
            "Cm_pitch": "PITCH", "Cn_yaw": "YAW", "Cl_roll": "ROLL"}


def js_config() -> dict:
    return {
        "property_map": {
            "qbar": "aero/qbar-psf", "Sw": "metrics/Sw-sqft",
            "bw": "metrics/bw-ft", "cbar": "metrics/cbarw-ft",
            "alpha": "aero/alpha-rad", "beta": "aero/beta-rad",
            "delta_e": "aero/delta-e-rad", "delta_a": "aero/delta-a-rad",
            "delta_r": "aero/delta-r-rad",
        },
        "axes": all_axes_conf(),
        "table_to_axis": table_to_axis(),
    }


def geometry() -> dict:
    return {"reference": {"S_ref_m2": 0.2, "b_ref_m": 0.8, "cbar_ref_m": 0.25}}


def build_all_2d_tables(with_controls: bool = False) -> dict:
    """Merge the lateral + longitudinal 2D fits into one aero_tables dict.

    with_controls=True adds the neutral-state aileron/rudder scans so the
    lateral axes also carry 1D control-derivative terms.
    """
    lat_rows = lateral_rows() + (control_rows() if with_controls else [])
    lat = build_tables(lat_rows, lateral_axes_conf(), {"CY": "SIDE",
                                                       "Cl_roll": "ROLL",
                                                       "Cn_yaw": "YAW"})
    lon = build_tables(longitudinal_rows(), longitudinal_axes_conf(),
                       {"CL": "LIFT", "CD": "DRAG", "Cm_pitch": "PITCH"})
    return {
        "generated": lat["generated"],
        "source": "aero_normalized.csv",
        "axes": {**lat["axes"], **lon["axes"]},
        "coverage": {**lat["coverage"], **lon["coverage"]},
    }


# ---------------------------------------------------------------------------
# 1. grid expansion
# ---------------------------------------------------------------------------

def test_expand_grids_contract_a_product():
    """The contract-A grid (alpha x beta x delta_e) expands to 6*3*3 = 54."""
    grid = {"name": "alpha-beta-delta-e",
            "alpha_deg": [-4, 0, 4, 8, 12, 16],
            "beta_deg": [0, 5, 10],
            "delta_e_deg": [-8, 0, 8]}
    cases = expand_grids({"grids": [grid]})
    assert len(cases) == 6 * 3 * 3
    # every combination is present exactly once
    combos = {(c["alpha_deg"], c["beta_deg"], c["delta_e_deg"]) for c in cases}
    expected = {(a, b, de)
                for a in (-4, 0, 4, 8, 12, 16)
                for b in (0, 5, 10)
                for de in (-8, 0, 8)}
    assert combos == expected
    # delta_a / delta_r default to 0 on every expanded case
    assert all(c["delta_a_deg"] == 0.0 and c["delta_r_deg"] == 0.0 for c in cases)
    assert all(c["delta_e_deg"] in (-8.0, 0.0, 8.0) for c in cases)


def test_expand_grids_deterministic_ids():
    grid = {"name": "gb", "alpha_deg": [-4, 0, 4], "beta_deg": [0, 5]}
    m = {"grids": [grid]}
    assert expand_grids(m) == expand_grids(m)
    ids = [c["id"] for c in expand_grids(m)]
    assert len(ids) == len(set(ids)), "ids must be unique"
    assert ids[0] == "gb_am04_b00"          # negative -> 'm' prefix
    assert ids[-1] == "gb_a04_b05"


def test_resolve_cases_falls_back_to_explicit():
    m = {"cases": [{"id": "c1", "alpha_deg": 1.0},
                   {"id": "c2", "alpha_deg": 0.0, "beta_deg": 3.0}]}
    cases = resolve_cases(m)
    assert [c["id"] for c in cases] == ["c1", "c2"]
    # per-case schema gains the delta fields, defaulted to 0
    assert cases[0]["delta_e_deg"] == 0.0
    assert cases[0]["delta_a_deg"] == 0.0
    assert cases[1]["delta_r_deg"] == 0.0


def test_resolve_cases_prefers_grids_when_present():
    grid = {"name": "g", "alpha_deg": [0.0, 4.0], "beta_deg": [0.0, 5.0]}
    m = {"cases": [{"id": "x", "alpha_deg": 0.0}], "grids": [grid]}
    cases = resolve_cases(m)
    assert len(cases) == 1 + 2 * 2          # explicit + expanded grids
    assert all(c["alpha_deg"] in (0.0, 4.0) for c in cases[1:])
    assert all("delta_r_deg" in c for c in cases)


# ---------------------------------------------------------------------------
# 2. model_coefficients reduces EXACTLY to 1D at zero beta/controls
# ---------------------------------------------------------------------------

def test_model_coefficients_reduces_to_1d():
    for a in (-4.0, 0.0, 4.0, 8.0, 12.0, 16.0):
        m = model_coefficients(a, 0.0)
        ar = math.radians(a)
        cl = 2.0 * math.pi / 6.0 * ar + 0.05
        assert m["CL"] == pytest.approx(cl, abs=1e-12)
        assert m["CD"] == pytest.approx(0.020 + 0.045 * cl * cl, abs=1e-12)
        assert m["Cm_pitch"] == pytest.approx(-0.010 - 0.30 * ar, abs=1e-12)
        # no beta / no controls -> zero lateral for a clean alpha sweep
        assert m["CY"] == 0.0
        assert m["Cl_roll"] == 0.0
        assert m["Cn_yaw"] == 0.0
    for b in (-10.0, -5.0, 5.0, 10.0):
        m = model_coefficients(0.0, b)
        br = math.radians(b)
        assert m["CY"] == pytest.approx(0.15 * br, abs=1e-12)
        assert m["Cl_roll"] == pytest.approx(0.12 * br, abs=1e-12)
        assert m["Cn_yaw"] == pytest.approx(0.06 * br, abs=1e-12)


def test_model_coefficients_controls_vanish():
    zero = model_coefficients(0.0, 0.0)
    with_ctrl = model_coefficients(8.0, 3.0, delta_e_deg=10.0,
                                   delta_a_deg=10.0, delta_r_deg=10.0)
    assert with_ctrl["CL"] != zero["CL"]
    assert with_ctrl["CY"] != zero["CY"]
    # setting a control to 0 leaves the rest of the model intact
    no_da = model_coefficients(8.0, 3.0, delta_e_deg=10.0,
                               delta_a_deg=0.0, delta_r_deg=10.0)
    same_a = model_coefficients(8.0, 3.0, delta_e_deg=10.0,
                                delta_a_deg=0.0, delta_r_deg=0.0)
    assert no_da["Cl_roll"] != same_a["Cl_roll"]      # aileron matters


# ---------------------------------------------------------------------------
# 3. 2D fit accuracy + control terms + 1D fallback
# ---------------------------------------------------------------------------

def test_fit_lateral_2d_recovers_ground_truth():
    lat = build_tables(lateral_rows(), lateral_axes_conf(),
                       {"CY": "SIDE", "Cl_roll": "ROLL", "Cn_yaw": "YAW"})
    for axis, coeff in (("SIDE", "CY"), ("ROLL", "Cl_roll"), ("YAW", "Cn_yaw")):
        tab = lat["axes"][axis]
        assert tab["dim"] == "2d"
        assert tab["status"] == "ok"
        assert tab["row_var"] == "alpha" and tab["col_var"] == "beta"
        assert tab["row_x_deg"] == LAT_ALPHA
        assert tab["col_y_deg"] == LAT_BETA
        assert "controls" not in tab          # no deflected control rows
        for i, a in enumerate(LAT_ALPHA):
            for j, b in enumerate(LAT_BETA):
                want = model_coefficients(a, b)[coeff]
                assert tab["c2d"][i][j] == pytest.approx(want, abs=1e-12)


def test_fit_longitudinal_2d_recovers_ground_truth():
    lon = build_tables(longitudinal_rows(), longitudinal_axes_conf(),
                       {"CL": "LIFT", "CD": "DRAG", "Cm_pitch": "PITCH"})
    for axis, coeff in (("LIFT", "CL"), ("DRAG", "CD"), ("PITCH", "Cm_pitch")):
        tab = lon["axes"][axis]
        assert tab["dim"] == "2d"
        assert tab["row_var"] == "alpha" and tab["col_var"] == "delta_e"
        assert tab["row_x_deg"] == LON_ALPHA
        assert tab["col_y_deg"] == LON_DELTA_E
        for i, a in enumerate(LON_ALPHA):
            for j, de in enumerate(LON_DELTA_E):
                want = model_coefficients(a, 0.0, delta_e_deg=de)[coeff]
                assert tab["c2d"][i][j] == pytest.approx(want, abs=1e-12)


def test_fit_lateral_controls_recovers_ground_truth():
    """Neutral-state aileron/rudder scans fit 1D control-derivative tables."""
    lat = build_tables(lateral_rows() + control_rows(), lateral_axes_conf(),
                       {"CY": "SIDE", "Cl_roll": "ROLL", "Cn_yaw": "YAW"})
    for axis, coeff in (("SIDE", "CY"), ("ROLL", "Cl_roll"), ("YAW", "Cn_yaw")):
        tab = lat["axes"][axis]
        assert tab["dim"] == "2d"
        names = [c["control"] for c in tab.get("controls", [])]
        assert names == ["delta_a", "delta_r"]
        for c in tab["controls"]:
            assert c["status"] == "ok" and c["dim"] == "1d"
            for x, want in zip(c["x_deg"], c["c"]):
                if c["control"] == "delta_a":
                    truth = model_coefficients(0.0, 0.0, delta_a_deg=x)[coeff]
                else:
                    truth = model_coefficients(0.0, 0.0, delta_r_deg=x)[coeff]
                assert want == pytest.approx(truth, abs=1e-12)


def test_1d_fallback_when_inner_axis_spans_one_value():
    """The default 10-case CH-3 style data only spans a single inner value ->
    every axis stays 1D (and keeps its existing x_deg/c shape)."""
    rows = []
    for a in (-4.0, 0.0, 4.0, 8.0, 12.0, 16.0):
        rows.append({"case_id": f"a{a:+.0f}", "alpha_deg": a, "beta_deg": 0.0,
                     "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                     "CD": 0.02, "CL": 0.05 + 0.03 * a, "Cm_pitch": -0.01 - 0.3 * a,
                     "CY": 0.0, "Cl_roll": 0.0, "Cn_yaw": 0.0})
    for b in (-10.0, -5.0, 0.0, 5.0, 10.0):
        rows.append({"case_id": f"b{b:+.0f}", "alpha_deg": 0.0, "beta_deg": b,
                     "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                     "CD": 0.02, "CL": 0.05, "Cm_pitch": -0.01,
                     "CY": 0.15 * b, "Cl_roll": 0.12 * b, "Cn_yaw": 0.06 * b})
    tabs = build_tables(rows, all_axes_conf(), table_to_axis())
    assert tabs["axes"]["LIFT"]["dim"] == "1d"
    assert tabs["axes"]["SIDE"]["dim"] == "1d"
    assert tabs["axes"]["LIFT"]["x_deg"] == [-4.0, 0.0, 4.0, 8.0, 12.0, 16.0]
    assert tabs["axes"]["SIDE"]["x_deg"] == [-10.0, -5.0, 0.0, 5.0, 10.0]
    # dim marker present on 1D entries without disturbing the old fields
    assert "dim" in tabs["axes"]["LIFT"] and "c" in tabs["axes"]["LIFT"]


# ---------------------------------------------------------------------------
# 4. 2D validation
# ---------------------------------------------------------------------------

def test_validate_accepts_complete_2d_tables():
    tables = build_all_2d_tables(with_controls=True)
    errors, warnings = validate_tables(tables, all_axes_conf(), table_to_axis())
    assert errors == []
    assert warnings == []


def test_validate_rejects_malformed_2d_grid():
    tables = build_all_2d_tables()
    bad = dict(tables["axes"]["SIDE"])
    bad["c2d"] = [[1.0, 2.0], [3.0]]            # wrong shape
    tables["axes"]["SIDE"] = bad
    errors, _ = validate_tables(tables, all_axes_conf(), table_to_axis())
    assert any("c2d grid" in e for e in errors)


def test_validate_rejects_nan_in_2d_surface():
    tables = build_all_2d_tables()
    bad = dict(tables["axes"]["SIDE"])
    bad["c2d"] = [[v if j != 0 else math.nan for j, v in enumerate(row)]
                  for row in bad["c2d"]]
    tables["axes"]["SIDE"] = bad
    errors, _ = validate_tables(tables, all_axes_conf(), table_to_axis())
    assert any("NaN/Inf" in e for e in errors)


# ---------------------------------------------------------------------------
# 5. 2D XML structure (build-up: gridded 2D baseline + control tables SUMMED)
# ---------------------------------------------------------------------------

def _render(tables):
    xml = generate_xml(tables, js_config(), geometry(),
                       template_dir=str(Path(__file__).resolve().parent.parent / "templates"))
    return ET.fromstring(xml), xml


def test_2d_xml_emits_sum_of_tables():
    """A 2D axis emits product -> sum -> gridded 2D baseline <table> with a
    row + column lookup (no controls in this dataset -> exactly one table)."""
    tables = build_all_2d_tables()
    root, _ = _render(tables)
    axes = {a.attrib["name"]: a for a in root if a.tag == "axis"}
    assert set(axes) == set(table_to_axis().values())

    for name, tab in tables["axes"].items():
        assert tab["dim"] == "2d"
        axis = axes[name]
        fn = axis.find("function")
        assert fn is not None
        product = fn.find("product")
        assert product is not None
        # single product scales once: qbar + Sw (+ ref len) then <sum>
        props = [(p.text or "").strip() for p in product.findall("property")]
        assert props.count("aero/qbar-psf") == 1
        assert props.count("metrics/Sw-sqft") == 1
        s = product.find("sum")
        assert s is not None, f"{name}: 2D axis must emit a <sum> of tables"
        tables_xml = s.findall("table")
        assert len(tables_xml) == 1, f"{name}: no controls -> one baseline table"

        base = tables_xml[0]
        ivs = base.findall("independentVar")
        assert len(ivs) == 2
        assert ivs[0].attrib["lookup"] == "row"
        assert ivs[1].attrib["lookup"] == "column"
        row_prop = _prop("aero/", tab["row_var"])
        col_prop = _prop("aero/", tab["col_var"])
        assert (ivs[0].text or "").strip() == row_prop
        assert (ivs[1].text or "").strip() == col_prop


def _prop(ns: str, var: str) -> str:
    names = {"alpha": "alpha", "beta": "beta", "delta_e": "delta-e",
             "delta_a": "delta-a", "delta_r": "delta-r"}
    return f"{ns}{names[var]}-rad"


def test_2d_xml_gridded_table_data_matches_fgtable2_layout():
    """FGTable2 gridded tableData: line 1 = column breakpoints, then one line
    per row (row breakpoint + one value per column), row-major over (row,col)."""
    tables = build_all_2d_tables()
    root, _ = _render(tables)
    axis = next(a for a in root if a.tag == "axis" and a.attrib["name"] == "SIDE")
    base = axis.find("function/product/sum/table")
    assert base is not None
    td = base.find("tableData")
    assert td is not None and td.text
    lines = [ln.strip() for ln in td.text.split("\n") if ln.strip()]
    tab = tables["axes"]["SIDE"]
    col_y = tab["col_y_deg"]
    row_x = tab["row_x_deg"]
    # line 1 = the column breakpoints
    first = [float(x) for x in lines[0].split()]
    assert first == pytest.approx([math.radians(y) for y in col_y], abs=1e-6)
    # remaining lines: row bp + one value per column, matching c2d
    assert len(lines) == len(row_x) + 1
    for i, line in enumerate(lines[1:]):
        vals = [float(x) for x in line.split()]
        assert vals[0] == pytest.approx(math.radians(row_x[i]), abs=1e-6)
        assert len(vals) == 1 + len(col_y)
        for j, v in enumerate(vals[1:]):
            assert v == pytest.approx(tab["c2d"][i][j], abs=1e-6)


def test_2d_xml_emits_control_terms_in_sum():
    """With aileron/rudder scans, each lateral axis's <sum> carries the 2D
    baseline PLUS one 1D row-lookup table per control term; the control
    independentVar points at the aero/<ctrl>-rad property."""
    tables = build_all_2d_tables(with_controls=True)
    root, _ = _render(tables)
    axes = {a.attrib["name"]: a for a in root if a.tag == "axis"}
    for name in ("SIDE", "ROLL", "YAW"):
        tab = tables["axes"][name]
        assert [c["control"] for c in tab.get("controls", [])] == \
            ["delta_a", "delta_r"]
        s = axes[name].find("function/product/sum")
        assert s is not None
        tables_xml = s.findall("table")
        assert len(tables_xml) == 1 + 2
        for k, c in enumerate(tab["controls"]):
            t = tables_xml[k + 1]
            (iv,) = t.findall("independentVar")
            assert iv.attrib["lookup"] == "row"
            assert (iv.text or "").strip() == _prop("aero/", c["control"])


def test_1d_xml_keeps_single_table_form():
    """A pure-1D tables dict renders product->table (no <sum>)."""
    rows = []
    for a in (-4.0, 0.0, 4.0, 8.0, 12.0, 16.0):
        rows.append({"case_id": f"a{a:+.0f}", "alpha_deg": a, "beta_deg": 0.0,
                     "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                     "CD": 0.02, "CL": 0.05 + 0.03 * a, "Cm_pitch": -0.01 - 0.3 * a,
                     "CY": 0.0, "Cl_roll": 0.0, "Cn_yaw": 0.0})
    tabs = build_tables(rows, all_axes_conf(), table_to_axis())
    root, _ = _render(tabs)
    axis = next(a for a in root if a.tag == "axis" and a.attrib["name"] == "LIFT")
    product = axis.find("function/product")
    assert product is not None
    assert product.find("sum") is None
    table = product.find("table")
    assert table is not None
    iv = table.find("independentVar")
    assert iv is not None
    assert iv.attrib["lookup"] == "row"
    assert (iv.text or "").strip() == "aero/alpha-rad"


# ---------------------------------------------------------------------------
# 6. 2D comparison (bilinear == JSBSim FGTable2 row/col semantics)
# ---------------------------------------------------------------------------

def _bilinear_table() -> dict:
    """A planar surface C = 2*alpha_rad + 3*beta_rad — bilinear is exact."""
    def val(a, b):
        return 2.0 * math.radians(a) + 3.0 * math.radians(b)
    A = [-4.0, 0.0, 4.0]
    B = [-10.0, 0.0, 10.0]
    return {
        "coefficient": "CY", "variable": "beta", "dim": "2d",
        "row_var": "alpha", "col_var": "beta", "status": "ok",
        "row_x_deg": A, "row_x_rad": [math.radians(x) for x in A],
        "col_y_deg": B, "col_y_rad": [math.radians(y) for y in B],
        "c2d": [[val(a, b) for b in B] for a in A],
    }


def test_evaluate_table_2d_matches_hand_bilinear():
    """Hand-computed bilinear at (2°, 5°) — the contract-E pinned value."""
    tab = _bilinear_table()
    # breakpoint hull: row 0°..4°, col 0°..10°
    # tx = (2-0)/(4-0) = 0.5 ; ty = (5-0)/(10-0) = 0.5
    # f00=c2d[0][0]=0, f10=c2d[2][0]=2*rad(4), f01=c2d[0][2]=3*rad(10),
    # f11=c2d[2][2]=2*rad(4)+3*rad(10)
    # f(x,0)=0.5*2*rad(4); f(x,10)=0.5*(2*rad(4)+3*rad(10))+0.5*3*rad(10)
    # result = 0.5*f(x,0) + 0.5*f(x,10) = rad(4) + 1.5*rad(10)
    expected = math.radians(4.0) + 1.5 * math.radians(10.0)
    got = evaluate_table_2d(tab, 2.0, 5.0)
    assert got == pytest.approx(expected, abs=1e-12)
    # exact at a grid corner
    assert evaluate_table_2d(tab, -4.0, -10.0) == pytest.approx(
        2.0 * math.radians(-4.0) + 3.0 * math.radians(-10.0), abs=1e-12)
    # outside the hull -> NaN (loud over-range, same policy as 1D)
    assert math.isnan(evaluate_table_2d(tab, 40.0, 0.0))
    assert math.isnan(evaluate_table_2d(tab, 0.0, 40.0))


def test_compare_2d_matches_hand_computed(tmp_path):
    tab = _bilinear_table()
    tables = {"axes": {"SIDE": tab}}
    rows = []
    for a in (-4.0, 0.0, 4.0):
        for b in (-10.0, 0.0, 10.0):
            rows.append({"case_id": f"r{a}_{b}", "alpha_deg": a, "beta_deg": b,
                         "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                         "CY": 2.0 * math.radians(a) + 3.0 * math.radians(b)})
    # off-grid point -> the hand-computed bilinear value above
    rows.append({"case_id": "off", "alpha_deg": 2.0, "beta_deg": 5.0,
                 "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
                 "CY": math.radians(4.0) + 1.5 * math.radians(10.0)})
    axes_conf = {"SIDE": {"independent_var": "beta", "row_var": "alpha",
                          "col_var": "beta", "factors": ["qbar", "Sw"],
                          "output_units": "lbf"}}
    stats = compare(rows, tables, axes_conf, {"CY": "SIDE"},
                    tmp_path / "c.csv", tmp_path / "r.md")
    assert stats["SIDE"]["count"] == 10
    assert stats["SIDE"]["max_abs"] < 1e-12      # planar surface reproduces exactly


def test_compare_2d_ignores_rows_outside_buildup(tmp_path):
    """A row whose non-axis inputs are NOT neutral (e.g. elevator on a lateral
    surface) is outside the build-up and must not be compared."""
    tab = _bilinear_table()
    tables = {"axes": {"SIDE": tab}}
    rows = [{"case_id": "with_elevator", "alpha_deg": 0.0, "beta_deg": 0.0,
             "delta_e_deg": 8.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
             "CY": 0.0},
            {"case_id": "clean", "alpha_deg": 0.0, "beta_deg": 0.0,
             "delta_e_deg": 0.0, "delta_a_deg": 0.0, "delta_r_deg": 0.0,
             "CY": 0.0}]
    axes_conf = {"SIDE": {"independent_var": "beta", "row_var": "alpha",
                          "col_var": "beta", "factors": ["qbar", "Sw"],
                          "output_units": "lbf"}}
    stats = compare(rows, tables, axes_conf, {"CY": "SIDE"},
                    tmp_path / "c.csv", tmp_path / "r.md")
    assert stats["SIDE"]["count"] == 1           # only the clean row compared


def test_compare_lateral_with_controls(tmp_path):
    """Baseline + control derivative tables reproduce the neutral-state
    deflected rows exactly (build-up closed loop for aileron/rudder)."""
    tables = build_all_2d_tables(with_controls=True)
    rows = lateral_rows() + control_rows()
    stats = compare(rows, tables, lateral_axes_conf(),
                    {"CY": "SIDE", "Cl_roll": "ROLL", "Cn_yaw": "YAW"},
                    tmp_path / "c.csv", tmp_path / "r.md")
    assert set(stats) == {"SIDE", "ROLL", "YAW"}
    for s in stats.values():
        assert s["max_abs"] < 1e-9


def test_pipeline_2d_tables_compare_zero_error(tmp_path):
    """The fitted 2D tables reproduce the DB coefficients they were fitted
    from exactly (fit -> compare round trip at every in-model grid point)."""
    tables = build_all_2d_tables()
    rows = lateral_rows() + longitudinal_rows()
    stats = compare(rows, tables, all_axes_conf(), table_to_axis(),
                    tmp_path / "c.csv", tmp_path / "r.md")
    assert set(stats) == set(table_to_axis().values())
    for s in stats.values():
        assert s["max_abs"] < 1e-9
