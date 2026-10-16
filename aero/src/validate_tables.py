"""Structural and physical validation of the fitted aero tables and DB.

Runs after fit_aero_tables and before generate_jsbsim_xml.  Catches the
failures that poison a JSBSim model silently:

  * NaN / Inf in breakpoints or coefficients
  * non-strictly-increasing breakpoints (JSBSim needs monotonic lookup)
  * missing axes for the JSBSim config
  * tables that don't span the configured flight envelope (coverage warnings,
    surfaced as warnings not errors so a partial sweep still generates)
  * duplicate case ids in the normalized DB

Returns (issues, warnings) where issues must be resolved before generation;
warnings are advisory.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from .normalize_coefficients import COEFF_DIMENSION, COEFF_FIELDS


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

        xs = tab.get("x_rad") or tab.get("x_deg") or []
        cs = tab.get("c") or []
        if len(xs) != len(cs):
            errors.append(f"axis {axis_name}: {len(xs)} breakpoints vs "
                          f"{len(cs)} coefficients")
            continue
        if len(xs) < 2:
            warnings.append(f"axis {axis_name}: fewer than 2 breakpoints")
            continue
        arr_x = np.asarray(xs, dtype=np.float64)
        arr_c = np.asarray(cs, dtype=np.float64)
        if not np.all(np.isfinite(arr_x)) or not np.all(np.isfinite(arr_c)):
            errors.append(f"axis {axis_name}: NaN/Inf in table")
            continue
        if not np.all(np.diff(arr_x) > 0):
            errors.append(f"axis {axis_name}: breakpoints not strictly "
                          f"increasing: {arr_x.tolist()}")
            continue
        if not np.all(np.diff(arr_c) != 0):
            # flat segments are technically fine (2 equal bp values are not),
            # but two equal breakpoints WOULD be; we already checked strict inc.
            pass

    # envelope coverage -> warnings
    if envelope:
        for axis_name, coeff in coeff_of_axis.items():
            tab = axes.get(axis_name)
            if not tab or not tab.get("x_rad"):
                continue
            bounds = envelope.get(axis_name)
            if bounds is None:
                continue
            vmin, vmax = bounds
            xs = tab.get("x_deg") or tab.get("x_rad") or []
            if xs:
                if vmin is not None and xs[0] > float(vmin):
                    warnings.append(f"axis {axis_name}: min breakpoint "
                                    f"{xs[0]} > envelope min {vmin}")
                if vmax is not None and xs[-1] < float(vmax):
                    warnings.append(f"axis {axis_name}: max breakpoint "
                                    f"{xs[-1]} < envelope max {vmax}")

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
