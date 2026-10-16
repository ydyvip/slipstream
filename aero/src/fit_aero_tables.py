"""Fit one-dimensional aero tables from the normalized database.

For each JSBSim <axis> (DRAG/SIDE/LIFT/ROLL/PITCH/YAW) we carve a 1D table:

  * table axis = coefficient (CL, CD, CY, Cm_pitch, Cl_roll, Cn_yaw)
  * independent variable = the axis's configured var (alpha or beta)
  * rows are filtered to a *clean sweep*: for alpha-based axes the side-slip
    and all controls must be zero; for beta-based axes alpha must be zero.
    This guarantees each table is a genuine 1D function of its breakpoint var.

Breakpoints are sorted ascending, duplicates collapsed (later rows win), and
NaN breakpoints dropped.  Linear interpolation is applied at generation /
evaluation time (scipy) — the raw table in aero_tables.json holds the
dimensionless database values exactly as fitted, never extrapolated.

Output: database/aero_tables.json
  {
    "generated": iso-timestamp,
    "source": "aero_normalized.csv",
    "axes": {
      "LIFT": {"coefficient": "CL", "variable": "alpha",
               "case_count": 6, "cases": [...],
               "x_deg": [...], "x_rad": [...], "c": [...] },
      ...
    },
    "coverage": {"LIFT": {"min": -4.0, "max": 16.0, "warnings": [...]}, ...}
  }
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


def _clean_sweep_rows(rows, variable: str, fixed: Mapping[str, float],
                      tol: float = 1e-9):
    """Rows where the given independent var varies freely and every other
    rotational variable is held at its fixed value (default 0)."""
    out = []
    for r in rows:
        v = r.get(variable)
        if v is None:
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


def build_tables(
    rows: Sequence[Mapping],
    axes_conf: Mapping,      # jsbsim_properties.yaml 'axes'
    table_to_axis: Mapping,  # coefficient -> JSBSim axis
    envelope: Mapping | None = None,
    tol: float = 1e-9,
) -> dict:
    """Fit 1D tables.  rows = aero_normalized rows (dicts)."""
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
        if var == "alpha":
            fixed = {"beta_deg": 0.0, "delta_e_deg": 0.0,
                     "delta_a_deg": 0.0, "delta_r_deg": 0.0}
        elif var == "beta":
            fixed = {"alpha_deg": 0.0, "delta_e_deg": 0.0,
                     "delta_a_deg": 0.0, "delta_r_deg": 0.0}
        else:
            fixed = {}
        sweep = _clean_sweep_rows(rows, var + "_deg", fixed, tol)
        if len(sweep) < 2:
            axes[axis_name] = {
                "coefficient": coeff, "variable": var,
                "case_count": 0, "cases": [], "x_deg": [],
                "x_rad": [], "c": [], "status": "insufficient",
            }
            continue
        # sort by the independent breakpoint; drop NaN; collapse duplicates
        pairs: dict[float, float] = {}
        for r in sweep:
            x = float(r[var + "_deg"])
            c = float(r[coeff])
            if math.isnan(x) or math.isnan(c):
                continue
            pairs[round(x, 9)] = c  # later duplicate wins
        xs = sorted(pairs)
        cs = [pairs[x] for x in xs]
        axes[axis_name] = {
            "coefficient": coeff,
            "variable": var,
            "dimension": COEFF_DIMENSION[coeff],
            "case_count": len(sweep),
            "cases": [r["case_id"] for r in sweep],
            "x_deg": xs,
            "x_rad": [math.radians(x) for x in xs],
            "c": cs,
            "status": "ok" if len(xs) >= 2 else "insufficient",
        }

    coverage: "OrderedDict[str, dict]" = OrderedDict()
    for name, a in axes.items():
        x_deg: Sequence[float] = a.get("x_deg") or []
        if len(x_deg) < 2:
            coverage[name] = {"warnings": ["no table points"]}
            continue
        warn = []
        if envelope:
            bounds = envelope.get(name)
            if bounds is not None:
                vmin, vmax = bounds
                if vmin is not None and x_deg[0] > float(vmin) + tol:
                    warn.append(f"low-edge breakpoint {x_deg[0]} > envelope min {vmin}")
                if vmax is not None and x_deg[-1] < float(vmax) - tol:
                    warn.append(f"high-edge breakpoint {x_deg[-1]} < envelope max {vmax}")
        coverage[name] = {"min": x_deg[0], "max": x_deg[-1],
                          "warnings": warn}

    return {
        "generated": generated_utc(),
        "source": "aero_normalized.csv",
        "axes": dict(axes),
        "coverage": dict(coverage),
    }


def evaluate_table(table: Mapping, x_deg: float, method: str = "linear") -> float:
    """Interpolate the fitted table at x_deg (linear, no extrapolation beyond
    the breakpoints — values outside return NaN so over-range use is loud)."""
    xs = table["x_rad"] if table.get("x_rad") else table["x_deg"]
    cs = table["c"]
    x = math.radians(x_deg) if table.get("x_rad") else x_deg
    if not xs or len(xs) < 2:
        return math.nan
    interp = interpolate.interp1d(
        np.asarray(xs, dtype=float), np.asarray(cs, dtype=float),
        kind=method, bounds_error=False, fill_value=math.nan)
    return float(interp(x))


def write_tables(path, tables: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tables, f, indent=2)


def load_tables(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
