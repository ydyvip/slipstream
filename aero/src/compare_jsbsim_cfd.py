"""Compare JSBSim-evaluated tables against the original CFD points.

The point of the aero database (plan §1, §4.7) is that the JSBSim functions
must *reproduce* the CFD data they were built from.  This module:

  1. loads the normalized DB (aero_normalized.csv) and the fitted tables
     (aero_tables.json),
  2. for every DB row whose independent variable(s) lie inside the fitted
     table's breakpoints, evaluates the JSBSim coefficient at that row:
       - 1D tables: linear interpolation over the axis independent variable;
       - 2D tables: bilinear interpolation over (row_var, col_var) using the
         same row-outer / column-inner semantics as JSBSim's FGTable2,
  3. compares to the DB coefficient and writes
       reports/coefficient_comparison.csv   one row per (case, coefficient):
                                            coeff_cfd, coeff_db, coeff_jsbsim,
                                            abs_err, rel_err
       reports/validation_report.md         summary stats per axis + overall
                                            pass/fail verdict.

This closes the loop the plan calls "生成的 aerodynamics.xml 必须能在
JSBSim 中加载并通过回归" — we can't run JSBSim itself without the package,
so we evaluate the exact tables we emitted and compare at CFD points.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Mapping, Sequence

from . import _units
from .fit_aero_tables import evaluate_table, evaluate_table_2d
from .generate_jsbsim_xml import _fmt

# every rotational / control variable that can appear in a normalized row
_ROTATION_VARS = (
    "alpha_deg", "beta_deg",
    "delta_e_deg", "delta_a_deg", "delta_r_deg",
)


def _table_model_vars(tab: Mapping) -> set[str]:
    """Deg-column names this table models (its lookup axes + control terms)."""
    if tab.get("dim") == "2d":
        axes = {tab.get("row_var"), tab.get("col_var")}
        for c in tab.get("controls", []):
            if c.get("status") == "ok" and c.get("variable"):
                axes.add(c["variable"])
        return {v + "_deg" for v in axes if v}
    var = tab.get("variable")
    return {var + "_deg"} if var else set()


def _in_model(r: Mapping, tab: Mapping, tol: float = 1e-9) -> bool:
    """True when the row is inside the build-up this table represents: every
    rotational variable NOT on a table axis (or control term) is at its
    neutral 0.  A LIFT alpha x delta_e surface models alpha + elevator, so it
    is only compared against rows with beta/aileron/rudder neutral."""
    model = _table_model_vars(tab)
    for v in _ROTATION_VARS:
        if v in model:
            continue
        val = r.get(v)
        if val is None or abs(float(val)) > tol:
            return False
    return True


def _row_inputs(r: Mapping, var: str, tab: Mapping) -> tuple[float, float] | None:
    """(x_deg, y_deg) evaluation inputs for a row vs one axis table.

    1D tables ignore y.  For a 2D table the inputs are the table's own
    row_var / col_var (NOT the axis independent_var — lateral axes sweep
    (alpha, beta) with row_var=alpha while independent_var=beta).  Returns
    None when the row lacks finite inputs.
    """
    if tab.get("dim") == "2d":
        row_var = tab.get("row_var", var)
        col_var = tab.get("col_var")
        x_deg = float(r.get(row_var + "_deg", math.nan))
        y_deg = float(r.get(col_var + "_deg", math.nan)) if col_var else math.nan
        if not (math.isfinite(x_deg) and math.isfinite(y_deg)):
            return None
        return x_deg, y_deg
    x_deg = float(r.get(var + "_deg", math.nan))
    if not math.isfinite(x_deg):
        return None
    return x_deg, math.nan


def _in_hull(x_deg: float, y_deg: float, tab: Mapping) -> bool:
    """True when (x_deg, y_deg) falls inside the table breakpoints (JSBSim
    clamps or errors outside; we never extrapolate)."""
    if tab.get("dim") == "2d":
        xs = tab.get("row_x_deg") or tab.get("row_x_rad") or []
        ys = tab.get("col_y_deg") or tab.get("col_y_rad") or []
        return bool(xs and ys and min(xs) <= x_deg <= max(xs)
                    and min(ys) <= y_deg <= max(ys))
    xs = tab.get("x_deg") or tab.get("x_rad") or []
    return bool(xs and min(xs) <= x_deg <= max(xs))


def _evaluate_table_at(r: Mapping, tab: Mapping, x_deg: float,
                       y_deg: float) -> float:
    """Evaluate this axis's JSBSim build-up at a row: the base surface (1D
    linear or 2D bilinear) summed with every in-range control derivative
    term.  This mirrors the <sum> of <table>s the XML generator emits."""
    val = (evaluate_table_2d(tab, x_deg, y_deg)
           if tab.get("dim") == "2d"
           else evaluate_table(tab, x_deg))
    if not math.isfinite(val):
        return val
    for c in tab.get("controls", []):
        if c.get("status") != "ok" or not c.get("variable"):
            continue
        cval = float(r.get(c["variable"] + "_deg", 0.0))
        if not _in_hull(cval, math.nan, c):
            continue
        term = evaluate_table(c, cval)
        if math.isfinite(term):
            val += term
    return val


def compare(
    rows: Sequence[Mapping],
    tables: Mapping,
    axes_conf: Mapping,
    table_to_axis: Mapping,
    out_csv: str | Path,
    out_md: str | Path,
) -> dict:
    """Evaluate tables at every DB point and write comparison artifacts.

    Returns a summary dict {axis: {count, max_abs, max_rel, rms}}.
    """
    out_csv = Path(out_csv)
    out_md = Path(out_md)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    var_of_axis = {name: conf["independent_var"] for name, conf in axes_conf.items()}
    # map coefficient -> (axis, independent-var)  (table_to_axis: coeff -> axis)
    coeff_info = {coeff: (axis, var_of_axis[axis])
                  for coeff, axis in table_to_axis.items()
                  if axis in var_of_axis}

    results: list[dict] = []
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "alpha_deg", "beta_deg",
                    "delta_e_deg", "delta_a_deg", "delta_r_deg",
                    "coefficient", "axis",
                    "value_cfd", "value_jsbsim", "abs_err", "rel_err"])
        for r in rows:
            for coeff, (axis, var) in coeff_info.items():
                tab = tables["axes"].get(axis)
                if not tab or tab.get("status") != "ok":
                    continue
                # a build-up table is only compared at points it represents:
                # every rotational var not on a table axis must be neutral
                if not _in_model(r, tab):
                    continue
                cfd_v = r.get(coeff, math.nan)
                cfd = math.nan if cfd_v is None else float(cfd_v)
                if not math.isfinite(cfd):
                    continue
                inputs = _row_inputs(r, var, tab)
                if inputs is None:
                    continue
                x_deg, y_deg = inputs
                # only compare inside the fitted range (JSBSim would clamp or
                # error outside; we never extrapolate)
                if not _in_hull(x_deg, y_deg, tab):
                    continue
                jsbsim = _evaluate_table_at(r, tab, x_deg, y_deg)
                if not math.isfinite(jsbsim):
                    continue
                abs_err = jsbsim - cfd
                rel_err = abs_err / cfd if abs(cfd) > 1e-12 else math.nan
                results.append({
                    "case_id": r.get("case_id", ""),
                    "alpha_deg": r.get("alpha_deg", ""),
                    "beta_deg": r.get("beta_deg", ""),
                    "coefficient": coeff, "axis": axis,
                    "value_cfd": cfd, "value_jsbsim": jsbsim,
                    "abs_err": abs_err, "rel_err": rel_err,
                })
                w.writerow([r.get("case_id", ""), f"{_fmt(r.get('alpha_deg', 0.0), 3)}",
                            f"{_fmt(r.get('beta_deg', 0.0), 3)}",
                            f"{_fmt(r.get('delta_e_deg', 0.0), 3)}",
                            f"{_fmt(r.get('delta_a_deg', 0.0), 3)}",
                            f"{_fmt(r.get('delta_r_deg', 0.0), 3)}",
                            coeff, axis,
                            _fmt(cfd, 6), _fmt(jsbsim, 6),
                            _fmt(abs_err, 6), _fmt(rel_err, 6)])

    # per-axis stats
    per_axis: dict[str, dict] = {}
    for row in results:
        a = per_axis.setdefault(row["axis"], {"count": 0, "ae": [], "re": []})
        a["count"] += 1
        a["ae"].append(abs(row["abs_err"]))
        if math.isfinite(row["rel_err"]):
            a["re"].append(abs(row["rel_err"]))

    stats = {}
    for axis, a in per_axis.items():
        stats[axis] = {
            "count": a["count"],
            "max_abs": max(a["ae"]) if a["ae"] else math.nan,
            "rms": math.sqrt(sum(x * x for x in a["ae"]) / len(a["ae"])) if a["ae"] else math.nan,
            "max_rel": max(a["re"]) if a["re"] else math.nan,
        }

    # markdown report
    lines = [
        "# Aero table vs CFD regression report",
        "",
        f"Generated: fitted {len(tables.get('axes', {}))} axes from "
        f"{tables.get('axes', {}).get('DRAG', {}).get('case_count', 0)} sweep cases.",
        "",
        "Every DB point inside a fitted table's breakpoints is evaluated by the",
        "same interpolation the JSBSim function uses (linear for 1D tables,",
        "bilinear over (row, col) for 2D tables), then compared to the DB",
        "coefficient.  Zero error means the JSBSim function reproduces the CFD",
        "point exactly; non-zero error signals a bug in fitting or generation.",
        "",
        "| axis | points | max \\|abs err\\| | RMS | max \\|rel err\\| |",
        "|---|---|---|---|---|",
    ]
    for axis in ("DRAG", "SIDE", "LIFT", "PITCH", "YAW", "ROLL"):
        if axis not in stats:
            continue
        s = stats[axis]
        lines.append(
            f"| {axis} | {s['count']} | {_fmt(s['max_abs'], 5)} | "
            f"{_fmt(s['rms'], 5)} | {_fmt(s['max_rel'], 5)} |"
        )
    worst = max((s["max_abs"] for s in stats.values()), default=0.0)
    verdict = "PASS" if worst < 1e-9 else "REVIEW"
    lines += ["", f"**Verdict: {verdict}** (max abs error = {_fmt(worst, 6)}).",
              "", "See coefficient_comparison.csv for case-level detail."]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats
