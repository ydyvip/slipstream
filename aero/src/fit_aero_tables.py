"""Fit aero tables from the normalized database (1D and 2D build-up).

For each JSBSim <axis> (DRAG/SIDE/LIFT/ROLL/PITCH/YAW) we fit a table:

  * 1D (``dim: "1d"``): a coefficient table over the axis's configured
    independent variable (alpha or beta).  Rows are filtered to a *clean
    sweep*: for alpha-based axes the side-slip and all controls must be zero;
    for beta-based axes alpha must be zero.

  * 2D (``dim: "2d"``): a coefficient surface over (row_var, col_var) as
    configured for the axis in jsbsim_properties.yaml —
      DRAG/LIFT/PITCH -> (alpha, delta_e)    SIDE/ROLL/YAW -> (alpha, beta)
    Rows are filtered so every rotational variable *not* on a table axis is
    held at zero.  The grid must be complete (every row x col cell present) or
    the fitter falls back to the 1D path.

Axis -> dims (jsbsim_properties.yaml axes config):
    row_var (outer) defaults to the axis independent_var; col_var (inner) is
    optional — an axis without a configured col_var is always 1D.

Breakpoints are sorted ascending, duplicates collapsed (later rows win), and
NaN breakpoints dropped.  Linear interpolation is applied at generation /
evaluation time — the raw table in aero_tables.json holds the dimensionless
database values exactly as fitted, never extrapolated.

Output: database/aero_tables.json
  {
    "generated": iso-timestamp,
    "source": "aero_normalized.csv",
    "axes": {
      "LIFT": {"coefficient": "CL", "variable": "alpha", "dim": "1d",
               "case_count": 6, "cases": [...],
               "x_deg": [...], "x_rad": [...], "c": [...] },
      "ROLL": {"coefficient": "Cl_roll", "variable": "beta", "dim": "2d",
               "row_var": "alpha", "col_var": "beta",
               "row_x_deg": [...], "row_x_rad": [...],
               "col_y_deg": [...], "col_y_rad": [...],
               "c2d": [[rows x cols]], "status": "ok", ...},
      ...
    },
    "coverage": {...}
  }

The 2D c2d array is row-major: c2d[i][j] = coefficient at
(row_x[i], col_y[j]), matching JSBSim FGTable2's row-outer / column-inner
convention.
"""
from __future__ import annotations

import json
import math
from collections import OrderedDict
from typing import Mapping, Sequence

import numpy as np
from scipy import interpolate

# table variable -> the coefficient dimension this axis is scaled by (# plan §6.4)
from ._clock import generated_utc
from .normalize_coefficients import COEFF_DIMENSION

# every rotational / control variable that can appear in a normalized row;
# a clean table sweep holds all but its table axes at zero.
_ROTATION_VARS = (
    "alpha_deg", "beta_deg",
    "delta_e_deg", "delta_a_deg", "delta_r_deg",
)


def _fixed_for_free(free: Sequence[str]) -> dict[str, float]:
    """All rotational variables except the given free ones, held at zero."""
    return {k: 0.0 for k in _ROTATION_VARS if k not in set(free)}


def _clean_sweep_rows(rows, variable: str, fixed: Mapping[str, float],
                      tol: float = 1e-9):
    """Rows where the given independent var varies freely and every other
    rotational variable is held at its fixed value (default 0)."""
    return _free_rows(rows, [variable], fixed, tol)


def _free_rows(rows, free: Sequence[str], fixed: Mapping[str, float],
               tol: float = 1e-9):
    """Rows where each free variable is present and every other rotational
    variable is held at its fixed value (default 0)."""
    free_set = set(free)
    out = []
    for r in rows:
        if any(r.get(v) is None for v in free_set):
            continue
        ok = True
        for k, want in fixed.items():
            val = r.get(k)
            if val is None:
                ok = False
                break
            if abs(float(val) - want) > tol:
                ok = False
                break
        if ok:
            out.append(r)
    return out


def _fit_1d(sweep, coeff: str, var: str):
    """Collapse a 1D clean sweep into sorted breakpoints + coefficients."""
    pairs: dict[float, float] = {}
    for r in sweep:
        x = float(r[var + "_deg"])
        c = float(r[coeff])
        if math.isnan(x) or math.isnan(c):
            continue
        pairs[round(x, 9)] = c  # later duplicate wins
    xs = sorted(pairs)
    return xs, [pairs[x] for x in xs]


def _fit_2d_grid(rows, coeff: str, row_var: str, col_var: str,
                 tol: float = 1e-9):
    """Build a complete 2D grid of (row_var, col_var) -> coeff.

    Returns the grid dict (row_x_deg/row_x_rad/col_y_deg/col_y_rad/c2d/cases)
    or None when the data cannot form a complete 2D surface: fewer than two
    distinct values on either axis, or any missing grid cell.  Missing cells
    make the fitter fall back to the axis's 1D path.
    """
    rv = row_var + "_deg"
    cv = col_var + "_deg"
    fixed = _fixed_for_free([rv, cv])
    sweep = _free_rows(rows, [rv, cv], fixed, tol)
    if len(sweep) < 2:
        return None
    data: dict[tuple[float, float], float] = {}
    cases: list[str] = []
    for r in sweep:
        x = float(r[rv])
        y = float(r[cv])
        c = float(r[coeff])
        if math.isnan(x) or math.isnan(y) or math.isnan(c):
            continue
        data[(round(x, 9), round(y, 9))] = c
        if r.get("case_id"):
            cases.append(str(r["case_id"]))
    if not data:
        return None
    xs = sorted({k[0] for k in data})
    ys = sorted({k[1] for k in data})
    if len(xs) < 2 or len(ys) < 2:
        return None
    c2d: list[list[float]] = []
    for x in xs:
        row_c = []
        for y in ys:
            val = data.get((x, y))
            if val is None:      # incomplete cell -> not a clean surface
                return None
            row_c.append(val)
        c2d.append(row_c)
    return {
        "case_count": len(sweep),
        "cases": cases,
        "row_x_deg": xs,
        "row_x_rad": [math.radians(x) for x in xs],
        "col_y_deg": ys,
        "col_y_rad": [math.radians(y) for y in ys],
        "c2d": c2d,
    }


def _fit_lateral_controls(rows, coeff: str, row_var: str,
                          tol: float = 1e-9) -> list[dict]:
    """Control-derivative terms for a lateral (alpha x beta) axis.

    Each of aileron (delta_a) and rudder (delta_r) is fitted as a 1D table
    of the coefficient vs the control deflection at the NEUTRAL state
    (alpha=0, beta=0, elevator=0, the other control=0), mirroring how a
    build-up model adds separate aileron/rudder effectiveness tables on top
    of the sideslip surface.  Terms with fewer than 2 usable breakpoints
    (e.g. a matrix that never deflects that control) are omitted.
    """
    controls: list[dict] = []
    for ctrl in ("delta_a_deg", "delta_r_deg"):
        # hold every rotational var except alpha, beta and THIS control at
        # zero, so the term isolates the control's own effectiveness at the
        # neutral state
        fixed = _fixed_for_free(["alpha_deg", "beta_deg", ctrl])
        sweep = _free_rows(rows, [ctrl], fixed, tol)
        if len(sweep) < 2:
            continue
        pairs: dict[float, float] = {}
        for r in sweep:
            x = float(r[ctrl])
            c = float(r[coeff])
            if math.isnan(x) or math.isnan(c):
                continue
            pairs[round(x, 9)] = c
        xs = sorted(pairs)
        if len(xs) < 2:
            continue
        controls.append({
            "dim": "1d",
            "control": ctrl[:-4],      # "delta_a_deg" -> "delta_a"
            "variable": ctrl[:-4],
            "case_count": len(sweep),
            "cases": [r["case_id"] for r in sweep],
            "x_deg": xs,
            "x_rad": [math.radians(x) for x in xs],
            "c": [pairs[x] for x in xs],
            "status": "ok",
        })
    return controls


def build_tables(
    rows: Sequence[Mapping],
    axes_conf: Mapping,      # jsbsim_properties.yaml 'axes'
    table_to_axis: Mapping,  # coefficient -> JSBSim axis
    envelope: Mapping | None = None,
    tol: float = 1e-9,
) -> dict:
    """Fit 1D and 2D tables.  rows = aero_normalized rows (dicts)."""
    # integer/float keys in yaml are loaded as int/float; normalise to str
    var_of_axis = {name: conf["independent_var"] for name, conf in axes_conf.items()}
    coeff_of_axis = {axis: coeff for coeff, axis in table_to_axis.items()}

    axes: "OrderedDict[str, dict]" = OrderedDict()
    for axis_name, conf in axes_conf.items():
        coeff = coeff_of_axis.get(axis_name)
        if coeff is None:
            # no DB coefficient mapped to this axis (e.g. power); skip
            continue
        var = conf["independent_var"]
        row_var = conf.get("row_var", var)
        col_var = conf.get("col_var")

        entry: dict | None = None
        # 2D path: configured col_var + complete grid across both axes.
        if col_var:
            grid = _fit_2d_grid(rows, coeff, row_var, col_var, tol)
            if grid is not None:
                entry = {
                    "coefficient": coeff,
                    "variable": var,
                    "dim": "2d",
                    "row_var": row_var,
                    "col_var": col_var,
                    "dimension": COEFF_DIMENSION[coeff],
                    "status": "ok",
                    **grid,
                }

        # Lateral build-up: aileron/rudder effectiveness as 1D control
        # derivative tables (baseline alpha x beta surface + 1D control terms
        # at the neutral state — the classic JSBSim build-up granularity).
        if entry is not None and entry.get("col_var") == "beta":
            controls = _fit_lateral_controls(rows, coeff, row_var, tol)
            if controls:
                entry["controls"] = controls

        # 1D fallback (and the whole path for non-2D axes) — unchanged shape
        # plus the explicit "dim":"1d" marker.
        if entry is None:
            fixed = _fixed_for_free([var + "_deg"])
            sweep = _clean_sweep_rows(rows, var + "_deg", fixed, tol)
            if len(sweep) < 2:
                axes[axis_name] = {
                    "coefficient": coeff, "variable": var,
                    "dim": "1d",
                    "case_count": 0, "cases": [], "x_deg": [],
                    "x_rad": [], "c": [], "status": "insufficient",
                }
                continue
            xs, cs = _fit_1d(sweep, coeff, var)
            axes[axis_name] = {
                "coefficient": coeff,
                "variable": var,
                "dim": "1d",
                "dimension": COEFF_DIMENSION[coeff],
                "case_count": len(sweep),
                "cases": [r["case_id"] for r in sweep],
                "x_deg": xs,
                "x_rad": [math.radians(x) for x in xs],
                "c": cs,
                "status": "ok" if len(xs) >= 2 else "insufficient",
            }
        else:
            axes[axis_name] = entry

    coverage: "OrderedDict[str, dict]" = OrderedDict()
    for name, a in axes.items():
        coverage[name] = _coverage(name, a, envelope, tol)

    return {
        "generated": generated_utc(),
        "source": "aero_normalized.csv",
        "axes": dict(axes),
        "coverage": dict(coverage),
    }


def _coverage(axis_name: str, table: Mapping, envelope: Mapping | None,
              tol: float = 1e-9) -> dict:
    """Coverage warning block for a 1D or 2D table entry.

    envelope maps axis NAME (LIFT/DRAG/...) to (lo, hi) in the axis's
    independent variable (degrees).  For a 2D table the check runs against
    whichever axis carries that variable — lateral (SIDE/ROLL/YAW) 2D tables
    carry beta on the column axis, longitudinal (LIFT/DRAG/PITCH) 2D tables
    carry alpha on the row axis.
    """
    warn: list[str] = []
    if table.get("dim") == "2d":
        xs = table.get("row_x_deg") or []
        ys = table.get("col_y_deg") or []
        if not xs or not ys:
            return {"warnings": ["no table points"]}
        if envelope:
            bounds = envelope.get(axis_name)
            if bounds is not None:
                vmin, vmax = bounds
                var = table.get("variable")
                if var == table.get("col_var"):
                    lo, hi = ys[0], ys[-1]
                    label = "col"
                else:
                    lo, hi = xs[0], xs[-1]
                    label = "row"
                if vmin is not None and lo > float(vmin) + tol:
                    warn.append(f"low-edge {label} breakpoint {lo} > "
                                f"envelope min {vmin}")
                if vmax is not None and hi < float(vmax) - tol:
                    warn.append(f"high-edge {label} breakpoint {hi} < "
                                f"envelope max {vmax}")
        return {"min": xs[0], "max": xs[-1], "warnings": warn}

    # 1D entries: unchanged coverage behavior
    x_deg: Sequence[float] = table.get("x_deg") or []
    if len(x_deg) < 2:
        return {"warnings": ["no table points"]}
    warn = []
    if envelope:
        bounds = envelope.get(axis_name)
        if bounds is not None:
            vmin, vmax = bounds
            if vmin is not None and x_deg[0] > float(vmin) + tol:
                warn.append(f"low-edge breakpoint {x_deg[0]} > envelope min {vmin}")
            if vmax is not None and x_deg[-1] < float(vmax) - tol:
                warn.append(f"high-edge breakpoint {x_deg[-1]} < envelope max {vmax}")
    return {"min": x_deg[0], "max": x_deg[-1], "warnings": warn}


def evaluate_table(table: Mapping, x_deg: float, method: str = "linear") -> float:
    """Interpolate the 1D fitted table at x_deg (linear, no extrapolation
    beyond the breakpoints — values outside return NaN so over-range use is
    loud)."""
    xs = table["x_rad"] if table.get("x_rad") else table["x_deg"]
    cs = table["c"]
    x = math.radians(x_deg) if table.get("x_rad") else x_deg
    if not xs or len(xs) < 2:
        return math.nan
    interp = interpolate.interp1d(
        np.asarray(xs, dtype=float), np.asarray(cs, dtype=float),
        kind=method, bounds_error=False, fill_value=math.nan)
    return float(interp(x))


def evaluate_table_2d(table: Mapping, row_deg: float, col_deg: float) -> float:
    """Bilinear interpolation of a 2D table at (row, col) in degrees.

    Matches JSBSim FGTable2 semantics: rows sorted by the row variable (outer
    axis, first index of c2d), columns by the column variable (inner axis).
    Values outside the breakpoint hull return NaN (over-range is loud, same
    policy as the 1D path).
    """
    xs = table.get("row_x_rad") or table.get("row_x_deg") or []
    ys = table.get("col_y_rad") or table.get("col_y_deg") or []
    c2d = table.get("c2d") or []
    x = math.radians(row_deg) if table.get("row_x_rad") else row_deg
    y = math.radians(col_deg) if table.get("col_y_rad") else col_deg
    if len(xs) < 2 or len(ys) < 2:
        return math.nan
    if x < xs[0] or x > xs[-1] or y < ys[0] or y > ys[-1]:
        return math.nan
    i1 = 1
    while i1 < len(xs) - 1 and xs[i1] < x:
        i1 += 1
    i0 = i1 - 1
    j1 = 1
    while j1 < len(ys) - 1 and ys[j1] < y:
        j1 += 1
    j0 = j1 - 1
    tx = (x - xs[i0]) / (xs[i1] - xs[i0])
    ty = (y - ys[j0]) / (ys[j1] - ys[j0])
    f00 = c2d[i0][j0]
    f10 = c2d[i1][j0]
    f01 = c2d[i0][j1]
    f11 = c2d[i1][j1]
    top = f00 * (1.0 - tx) + f10 * tx
    bot = f01 * (1.0 - tx) + f11 * tx
    return top * (1.0 - ty) + bot * ty


def write_tables(path, tables: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tables, f, indent=2)


def load_tables(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
