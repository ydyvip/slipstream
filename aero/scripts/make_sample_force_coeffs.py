"""Generate synthetic-but-realistic OpenFOAM post-processing sample data.

Produces, for every case in config/cfd_case_matrix.yaml:

  raw/forceCoeffs/<case_id>/coefficient.dat   forceCoeffs FO output
  raw/forces/<case_id>/force.dat, moment.dat  forces FO output

The data is derived from a smooth analytic model so the aero pipeline can be
exercised end-to-end deterministically (unit tests assert we recover the exact
generating functions).  The generating functions are chosen to be
physically sane:

  CL(alpha) = CL_a * alpha + CL_0                      (thin-airfoil slope)
  CD(alpha) = CD_0 + k * CL^2                          (drag polar)
  Cm(alpha) = Cm_0 + Cm_a * alpha                      (static margin)
  CY(beta)  = CY_b * beta
  Cl(beta)  = Cl_b * beta
  Cn(beta)  = Cn_b * beta

Moments are computed about the case's CofR (moment_ref of the matrix
defaults) so the pipeline's moment-reference shift to the CG is actually
exercised.  Dimensional forces: F = C * q * S_ref (+ moments * ref length).

OpenFOAM forceCoeffs writes a header line '#' with column names; modern
OpenFOAM emits the plain columns (Cd, Cl, ...) as *pressure* contribution and
'(f)' columns (Cd(f), ...) as the full pressure+viscous value.  We emit both so
the split path (total - pressure = viscous) is exercised.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


def load_matrix() -> dict:
    with open(CONFIG / "cfd_case_matrix.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _coefs_for(case_meta: dict, defaults: dict) -> dict[str, float]:
    """Coefficients (about CofR) for one case from the sample analytic model.

    Keys are explicit and collision-free (no aliasing like 'Cl').  The
    coefficient.dat convention used here (modern OpenFOAM forceCoeffs):
      plain columns  = pressure-only contribution
      '(f)' columns  = full pressure+viscous value
    so CD total = Cd(f), CD_pressure = Cd, CD_viscous = Cd(f)-Cd.
    """
    alpha = math.radians(float(case_meta.get("alpha_deg", 0.0)))
    beta = math.radians(float(case_meta.get("beta_deg", 0.0)))
    CL_a, CL_0 = 2.0 * math.pi / 6.0, 0.05          # ~ per rad slope / offset
    CD_0, k = 0.020, 0.045
    Cm_0, Cm_a = -0.010, -0.30                     # stable: dCm/dalpha < 0
    CY_b, Cl_b, Cn_b = 0.15, 0.12, 0.06

    CL = CL_a * alpha + CL_0
    CD = CD_0 + k * CL * CL
    Cm = Cm_0 + Cm_a * alpha
    CY = CY_b * beta
    Cl_roll = Cl_b * beta
    Cn_yaw = Cn_b * beta
    # synthetic split: 10% of CD/CL is viscous (0 => 100% pressure)
    visc_frac = 0.10
    return {
        # plain columns = pressure part
        "Cd": CD * (1.0 - visc_frac),
        "Cl": CL * (1.0 - visc_frac),
        "CmPitch": Cm * (1.0 - visc_frac),
        "Cd(f)": CD, "Cl(f)": CL, "CmPitch(f)": Cm,
        # roll/yaw/side coefficients (no split in this model)
        "CmRoll": Cl_roll, "CmYaw": Cn_yaw, "Cs": CY,
        # model params (used by _force_vectors for dimensional reconstruction)
        "CL": CL, "CD": CD, "CY": CY,
        "Cl_roll": Cl_roll, "Cm": Cm, "Cn_yaw": Cn_yaw,
    }


def _case_dirs(force_coeffs: Path, forces: Path, case_id: str) -> None:
    force_coeffs.joinpath(case_id).mkdir(parents=True, exist_ok=True)
    forces.joinpath(case_id).mkdir(parents=True, exist_ok=True)


def _write_force_coeffs(path: Path, fc: dict[str, float], n_rows: int = 24) -> None:
    """coefficient.dat with a settling transient then the converged value."""
    time_end = 100.0
    header = "# Time     Cd         Cl         CmPitch    CmRoll     CmYaw      Cs         Cd(f)      Cl(f)      CmPitch(f)"
    lines = [header]
    for i in range(n_rows):
        t = time_end * (i / max(1, n_rows - 1))
        # settle: start slightly off, approach the converged value exponentially
        relax = 1.0 - math.exp(-t / time_end * 8.0)
        row = [f"{t:.3f}"]
        for lab in ("Cd", "Cl", "CmPitch", "CmRoll", "CmYaw", "Cs",
                    "Cd(f)", "Cl(f)", "CmPitch(f)"):
            val = fc.get(lab, 0.0)
            row.append(f"{val * relax:.6f}")
        lines.append(" ".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_forces(
    forces_path: Path,
    f_tot: tuple[float, float, float],
    m_tot: tuple[float, float, float],
) -> None:
    """Write one forces FO output (OpenFOAM v2306 layout, a single forces.dat):

        # Time  forces(pressure)  forces(viscous)  moment(pressure)  moment(viscous)
        10.0    (Fpx Fpy Fpz)     (Fvx Fvy Fvz)    (Mpx Mpy Mpz)     (Mvx Mvy Mvz)

    Each row carries 4 vector groups -> parse_forces' expected layout.  We
    split total force into 60% pressure / 40% viscous (synthetic), with a
    settling transient then the converged value (last row).
    """
    n = 24
    lines = ["# Time     forces(pressure)     forces(viscous)     "
             "moment(pressure)     moment(viscous)"]
    # pressure + viscous = total; both are components of the SAME force vector
    # so they share sign (OpenFOAM forces FO convention)
    fp = tuple(0.6 * v for v in f_tot)
    fv = tuple(0.4 * v for v in f_tot)
    mp = tuple(0.6 * v for v in m_tot)
    mv = tuple(0.4 * v for v in m_tot)
    for i in range(n):
        relax = 1.0 - math.exp(-i / 24.0 * 8.0)
        t = 100.0 * i / max(1, n - 1)
        lines.append(
            f"{t:.3f} "
            f"({fp[0]*relax:.6f} {fp[1]*relax:.6f} {fp[2]*relax:.6f}) "
            f"({fv[0]*relax:.6f} {fv[1]*relax:.6f} {fv[2]*relax:.6f}) "
            f"({mp[0]*relax:.6f} {mp[1]*relax:.6f} {mp[2]*relax:.6f}) "
            f"({mv[0]*relax:.6f} {mv[1]*relax:.6f} {mv[2]*relax:.6f})"
        )
    forces_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _force_vectors(fc: dict[str, float], case_meta: dict, defaults: dict,
                   geometry: dict) -> tuple[tuple[float, float, float],
                                            tuple[float, float, float]]:
    """Dimensional F (aero frame) and M about CofR from the coefficient model.

    q = 0.5 rho V^2 ; C_qS = C * q * S_ref ; moments = C * q * S * ref_len.
    Moment reference: CG-to-CofR shift (M_cofr = M_cg - R x F, R = cofr - cg).
    """
    rho = float(case_meta.get("rho_kgm3", defaults["rho_kgm3"]))
    v = float(case_meta.get("V_inf_mps", defaults["V_inf_mps"]))
    q = 0.5 * rho * v * v
    sref = float(case_meta.get("S_ref_m2",
                               defaults.get("reference", {}).get("S_ref_m2", 0.2)))
    bref = float(case_meta.get("b_ref_m",
                               defaults.get("reference", {}).get("b_ref_m", 0.8)))
    cbar = float(case_meta.get("cbar_ref_m",
                               defaults.get("reference", {}).get("cbar_ref_m", 0.25)))
    georef = geometry["reference"]
    cg = geometry.get("center_of_gravity_m", (0.0, 0.0, 0.0))
    cofr = (float(case_meta.get("moment_ref_x_m", georef.get("moment_ref_x_m", 0.0))),
            float(case_meta.get("moment_ref_y_m", georef.get("moment_ref_y_m", 0.0))),
            float(case_meta.get("moment_ref_z_m", georef.get("moment_ref_z_m", 0.0))))

    # aero frame CD/CY/CL are about the *center* (no point dependence).
    # Use the TOTAL coefficients (the '(f)' values) — the same totals the
    # coefficient.dat parser reads, so F and the DB coefficients agree.
    F = (fc["CD"] * q * sref,
         fc["CY"] * q * sref,
         fc["CL"] * q * sref)
    # moments about CG first (coefficient model frame), then shift to CofR
    M_cg = (fc["Cl_roll"] * q * sref * bref,
            fc["Cm"] * q * sref * cbar,
            fc["Cn_yaw"] * q * sref * bref)
    R = (cofr[0] - cg[0], cofr[1] - cg[1], cofr[2] - cg[2])
    cross = (R[1] * F[2] - R[2] * F[1],
             R[2] * F[0] - R[0] * F[2],
             R[0] * F[1] - R[1] * F[0])
    M_cofr = (M_cg[0] - cross[0], M_cg[1] - cross[1], M_cg[2] - cross[2])
    return F, M_cofr


def main() -> None:
    matrix = load_matrix()
    geometry = None
    with open(CONFIG / "aircraft_geometry.yaml", encoding="utf-8") as f:
        geometry = yaml.safe_load(f)

    defaults = dict(matrix.get("conditions", {}))
    defaults["reference"] = matrix.get("reference", {})

    fc_root = ROOT / "raw" / "forceCoeffs"
    f_root = ROOT / "raw" / "forces"
    for case in matrix.get("cases", []):
        meta = dict(defaults.get("reference", {}))
        meta.update(case)
        fc = _coefs_for(case, defaults)
        _case_dirs(fc_root, f_root, case["id"])
        _write_force_coeffs(fc_root / case["id"] / "coefficient.dat", fc)
        F, M = _force_vectors(fc, meta, defaults, geometry)
        _write_forces(f_root / case["id"] / "forces.dat", F, M)
    print(f"wrote sample data for {len(matrix.get('cases', []))} cases -> raw/")


if __name__ == "__main__":
    main()
