"""Expand 2D/3D wind-tunnel test grids into explicit case lists.

The aero toolchain models an alpha x beta x control-deflection test program,
so config/cfd_case_matrix.yaml accepts two ways to declare cases:

  * explicit ``cases:`` — one dict per converged run (the original schema),
  * ``grids:`` — compact product-of-axes definitions that expand into the
    same explicit per-case dicts with deterministic ids.

Each grid is a block like::

    grids:
      - name: alpha-beta-delta-e
        alpha_deg: [-4, 0, 4, 8, 12, 16]
        beta_deg: [0, 5, 10]
        delta_e_deg: [-8, 0, 8]

and expands to one case per combination of the listed axes (the Cartesian
product, iterated in the order the axes are listed).  Dimension lists may be
any of alpha_deg / beta_deg / delta_e_deg / delta_a_deg / delta_r_deg;
control axes not listed in the grid default to 0 deg on every expanded case,
so every case carries the full per-case schema (id + alpha_deg + beta_deg +
delta_e_deg + delta_a_deg + delta_r_deg).

``resolve_cases(matrix)`` is the single entry point used by the sample driver,
the pipeline and the real-CFD driver: explicit ``cases:`` come first, then
every expanded grid.  The default CH-3 10-case matrix (no ``grids:``) is
returned unchanged.
"""
from __future__ import annotations

import itertools
from typing import Mapping, Sequence

# per-case control-deflection fields, each defaulting to 0 deg
CONTROL_FIELDS = ("delta_e_deg", "delta_a_deg", "delta_r_deg")

# all rotational / control axes a grid may sweep, in id order
GRID_AXIS_FIELDS = (
    "alpha_deg", "beta_deg",
    "delta_e_deg", "delta_a_deg", "delta_r_deg",
)

# case_matrix dim -> id letter (single letters for alpha/beta to match the
# CH-3 "ch3_a04_bm10" style; de/da/dr so aileron stays distinct from alpha)
_DIM_LETTER = {
    "alpha_deg": "a",
    "beta_deg": "b",
    "delta_e_deg": "de",
    "delta_a_deg": "da",
    "delta_r_deg": "dr",
}


def _seg(key: str, v: float) -> str:
    """One id segment: letter + zero-padded magnitude, negative marked 'm'
    (4 -> 'a04', -4 -> 'am04', -8 -> 'dem08') — plain folder-name-safe."""
    fv = float(v)
    sign = "m" if fv < 0 else ""
    return f"{_DIM_LETTER[key]}{sign}{abs(fv):02.0f}"


def _case_id(grid_name: str, vals: Mapping[str, float]) -> str:
    """Deterministic case id for one grid point.

    <grid>_<letter><value>_... for the swept axes only, e.g.
    ``alpha-beta-delta-e_am04_b00_dem08``.  Un-swept axes are not part of the
    id; they default to 0 deg on the case dict.
    """
    body = "_".join(_seg(k, vals[k]) for k in GRID_AXIS_FIELDS if k in vals)
    return f"{grid_name}_{body}" if body else grid_name


def expand_grids(matrix: Mapping) -> list[dict]:
    """Expand every ``grids:`` block into explicit per-case dicts.

    Returns a flat list of case dicts (one per combination).  Only list-valued
    keys are swept; non-list keys (``name``, ``note``, ...) are metadata.
    Un-swept control axes default to 0 deg on every expanded case.
    """
    grids = matrix.get("grids") or []
    cases: list[dict] = []
    for g in grids:
        name = str(g.get("name", "grid"))
        axes = {k: [float(x) for x in v]
                for k, v in g.items() if isinstance(v, (list, tuple))}
        keys = [k for k in GRID_AXIS_FIELDS if k in axes] + \
               [k for k in axes if k not in GRID_AXIS_FIELDS]
        if not keys:
            continue
        for combo in itertools.product(*(axes[k] for k in keys)):
            vals = dict(zip(keys, combo))
            case: dict = {"id": _case_id(name, vals)}
            case.update(vals)
            for ctrl in CONTROL_FIELDS:
                if ctrl not in case:
                    case[ctrl] = 0.0
            cases.append(case)
    return cases


def resolve_cases(matrix: Mapping) -> list[dict]:
    """Resolve the runnable case list for a cfd_case_matrix dict.

    Explicit ``cases:`` first, then every expanded grid (when ``grids:`` is
    present).  Every returned case carries the delta_e/delta_a/delta_r keys
    (original case dicts are not mutated).
    """
    cases = [dict(c) for c in matrix.get("cases", [])]
    cases += expand_grids(matrix)
    for c in cases:
        for f in CONTROL_FIELDS:
            c.setdefault(f, 0.0)
    return cases


def grid_axis_names(grid: Mapping) -> Sequence[str]:
    """Names of the swept axes in a grid block (list-valued keys)."""
    return [k for k in grid if isinstance(grid[k], (list, tuple))]
