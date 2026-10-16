"""Parse OpenFOAM forces FO output (force.dat / moment.dat) into vectors.

The forces function object writes rows like

  # Time  forces(pressure,viscous) moment(pressure,viscous)
  10.0    (Fpx Fpy Fpz) (Fvx Fvy Fvz) (Mpx Mpy Mpz) (Mvx Mvy Mvz)

where each parenthesised group is a 3-vector.  The exact group count/naming
differs across OpenFOAM versions, so the expected layout comes from
coordinate_mapping.yaml (forces_row_layout) and is validated against the file.
The converged (last finite) row's pressure+viscous vectors are summed to give
total force F (N) and moment M (N·m) about the configured CofR.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import _datio
from ._datio import DatReadError

_VECTOR_RE = re.compile(r"\(([^()]*)\)")


def _vectors(line: str) -> list[tuple[float, float, float]]:
    """Extract all (x y z) vector groups from one data line."""
    out = []
    for m in _VECTOR_RE.finditer(line):
        parts = m.group(1).split()
        if len(parts) != 3:
            continue
        try:
            out.append((float(parts[0]), float(parts[1]), float(parts[2])))
        except ValueError:
            continue
    return out


def parse_forces(
    dat_path: str | Path,
    layout: dict | None = None,
    prefix: str = "",
) -> dict[str, float]:
    """Parse a forces FO .dat (force.dat or moment.dat) and return the last
    finite row as total pressure+viscous components.

    Returns {} when the file is absent or unusable.  Expected layout (from
    coordinate_mapping.yaml forces_row_layout, defaults matching OpenFOAM
    v2306):
      vectors_per_row = 4  -> [Fp, Fv, Mp, Mv]
      indexes {pressure_first_force, viscous_force, pressure_moment,
               viscous_moment}
    With prefix="force" the keys are force_Fx/force_Fy/... and for moments
    moment_Mx/... — the caller uses the same function for both files.
    """
    p = Path(dat_path)
    if not p.exists():
        return {}
    layout = layout or {}
    per_row = int(layout.get("vectors_per_row", 4))
    idx_pf = int(layout.get("pressure_first_force", 0))
    idx_vf = int(layout.get("viscous_force", 1))
    idx_pm = int(layout.get("pressure_moment", 2))
    idx_vm = int(layout.get("viscous_moment", 3))

    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return {}
    if not lines:
        return {}

    want_vecs = max(idx_pf, idx_vf, idx_pm, idx_vm) + 1
    result: dict[str, float] | None = None
    for line in reversed(lines):
        vecs = _vectors(line)
        if len(vecs) < want_vecs:
            continue  # partial trailing line while solver is writing
        # sum pressure + viscous
        fp = vecs[idx_pf]
        fv = vecs[idx_vf]
        mp = vecs[idx_pm]
        mv = vecs[idx_vm]
        result = {
            f"{prefix}Fx": fp[0] + fv[0],
            f"{prefix}Fy": fp[1] + fv[1],
            f"{prefix}Fz": fp[2] + fv[2],
            f"{prefix}Mx": mp[0] + mv[0],
            f"{prefix}My": mp[1] + mv[1],
            f"{prefix}Mz": mp[2] + mv[2],
        }
        break
    return result or {}
