"""Unit conversions and the "q·S is multiplied exactly once" invariant.

These tests pin the conventions that keep generated JSBSim functions
dimensionally correct:

  * SI <-> Imperial round trips (feet / lbf / psf / slug-ft^-3).
  * The reference geometry sizing block is consistent with the conversions.
  * Every coefficient is already normalized by q·S (and the reference length
    for moments), so a generated <axis> function multiplies by qbar·Sw exactly
    once — never twice (see the memory aid in src/_units.py).
"""
from __future__ import annotations

import pytest

from src import _units


@pytest.mark.parametrize(
    "si_value,imperial_value,fwd,rev",
    [
        (0.3048, 1.0, _units.m_to_ft, _units.ft_to_m),
        (0.09290304, 1.0, _units.m2_to_ft2, lambda v: v / _units.M2_TO_FT2),
        (4.4482216152605, 1.0, _units.n_to_lbf, _units.lbf_to_n),
        (1.0, _units.NM_TO_LBFFT, _units.n_m_to_lbf_ft, _units.lbf_ft_to_n_m),
        (47.880258, 1.0, _units.pa_to_psf, lambda v: v / _units.PA_TO_PSF),
        (515.378818, 1.0, _units.kgm3_to_slugft3, lambda v: v / _units.KGM3_TO_SLUGFT3),
    ],
)
def test_unit_roundtrip(si_value, imperial_value, fwd, rev):
    assert fwd(si_value) == pytest.approx(imperial_value, rel=1e-9)
    assert rev(imperial_value) == pytest.approx(si_value, rel=1e-9)


def test_q_inf_dynamic_pressure():
    rho, v = 1.225, 15.0
    assert _units.q_inf_pa(rho, v) == pytest.approx(0.5 * rho * v * v)
    assert _units.q_inf_pa(rho, 0.0) == 0.0


def test_reference_geometry_sizing_matches_conversion(configs):
    """aircraft_geometry.yaml's jsbsim block must equal the SI -> ft2/ft
    conversion of the reference quantities (so generate_xml never applies a
    second length conversion)."""
    geom = configs["geometry"]
    ref = geom["reference"]
    jb = geom["jsbsim"]
    assert jb["Sw_sqft"] == pytest.approx(_units.m2_to_ft2(ref["S_ref_m2"]), rel=1e-5)
    assert jb["bw_ft"] == pytest.approx(_units.m_to_ft(ref["b_ref_m"]), rel=1e-5)
    assert jb["cbarw_ft"] == pytest.approx(_units.m_to_ft(ref["cbar_ref_m"]), rel=1e-5)


def test_moment_unit_is_force_times_length_dimensionally():
    """N·m -> lbf·ft is exactly N -> lbf * m -> ft (never an extra factor)."""
    assert _units.NM_TO_LBFFT == pytest.approx(
        _units.N_TO_LBF * _units.M_TO_FT, rel=1e-12)
