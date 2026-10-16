"""Parse OpenFOAM forceCoeffs coefficient.dat into DB field values.

The forceCoeffs function object writes a columnar .dat file whose last header
line names the columns.  The exact column set varies by OpenFOAM version and
by the OpenFOAM instance's naming (e.g. Cd vs CD, Cs vs CY, CmPitch vs Cm),
so we resolve them *by name* through coordinate_mapping.yaml's
force_coeffs_columns table instead of hard-coding positions.

Important naming hazard (plan §1): OpenFOAM forceCoeffs' "Cl" is the LIFT
coefficient along the configured liftDir — it maps to the JSBSim LIFT axis,
NOT to the JSBSim body-roll coefficient that is also called "Cl".  We never
reinterpret names; we only use the physical-axis mapping table.
"""
from __future__ import annotations

from pathlib import Path

from . import _datio
from ._datio import DatReadError

# DB fields a coefficient.dat can provide.  The plain (pressure-only) naming
# is OpenFOAM-version-dependent: modern OpenFOAM (>= v1912) writes base
# columns (Cd, Cl, ...) for the *pressure* contribution and "(f)" columns
# (Cd(f), ...) for the full pressure+viscous value.  We map total coefficients
# from the "(f)" column when present and fall back to the plain column when
# not.  Viscous splits are computed (total - pressure) in normalize.
FIELDS = (
    "CD", "CY", "CL",
    "Cl_roll", "Cm_pitch", "Cn_yaw",
    "CD_pressure", "CL_pressure", "Cm_pressure",
)

# Field -> candidate column names (lower-cased, '(' stripped on match).
# Merged with the user's coordinate_mapping.yaml table at load time.
DEFAULT_FIELD_COLUMNS: dict[str, list[str]] = {
    "CD": ["cd(f)", "cd"],
    "CY": ["cy", "cs(f)", "cs"],
    "CL": ["cl(f)", "cl"],
    "Cl_roll": ["cl_roll", "cmroll"],
    "Cm_pitch": ["cm_pitch", "cmpitch(f)", "cmpitch"],
    "Cn_yaw": ["cn_yaw", "cmyaw(f)", "cmyaw"],
    "CD_pressure": ["cd"],
    "CL_pressure": ["cl"],
    "Cm_pressure": ["cmpitch"],
}


def normalize_colname(name: str) -> str:
    """Lower-case a header token, dropping any '(' suffix like '(f)'."""
    return name.lower().replace("(", "")


def resolve_columns(
    header: list[str], field_columns: dict[str, list[str]] | None = None
) -> dict[str, str]:
    """Map each requested DB field to the actual header column token.

    Returns {field: header_token}.  Fields with no matching column are simply
    absent (callers treat missing as 'not available').  A collision (two
    fields resolved to the same column) raises DatReadError.
    """
    table = DEFAULT_FIELD_COLUMNS.copy()
    if field_columns:
        for field, cols in field_columns.items():
            table.setdefault(field, []).extend(cols or [])

    # pressure/viscous split fields may legitimately share a column with their
    # base total field when the file has no '(f)' columns (older OpenFOAM):
    # in that case the split simply cannot be distinguished and is left out.
    SPLITS = {"CD_pressure", "CL_pressure", "Cm_pressure"}

    lowered = {normalize_colname(tok): tok for tok in header}
    resolved: dict[str, str] = {}
    for field, candidates in table.items():
        for cand in candidates:
            key = normalize_colname(cand)
            if key not in lowered:
                continue
            tok = lowered[key]
            if tok in resolved.values() and field in SPLITS:
                break  # already the base field's column -> cannot split
            if tok in resolved.values():
                raise DatReadError(
                    f"column '{tok}' resolved for multiple fields "
                    f"({[k for k, v in resolved.items() if v == tok]})"
                )
            resolved[field] = tok
            break
    return resolved


def parse_force_coeffs(
    dat_path: str | Path,
    field_columns: dict[str, list[str]] | None = None,
) -> dict[str, float]:
    """Parse one coefficient.dat and return the converged (last finite) row
    mapped to DB field names.  Returns {} if the file is absent or contains
    no usable rows.
    """
    p = Path(dat_path)
    if not p.exists():
        return {}
    try:
        header, rows = _datio.read_dat_fields(p)
        cols = _datio.to_array(header, rows)
        raw = _datio.last_converged_row(cols)
    except DatReadError:
        return {}

    resolved = resolve_columns(header, field_columns)
    out: dict[str, float] = {}
    time_val = raw.get("Time")
    if time_val is not None:
        out["Time"] = time_val
    for field, tok in resolved.items():
        val = raw.get(tok)
        if val is not None:
            out[field] = val
    return out
