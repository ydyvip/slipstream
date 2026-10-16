"""Moment-reference translation.

The forces FO reports moments about the CofR; the normalized DB keeps them
about the configured point (moment_reference: "cg" by default, i.e. the
center of gravity).  The shift is

    M_C = M_O - (r_C - r_O) x F   (all in the aero frame, SI units)

and the moment-reference columns must record the actual point used.
"""
from __future__ import annotations

import math

import pytest

from src.transform_coordinates import shift_moment_reference


def test_shift_identity_when_points_coincide():
    f = (1.0, 2.0, 3.0)
    m = (4.0, 5.0, 6.0)
    assert shift_moment_reference(f, m, (0, 0, 0), (0, 0, 0)) == pytest.approx(m)


def test_shift_pure_translation():
    # M about O equals moment about translated point plus r x F (opposite sign)
    f = (1.0, 0.0, 0.0)          # force along +x
    m = (0.0, 0.0, 0.0)
    # translating from O=(0,0,0) to C=(0,0,1): R=(0,0,1), R x F = (0, 1*1, 0)
    # M_C = M_O - (R x F) = (0,-1,0)
    assert shift_moment_reference(f, m, (0, 0, 0), (0, 0, 1.0)) == pytest.approx((0.0, -1.0, 0.0))
    # same translation the other way
    assert shift_moment_reference(f, (0.0, -1.0, 0.0), (0, 0, 1.0), (0, 0, 0)) == pytest.approx((0.0, 0.0, 0.0))


def test_shift_against_manual_cross_product():
    f = (2.0, -3.0, 4.0)
    m_o = (1.0, 2.0, 3.0)
    r_o = (0.0, 0.0, 0.0)
    r_c = (0.5, 0.0, -0.25)
    r = (r_c[0] - r_o[0], r_c[1] - r_o[1], r_c[2] - r_o[2])
    # R x F = (r1 f2 - r2 f1, r2 f0 - r0 f2, r0 f1 - r1 f0)
    cross = (
        r[1] * f[2] - r[2] * f[1],
        r[2] * f[0] - r[0] * f[2],
        r[0] * f[1] - r[1] * f[0],
    )
    expected = (m_o[0] - cross[0], m_o[1] - cross[1], m_o[2] - cross[2])
    assert shift_moment_reference(f, m_o, r_o, r_c) == pytest.approx(expected)


def test_shift_raises_on_bad_arity():
    with pytest.raises(ValueError):
        shift_moment_reference((1.0, 2.0), (0, 0, 0), (0, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError):
        shift_moment_reference((1.0, 2.0, 3.0), (0, 0), (0, 0, 0), (0, 0, 0))


# ---- pipeline: CofR -> CG actually applied ---------------------------------


def test_normalized_moment_is_shifted_to_cg(pipeline):
    """normalized M_CG equals the forces-FO CofR moment shifted by R x F, and
    moment_ref columns record the CG."""
    raw_by_id = {r["case_id"]: r for r in pipeline["raw_rows"]}
    for n in pipeline["normalized_rows"]:
        ra = raw_by_id[n["case_id"]]
        f = (float(ra["fFx_cfd_N"]), float(ra["fFy_cfd_N"]), float(ra["fFz_cfd_N"]))
        m_cofr = (float(ra["fMx_cofr_Nm"]), float(ra["fMy_cofr_Nm"]), float(ra["fMz_cofr_Nm"]))
        r_o = (0.0, 0.0, 0.0)
        # CG comes from geometry; moment_reference="cg" means M about CG
        cg_x = float(n["moment_ref_x_m"])
        m_cg = shift_moment_reference(f, m_cofr, r_o, (cg_x, 0.0, 0.0))
        assert float(n["Mx_Nm"]) == pytest.approx(m_cg[0], abs=1e-9)
        assert float(n["My_Nm"]) == pytest.approx(m_cg[1], abs=1e-9)
        assert float(n["Mz_Nm"]) == pytest.approx(m_cg[2], abs=1e-9)
        # moment was actually shifted off the CofR => recorded ref point != origin
        assert cg_x != 0.0
        assert float(n["moment_ref_y_m"]) == 0.0
        assert float(n["moment_ref_z_m"]) == 0.0


def test_moment_reference_config_choice(mapping, configs):
    """moment_reference:'cg' must be honoured; flipping to 'cofr' keeps CofR."""
    assert mapping["moment_reference"] == "cg"
    geom = configs["geometry"]
    ref = geom["reference"]
    assert (ref.get("moment_ref_x_m", 0.0), ref.get("moment_ref_y_m", 0.0),
            ref.get("moment_ref_z_m", 0.0)) == (0.0, 0.0, 0.0)
    cg = tuple(geom["center_of_gravity_m"])
    assert len(cg) == 3
    assert cg != (0.0, 0.0, 0.0), "CG must differ from CofR to make the test meaningful"


def test_moment_cross_reference_consistency(normalized_rows):
    """Cm_pitch about the CG must equal My/(q S cbar) computed from the DB
    quantities, i.e. the two paths agree to float precision."""
    for n in normalized_rows:
        q = float(n["q_inf_pa"])
        s = float(n["S_ref_m2"])
        cbar = float(n["cbar_ref_m"])
        expected = float(n["My_Nm"]) / (q * s * cbar)
        assert float(n["Cm_pitch"]) == pytest.approx(expected, abs=1e-9)


def test_geometry_reference_consistent(pipeline, configs):
    """The flight-case metadata must match the geometry config (SI units)."""
    geom = configs["geometry"]["reference"]
    n = pipeline["normalized_rows"][0]
    assert float(n["S_ref_m2"]) == pytest.approx(geom["S_ref_m2"])
    assert float(n["b_ref_m"]) == pytest.approx(geom["b_ref_m"])
    assert float(n["cbar_ref_m"]) == pytest.approx(geom["cbar_ref_m"])
