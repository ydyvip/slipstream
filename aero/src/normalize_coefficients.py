"""Standardize parsed CFD rows into the SI aero database.

Two artifacts (plan §5):

  database/aero_raw.csv          one row per case, exactly what the solver
                                 wrote (forceCoeffs fields + raw forces/moments
                                 in the CFD frame), plus case metadata.
  database/aero_normalized.csv   the standardized, flight-condition-independent
                                 database: every force/moment transformed to the
                                 aero frame, moment reference shifted to the CG
                                 (config moment_reference), and the six
                                 non-dimensional coefficients CD/CY/CL/
                                 Cl_roll/Cm_pitch/Cn_yaw plus pressure/viscous
                                 splits.

Authoritative path: when the forces FO output exists we derive coefficients
from the *dimensional* aero-frame forces/moments (about the chosen moment
reference) - this is what the JSBSim functions will reproduce.  The
forceCoeffs columns are kept in the raw DB and, when the forces output is
absent, used as a fallback (marked coefficient_source='forceCoeffs').

Units: SI - N, N·m, m, Pa.  Pressure/viscous splits are only meaningful when
the forceCoeffs columns differentiate them (base column vs "(f)" column in
modern OpenFOAM); otherwise viscous is left NaN and CD_pressure == CD_total.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from . import _units
from .transform_coordinates import shift_moment_reference, transform_vector

# DB coefficient <-> JSBSim <axis> name (plan §6.4)
COEFF_FIELDS = (
    "CD", "CY", "CL", "Cl_roll", "Cm_pitch", "Cn_yaw",
)
# which reference quantity each coefficient is normalized by
COEFF_DIMENSION = {
    "CD": "qS", "CY": "qS", "CL": "qS",
    "Cl_roll": "qSb", "Cm_pitch": "qScbar", "Cn_yaw": "qSb",
}

# Number of expected vector groups in forces FO rows per
# coordinate_mapping.forces_row_layout (kept here for the fallback sanity).
_LAYOUT_DEFAULT = {
    "vectors_per_row": 4,
    "pressure_first_force": 0,
    "viscous_force": 1,
    "pressure_moment": 2,
    "viscous_moment": 3,
}

NORMALIZED_COLUMNS = (
    "case_id", "alpha_deg", "beta_deg",
    "delta_e_deg", "delta_a_deg", "delta_r_deg",
    "V_inf_mps", "rho_kgm3", "mu_Pas", "Mach", "Re", "q_inf_pa",
    "S_ref_m2", "b_ref_m", "cbar_ref_m",
    "moment_ref_x_m", "moment_ref_y_m", "moment_ref_z_m",
    "Fx_N", "Fy_N", "Fz_N", "Mx_Nm", "My_Nm", "Mz_Nm",
    "CD", "CY", "CL", "Cl_roll", "Cm_pitch", "Cn_yaw",
    "CD_pressure", "CL_pressure", "Cm_pressure",
    "CD_viscous", "CL_viscous", "Cm_viscous",
    "coefficient_source", "convergence", "source_file",
)

RAW_COLUMNS = (
    "case_id", "geometry_revision", "foam_version", "solver", "turbulence_model",
    "alpha_deg", "beta_deg", "delta_e_deg", "delta_a_deg", "delta_r_deg",
    "V_inf_mps", "rho_kgm3", "mu_Pas",
    "fc_CD", "fc_CY", "fc_CL", "fc_Cl_roll", "fc_Cm_pitch", "fc_Cn_yaw",
    "fc_CD_pressure", "fc_CL_pressure", "fc_Cm_pressure",
    "fFx_cfd_N", "fFy_cfd_N", "fFz_cfd_N", "fMx_cofr_Nm", "fMy_cofr_Nm", "fMz_cofr_Nm",
    "convergence", "force_coeffs_file", "forces_file",
)


def _f_nan(v: float | None) -> float:
    return float(v) if v is not None and math.isfinite(float(v)) else math.nan


def normalize_case(
    case: Mapping,
    geometry: Mapping,
    mapping: Mapping,
    forcecoeff: Mapping[str, float],
    forces: Mapping[str, float],
) -> dict[str, float | str]:
    """Return one aero_normalized row for a single case.

    case     - one entry of cfd_case_matrix.cases, defaults already merged
               from the matrix's conditions/reference blocks.
    geometry - aircraft_geometry.yaml (reference + CG).
    mapping  - coordinate_mapping.yaml (rotation, signs, moment_reference).
    forcecoeff - parse_force_coeffs() result ({} allowed).
    forces   - dict from forces FO: keys Fx/Fy/Fz/Mx/My/Mz ({} allowed).
    """
    # ---- flight conditions -------------------------------------------------
    v = float(case.get("V_inf_mps", 15.0))
    rho = float(case.get("rho_kgm3", 1.225))
    mu = float(case.get("mu_Pas", 1.8e-5))
    sref = float(case.get("S_ref_m2", geometry["reference"]["S_ref_m2"]))
    bref = float(case.get("b_ref_m", geometry["reference"]["b_ref_m"]))
    cbar = float(case.get("cbar_ref_m", geometry["reference"]["cbar_ref_m"]))
    q = _units.q_inf_pa(rho, v)

    row: dict[str, float | str] = {
        "case_id": case["id"],
        "alpha_deg": _f_nan(case.get("alpha_deg")),
        "beta_deg": _f_nan(case.get("beta_deg", 0.0)),
        "delta_e_deg": _f_nan(case.get("delta_e_deg", 0.0)),
        "delta_a_deg": _f_nan(case.get("delta_a_deg", 0.0)),
        "delta_r_deg": _f_nan(case.get("delta_r_deg", 0.0)),
        "V_inf_mps": v,
        "rho_kgm3": rho,
        "mu_Pas": mu,
        "Mach": _f_nan(v / _units.SPEED_OF_SOUND_MPS),
        "Re": _f_nan(rho * v * cbar / mu),
        "q_inf_pa": q,
        "S_ref_m2": sref,
        "b_ref_m": bref,
        "cbar_ref_m": cbar,
        "convergence": str(case.get("converged", True)).lower(),
        "source_file": case["id"],
    }

    signs = mapping.get("sign", {})
    rotation = mapping.get("rotation", [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    moment_ref = mapping.get("moment_reference", "cg")
    geom_ref = geometry["reference"]
    cg = geometry.get("center_of_gravity_m", (0.0, 0.0, 0.0))

    # forceCoeffs total vs pressure splits
    def _split(total_key: str, pres_key: str) -> tuple[float, float, float]:
        total = forcecoeff.get(total_key)
        pres = forcecoeff.get(pres_key)
        total = _f_nan(total)
        pres = _f_nan(pres)
        hydro = pres if math.isfinite(pres) else total
        visc = total - pres if (math.isfinite(total) and math.isfinite(pres)) else math.nan
        return total, hydro, visc

    cd_t, cd_p, cd_v = _split("CD", "CD_pressure")
    cl_t, cl_p, cl_v = _split("CL", "CL_pressure")
    cm_t, cm_p, cm_v = _split("Cm_pitch", "Cm_pressure")

    # ---- authoritative path: dimensional forces ----------------------------
    has_forces = all(k in forces for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz"))
    if has_forces:
        f_cfd = (forces["Fx"], forces["Fy"], forces["Fz"])
        m_cofr = (forces["Mx"], forces["My"], forces["Mz"])
        cofr = (
            float(case.get("moment_ref_x_m", geom_ref.get("moment_ref_x_m", 0.0))),
            float(case.get("moment_ref_y_m", geom_ref.get("moment_ref_y_m", 0.0))),
            float(case.get("moment_ref_z_m", geom_ref.get("moment_ref_z_m", 0.0))),
        )
        f_aero = transform_vector(rotation, f_cfd)
        if moment_ref == "cg":
            m_ref = shift_moment_reference(f_aero, m_cofr, cofr, cg)
            ref_pt = tuple(float(x) for x in cg)
        else:
            m_ref = m_cofr
            ref_pt = cofr
        row.update(
            Fx_N=f_aero[0], Fy_N=f_aero[1], Fz_N=f_aero[2],
            Mx_Nm=m_ref[0], My_Nm=m_ref[1], Mz_Nm=m_ref[2],
            moment_ref_x_m=ref_pt[0], moment_ref_y_m=ref_pt[1], moment_ref_z_m=ref_pt[2],
        )
        coeff = _coefficients_from_forces(f_aero, m_ref, q, sref, bref, cbar, signs)
        # fall back to forceCoeffs totals when the dimensionless derive to NaN
        for f in COEFF_FIELDS:
            if not math.isfinite(coeff[f]):
                fc = _f_nan(forcecoeff.get(f))
                if math.isfinite(fc):
                    coeff[f] = fc * signs.get(f, 1.0)
        row.update(coeff)
        row["coefficient_source"] = "forces"
        row.update(**{  # pressure/viscous from forceCoeffs where available
            "CD_pressure": cd_p, "CD_viscous": cd_v,
            "CL_pressure": cl_p, "CL_viscous": cl_v,
            "Cm_pressure": cm_p, "Cm_viscous": cm_v,
        })
        # sanity: if the forces-derived total disagrees with forceCoeffs,
        # prefer the dimensional (frame-controlled) value and note it.
        row["CD"] = coeff["CD"]
        row["CL"] = coeff["CL"]
        row["Cm_pitch"] = coeff["Cm_pitch"]
    else:
        # fallback: forceCoeffs columns directly (about the case's CofR).
        coeff = {}
        for i, f in enumerate(COEFF_FIELDS):
            coeff[f] = _f_nan(forcecoeff.get(f)) * signs.get(f, 1.0)
        cofr = (
            float(case.get("moment_ref_x_m", geom_ref.get("moment_ref_x_m", 0.0))),
            float(case.get("moment_ref_y_m", geom_ref.get("moment_ref_y_m", 0.0))),
            float(case.get("moment_ref_z_m", geom_ref.get("moment_ref_z_m", 0.0))),
        )
        row.update(
            Fx_N=math.nan, Fy_N=math.nan, Fz_N=math.nan,
            Mx_Nm=math.nan, My_Nm=math.nan, Mz_Nm=math.nan,
            moment_ref_x_m=cofr[0], moment_ref_y_m=cofr[1], moment_ref_z_m=cofr[2],
        )
        row.update(coeff)
        row["coefficient_source"] = "forceCoeffs"
        row.update(
            CD_pressure=cd_p, CD_viscous=cd_v,
            CL_pressure=cl_p, CL_viscous=cl_v,
            Cm_pressure=cm_p, Cm_viscous=cm_v,
        )
    return row


def _coefficients_from_forces(
    f_aero: Sequence[float],
    m_aero: Sequence[float],
    q: float, sref: float, bref: float, cbar: float,
    signs: Mapping[str, float],
) -> dict[str, float]:
    """Non-dimensional coefficients from aero-frame forces/moments.

        CD  = +Fx/(q·S)      Cl_roll  = +Mx/(q·S·b)
        CY  = +Fy/(q·S)      Cm_pitch = +My/(q·S·cbar)
        CL  = +Fz/(q·S)      Cn_yaw   = +Mz/(q·S·b)
    with each multiplied by the configured sign (default +1; sign absorbed
    identically by the JSBSim function so the axis sense stays consistent).
    """
    denom_f = q * sref
    denom_b = q * sref * bref
    denom_c = q * sref * cbar
    return {
        "CD": signs.get("CD", 1.0) * f_aero[0] / denom_f,
        "CY": signs.get("CY", 1.0) * f_aero[1] / denom_f,
        "CL": signs.get("CL", 1.0) * f_aero[2] / denom_f,
        "Cl_roll": signs.get("Cl_roll", 1.0) * m_aero[0] / denom_b,
        "Cm_pitch": signs.get("Cm_pitch", 1.0) * m_aero[1] / denom_c,
        "Cn_yaw": signs.get("Cn_yaw", 1.0) * m_aero[2] / denom_b,
    }


def to_raw_row(
    case: Mapping,
    forcecoeff: Mapping[str, float],
    forces: Mapping[str, float],
    force_coeffs_file: str = "",
    forces_file: str = "",
) -> dict[str, float | str]:
    """One aero_raw.csv row - the as-solver-written values + metadata."""
    return {
        "case_id": case["id"],
        "geometry_revision": case.get("geometry_revision", "unknown"),
        "foam_version": case.get("foam_version", ""),
        "solver": case.get("solver", ""),
        "turbulence_model": case.get("turbulence_model", ""),
        "alpha_deg": _f_nan(case.get("alpha_deg")),
        "beta_deg": _f_nan(case.get("beta_deg", 0.0)),
        "delta_e_deg": _f_nan(case.get("delta_e_deg", 0.0)),
        "delta_a_deg": _f_nan(case.get("delta_a_deg", 0.0)),
        "delta_r_deg": _f_nan(case.get("delta_r_deg", 0.0)),
        "V_inf_mps": _f_nan(case.get("V_inf_mps", 15.0)),
        "rho_kgm3": _f_nan(case.get("rho_kgm3", 1.225)),
        "mu_Pas": _f_nan(case.get("mu_Pas", 1.8e-5)),
        "fc_CD": _f_nan(forcecoeff.get("CD")),
        "fc_CY": _f_nan(forcecoeff.get("CY")),
        "fc_CL": _f_nan(forcecoeff.get("CL")),
        "fc_Cl_roll": _f_nan(forcecoeff.get("Cl_roll")),
        "fc_Cm_pitch": _f_nan(forcecoeff.get("Cm_pitch")),
        "fc_Cn_yaw": _f_nan(forcecoeff.get("Cn_yaw")),
        "fc_CD_pressure": _f_nan(forcecoeff.get("CD_pressure")),
        "fc_CL_pressure": _f_nan(forcecoeff.get("CL_pressure")),
        "fc_Cm_pressure": _f_nan(forcecoeff.get("Cm_pressure")),
        "fFx_cfd_N": _f_nan(forces.get("Fx")),
        "fFy_cfd_N": _f_nan(forces.get("Fy")),
        "fFz_cfd_N": _f_nan(forces.get("Fz")),
        "fMx_cofr_Nm": _f_nan(forces.get("Mx")),
        "fMy_cofr_Nm": _f_nan(forces.get("My")),
        "fMz_cofr_Nm": _f_nan(forces.get("Mz")),
        "convergence": str(case.get("converged", True)).lower(),
        "force_coeffs_file": force_coeffs_file,
        "forces_file": forces_file,
    }


def write_csv(path, columns, rows) -> None:
    """Tiny stdlib CSV writer keeping floats as short as possible."""
    import csv

    headers = list(columns)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow([row.get(h, "") for h in headers])


def read_csv(path) -> list[dict[str, str]]:
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def np_col(rows, key: str) -> np.ndarray:
    """Column of numeric rows as a float array (non-numeric -> NaN)."""
    out = []
    for r in rows:
        try:
            out.append(float(r.get(key)))
        except (TypeError, ValueError):
            out.append(math.nan)
    return np.asarray(out, dtype=np.float64)
