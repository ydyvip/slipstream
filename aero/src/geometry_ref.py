"""Real CH-3 reference geometry (SI) — single source for the CFD driver.

Kept in src/ so the case-run driver can import it without depending on YAML
parsing of aircraft_geometry.yaml (same numbers, but usable from a plain script
that also imports the backend's foamcase/geometry modules).
"""
from __future__ import annotations

# --- CH-3 reference plane (from assets/ch-3 build_ch3.py) ---
S_REF_M2 = 6.6          # trapezoid wing planform: 8.0*(1.1+0.55)/2
B_REF_M = 8.0
CBAR_REF_M = 0.856       # MAC for taper 0.5
# Backend compute_params reads ref_area_cm2 if set -> forceCoeffs Aref becomes
# the planform area, so the pressure/viscous split in coefficient.dat is
# consistent with the aero DB's planform normalization.
REF_AREA_CM2 = int(round(S_REF_M2 * 10000.0))  # 66000

# --- CH-3 flight conditions (must match cfd_case_matrix.yaml conditions) ---
V_INF_MPS = 15.0
RHO_KGM3 = 1.225
MU_PAS = 1.8e-5
NU_M2S = MU_PAS / RHO_KGM3   # for OpenFOAM transportProperties

# Angle mapping (backend geometry.prepare_stl conventions), VERIFIED against
# real CFD output (aero/database/aero_normalized.csv, alpha/beta sweeps):
#
# CH-3 is built with the NOSE at x=0, tail at x=+4400mm (assets/ch-3/build_ch3.py),
# so after prepare_stl centres the bounding box the nose sits at -X and the
# tail at +X. Trajectory: wind flows along +X (dragDir (1 0 0)), the model
# faces upstream (-X), everything is consistent with the foam template.
#
# prepare_stl applies rotations about X(roll), then Y(pitch), then Z(-yaw) with
# trimesh's right-handed matrices:
#   - Ry(+θ) maps +X -> (cosθ, 0, -sinθ): +X tilts DOWN. The nose is at -X, so
#     pitch_deg > 0 moves the NOSE UP => alpha > 0. Hence pitch_deg = +alpha.
#   - Rz(φ) maps +X -> (cosφ, sinφ, 0). prepare_stl uses φ = -yaw_deg, so a
#     yaw_deg > 0 moves the -X nose toward +Y (starboard). Wind from port hits
#     the exposed left side and pushes the body toward +Y => CY > 0 for
#     beta > 0. Hence yaw_deg = +beta.
#
# (An earlier derivation assumed the nose sat at +X after centering and produced
# pitch_deg = -alpha / yaw_deg = -beta; the first real CFD runs showed the
# CL-vs-alpha slope and CY-vs-beta sign inverted against test_axis_signs, and
# the mapping below fixes that. Sign block in coordinate_mapping.yaml stays +1.)
def pitch_deg(alpha_deg: float) -> float:
    """Backend pitch angle for a given alpha (nose-up positive)."""
    return +float(alpha_deg)


def yaw_deg(beta_deg: float) -> float:
    """Backend yaw angle for a given sideslip (positive = wind from port)."""
    return +float(beta_deg)
