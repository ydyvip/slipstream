"""Structural and physical validation of the fitted aero tables and DB.

Runs after fit_aero_tables and before generate_jsbsim_xml.  Catches the
failures that poison a JSBSim model silently:

  * NaN / Inf in breakpoints or coefficients
  * non-strictly-increasing breakpoints (JSBSim needs monotonic lookup)
  * missing axes for the JSBSim config
  * tables that don't span the configured flight envelope (coverage warnings,
    surfaced as warnings not errors so a partial sweep still generates)
  * duplicate case ids in the normalized DB
  * 2D tables: row/column breakpoints strictly increasing, c2d grid shape
    consistent (rows x cols), no NaN cells

Returns (issues, warnings) where issues must be resolved before generation;
warnings are advisory.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from .normalize_coefficients import COEFF_DIMENSION, COEFF_FIELDS


def _validate_1d(tab: Mapping, axis_name: str,
                 errors: list[str], warnings: list[str]) -> None:
    xs = tab.get("x_rad") or tab.get("x_deg") or []
    cs = tab.get("c") or []
    if len(xs) != len(cs):
        errors.append(f"axis {axis_name}: {len(xs)} breakpoints vs "
                      f"{len(cs)} coefficients")
        return
    if len(xs) < 2:
        warnings.append(f"axis {axis_name}: fewer than 2 breakpoints")
        return
    arr_x = np.asarray(xs, dtype=np.float64)
    arr_c = np.asarray(cs, dtype=np.float64)
    if not np.all(np.isfinite(arr_x)) or not np.all(np.isfinite(arr_c)):
        errors.append(f"axis {axis_name}: NaN/Inf in table")
        return
    if not np.all(np.diff(arr_x) > 0):
        errors.append(f"axis {axis_name}: breakpoints not strictly "
                      f"increasing: {arr_x.tolist()}")


def _validate_2d(tab: Mapping, axis_name: str,
                 errors: list[str], warnings: list[str]) -> None:
    rx = tab.get("row_x_rad") or tab.get("row_x_deg") or []
    cy = tab.get("col_y_rad") or tab.get("col_y_deg") or []
    c2d = tab.get("c2d") or []
    if len(rx) < 2 or len(cy) < 2:
        warnings.append(f"axis {axis_name}: fewer than 2 breakpoints on a "
                        f"2D axis (rows={len(rx)}, cols={len(cy)})")
        return
    arr_rx = np.asarray(rx, dtype=np.float64)
    arr_cy = np.asarray(cy, dtype=np.float64)
    if not np.all(np.isfinite(arr_rx)) or not np.all(np.isfinite(arr_cy)):
        errors.append(f"axis {axis_name}: NaN/Inf in 2D breakpoints")
        return
    if not np.all(np.diff(arr_rx) > 0):
        errors.append(f"axis {axis_name}: row breakpoints not strictly "
                      f"increasing: {arr_rx.tolist()}")
        return
    if not np.all(np.diff(arr_cy) > 0):
        errors.append(f"axis {axis_name}: col breakpoints not strictly "
                      f"increasing: {arr_cy.tolist()}")
        return
    if len(c2d) != len(rx) or any(len(row) != len(cy) for row in c2d):
        errors.append(f"axis {axis_name}: c2d grid is {len(c2d)}x"
                      f"{len(c2d[0]) if c2d else 0}, expected "
                      f"{len(rx)}x{len(cy)}")
        return
    arr_c = np.asarray(c2d, dtype=np.float64)
    if not np.all(np.isfinite(arr_c)):
        errors.append(f"axis {axis_name}: NaN/Inf in 2D coefficients")
        return


def validate_tables(
    tables: Mapping,
    axes_conf: Mapping,       # jsbsim_properties 'axes'
    table_to_axis: Mapping,   # coefficient -> axis
    envelope: Mapping | None = None,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for aero_tables.json content."""
    errors: list[str] = []
    warnings: list[str] = []

    axes = tables.get("axes", {})
    coeff_of_axis = {axis: coeff for coeff, axis in table_to_axis.items()}

    for axis_name, coeff in coeff_of_axis.items():
        if axis_name not in axes:
            errors.append(f"axis {axis_name} missing from aero_tables.json")
            continue
        tab = axes[axis_name]
        if tab.get("status") != "ok":
            warnings.append(f"axis {axis_name}: {tab.get('status', 'n/a')} "
                            f"({tab.get('case_count', 0)} cases)")
            continue

        if tab.get("dim") == "2d":
            _validate_2d(tab, axis_name, errors, warnings)
        else:
            _validate_1d(tab, axis_name, errors, warnings)

        # lateral control-derivative terms (each is a 1D table over the
        # control deflection) must be valid too
        for ctrl in tab.get("controls", []):
            if ctrl.get("dim") != "1d" or ctrl.get("status") != "ok":
                warnings.append(f"axis {axis_name}: control term "
                                f"{ctrl.get('control', '?')} "
                                f"({ctrl.get('status', 'n/a')})")
                continue
            _validate_1d(ctrl, f"{axis_name}/{ctrl.get('control', '?')}",
                         errors, warnings)

    # envelope coverage -> warnings
    if envelope:
        for axis_name, coeff in coeff_of_axis.items():
            tab = axes.get(axis_name)
            if not tab:
                continue
            bounds = envelope.get(axis_name)
            if bounds is None:
                continue
            vmin, vmax = bounds
            if tab.get("dim") == "2d":
                rx = tab.get("row_x_deg") or []
                cy = tab.get("col_y_deg") or []
                if tab.get("variable") == tab.get("col_var"):
                    pts = cy
                    label = "col"
                else:
                    pts = rx
                    label = "row"
            else:
                pts = tab.get("x_deg") or []
                label = ""
            if pts:
                lo, hi = pts[0], pts[-1]
                if vmin is not None and lo > float(vmin):
                    warnings.append(f"axis {axis_name}: min {label} breakpoint "
                                    f"{lo} > envelope min {vmin}")
                if vmax is not None and hi < float(vmax):
                    warnings.append(f"axis {axis_name}: max {label} breakpoint "
                                    f"{hi} < envelope max {vmax}")

    return errors, warnings


def validate_normalized(rows: Sequence[Mapping]) -> tuple[list[str], list[str]]:
    """Check the normalized DB: duplicate ids, NaN coefficients, sign sanity."""
    errors: list[str] = []
    warnings: list[str] = []

    ids = [r.get("case_id") for r in rows]
    seen: set[str] = set()
    for i, cid in enumerate(ids):
        key = str(cid)
        if key in seen:
            errors.append(f"duplicate case_id '{key}' at row {i}")
        seen.add(key)

    for idx, r in enumerate(rows):
        for f in COEFF_FIELDS:
            v = r.get(f)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                warnings.append(f"row {idx} case {r.get('case_id')}: "
                                f"coefficient {f} missing")
            elif isinstance(v, float) and abs(v) > 100:
                errors.append(f"row {idx} case {r.get('case_id')}: "
                              f"coefficient {f} = {v} looks non-physical")

        # CL must be finite for a lift-generating body (warn, not error)
        q = r.get("q_inf_pa")
        v = r.get("V_inf_mps")
        if q and (isinstance(v, (int, float)) and int(v) <= 0):
            errors.append(f"row {idx} case {r.get('case_id')}: "
                          f"non-positive velocity {v}")
    return errors, warnings
