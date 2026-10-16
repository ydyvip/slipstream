"""Axis / sign-convention tests for the normalized aero database.

The coordinate_mapping.yaml sign block defaults every coefficient to +1,
meaning the aerodynamic sense is the JSBSim-positive direction:

  * alpha > 0  ->  CL > 0 (lift up), CD > 0 (drag aft), and, for a stable
                   airframe, Cm_pitch decreasing with alpha (dCm/dalpha < 0).
  *  beta > 0  ->  CY > 0 (side force right); Cl_roll / Cn_yaw follow the
                   configured sign for the current geometry (CH-3 sample
                   sets +1, so beta>0 -> positive Cl_roll / Cn_yaw).

These relationships hold for any well-behaved body; the tests are run against
the real pipeline DB.  They fail loudly if the sign block is ever changed to
something that contradicts the physical frame.
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from src.normalize_coefficients import _coefficients_from_forces, normalize_case

COEFFS = ("CD", "CY", "CL", "Cl_roll", "Cm_pitch", "Cn_yaw")


def _longitudinal(normalized_rows):
    """rows with zero sideslip (alpha sweep)."""
    return [r for r in normalized_rows if abs(float(r["beta_deg"])) < 1e-9]


def _lateral(normalized_rows):
    """rows with zero alpha but non-zero beta (beta sweep)."""
    return [r for r in normalized_rows
            if abs(float(r["alpha_deg"])) < 1e-9 and abs(float(r["beta_deg"])) >= 1e-9]


def _sort_by(rows, key):
    pairs = sorted((float(r[key]), r) for r in rows)
    return np.asarray([p[0] for p in pairs]), [p[1] for p in pairs]


# ---- physical sense against the real DB ----------------------------------


def test_alphas_cover_sweep(normalized_rows):
    xs, _ = _sort_by(_longitudinal(normalized_rows), "alpha_deg")
    assert len(xs) >= 5
    assert xs[0] < 0 < xs[-1]          # both signed directions present


def test_lift_coefficient_rises_with_alpha(normalized_rows):
    xs, rows = _sort_by(_longitudinal(normalized_rows), "alpha_deg")
    cl = np.asarray([float(r["CL"]) for r in rows])
    assert np.all(np.diff(cl) > 0), "CL must grow with alpha"


def test_drag_coefficient_positive_and_polar(normalized_rows):
    xs, rows = _sort_by(_longitudinal(normalized_rows), "alpha_deg")
    cd = np.asarray([float(r["CD"]) for r in rows])
    assert np.all(cd > 0), "CD must be positive"
    assert np.all(np.diff(cd) >= 0), "CD must not decrease with |alpha|"
    # drag polar: CD = CD_0 + k*CL^2 is symmetric about the zero-lift angle,
    # so the extreme |alpha| sample carries the largest drag.
    assert cd[-1] == pytest.approx(max(cd), rel=1e-9)


def test_static_longitudinal_stability(normalized_rows):
    xs, rows = _sort_by(_longitudinal(normalized_rows), "alpha_deg")
    cm = np.asarray([float(r["Cm_pitch"]) for r in rows])
    assert np.all(np.diff(cm) < 0), "dCm/dalpha must be < 0 for static stability"
    assert cm[-1] < cm[0]


def test_lateral_coefficients_follow_beta_sign(normalized_rows):
    for r in _lateral(normalized_rows):
        b = float(r["beta_deg"])
        assert np.sign(float(r["CY"])) == np.sign(b)
        assert np.sign(float(r["Cl_roll"])) == np.sign(b)
        assert np.sign(float(r["Cn_yaw"])) == np.sign(b)
        assert abs(float(r["CY"])) > 1e-6


def test_zero_beta_gives_zero_lateral(normalized_rows):
    for r in _longitudinal(normalized_rows):
        assert abs(float(r["CY"])) < 1e-9
        assert abs(float(r["Cl_roll"])) < 1e-9
        assert abs(float(r["Cn_yaw"])) < 1e-9


# ---- sign configuration is wired into coefficient derivation --------------


def test_default_signs_are_plus_one(mapping):
    sgn = mapping["sign"]
    for c in COEFFS:
        assert sgn.get(c) == 1, f"{c} default sign must be +1"


def test_sign_flip_inverts_coefficients():
    f = (10.0, -2.0, 3.0)
    m = (0.1, 0.2, -0.05)
    base = _coefficients_from_forces(f, m, q=100.0, sref=0.2, bref=0.8, cbar=0.25,
                                    signs={c: 1 for c in COEFFS})
    flipped = _coefficients_from_forces(f, m, q=100.0, sref=0.2, bref=0.8, cbar=0.25,
                                        signs={c: -1 for c in COEFFS})
    for c in COEFFS:
        assert float(flipped[c]) == pytest.approx(-float(base[c])), c
def test_normalize_case_respects_sign_mapping(mapping, configs):
    geometry = configs["geometry"]
    case = {"id": "sign-test", "alpha_deg": 5.0, "beta_deg": 2.0}
    forces = {"Fx": 1.0, "Fy": 0.5, "Fz": 2.0,
              "Mx": 0.01, "My": 0.04, "Mz": 0.02}
    base = normalize_case(case, geometry, mapping, {}, forces)

    flipped_map = copy.deepcopy(mapping)
    flipped_map["sign"] = {c: -1 for c in COEFFS}
    flipped = normalize_case(case, geometry, flipped_map, {}, forces)

    for c in COEFFS:
        assert float(flipped[c]) == pytest.approx(-float(base[c])), c
