"""Unit conversions between SI (database) and Imperial (JSBSim).

JSBSim works in feet / pounds / lbf / lbf·ft. The aero database is SI
(meters, N, N·m). All SI -> Imperial conversion lives here so it is
testable in one place (see tests/test_units.py).
"""
from __future__ import annotations

M_TO_FT = 1.0 / 0.3048
M2_TO_FT2 = M_TO_FT * M_TO_FT
M3_TO_FT3 = M_TO_FT * M_TO_FT * M_TO_FT
N_TO_LBF = 1.0 / 4.4482216152605          # 1 lbf = 4.4482216152605 N
NM_TO_LBFFT = NM_TO_LBF = N_TO_LBF * M_TO_FT  # 1 N·m = 0.737562149... lbf·ft
PA_TO_PSF = 1.0 / 47.880258               # 1 psf = 47.880258 Pa
KGM3_TO_SLUGFT3 = 1.0 / 515.378818        # 1 slug/ft^3 = 515.378818 kg/m^3

SPEED_OF_SOUND_MPS = 340.294              # ISA sea level, m/s

# -- [memory aid for the "don't double multiply" rule] ---------------------
# A JSBSim <axis> function computes  force = CL * qbar_psf * Sw_ft2  (lbf) or
# moment  = Cm * qbar_psf * Sw_ft2 * cbar_ft (lbf·ft). The coefficients stored
# in the aero database are *already* normalized by q_inf * S_ref (and the
# reference length for moments), so the generated function multiplies by
# qbar*Sw exactly once — never twice.  If you later add an extra qbar*Sw
# factor, the simulated forces are off by qbar*Sw and tests/test_units.py's
# round-trip check will fail.


def m_to_ft(v: float) -> float:
    return v * M_TO_FT


def m2_to_ft2(v: float) -> float:
    return v * M2_TO_FT2


def m3_to_ft3(v: float) -> float:
    return v * M3_TO_FT3


def n_to_lbf(v: float) -> float:
    """Convert a force in newtons to pound-force."""
    return v * N_TO_LBF


def n_m_to_lbf_ft(v: float) -> float:
    """Convert a moment in N·m to lbf·ft."""
    return v * NM_TO_LBFFT


def pa_to_psf(v: float) -> float:
    return v * PA_TO_PSF


def kgm3_to_slugft3(v: float) -> float:
    return v * KGM3_TO_SLUGFT3


def ft_to_m(v: float) -> float:
    return v / M_TO_FT


def lbf_to_n(v: float) -> float:
    return v / N_TO_LBF


def lbf_ft_to_n_m(v: float) -> float:
    return v / NM_TO_LBFFT


def q_inf_pa(rho_kgm3: float, v_mps: float) -> float:
    """Freestream dynamic pressure, q_inf = 0.5 rho V^2 (Pa)."""
    return 0.5 * rho_kgm3 * v_mps * v_mps
