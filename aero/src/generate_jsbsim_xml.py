"""Generate JSBSim <aerodynamics> XML from the fitted aero tables.

Key contract — the "no double multiply" rule (plan §6.5, tested in
tests/test_units.py):

  Each <axis> function computes a *force/moment* directly:
      force  = CL_table(alpha) * qbar_psf * Sw_sqft          [lbf]
      moment = Cm_table(alpha) * qbar_psf * Sw_sqft * cbar_ft [lbf·ft]

  The coefficients in the database are already normalized by q_inf·S_ref
  (and the reference length for moments), so the function multiplies by
  qbar·Sw exactly ONCE — never twice.  Moment tables use the extra reference
  length (bw for ROLL/YAW, cbarw for PITCH) as configured in
  jsbsim_properties.yaml.

Table emission:

  * 1D axes (``dim: "1d"``) emit the original single-table form:
        <product> qbar Sw [len] <table lookup="row">…</table> </product>
    byte-identical to the pre-2D toolchain output.

  * 2D build-up axes (``dim: "2d"``) emit a single JSBSim FGTable2 gridded
    table over the row/column variables (the fitted surface itself), inside a
    <sum> so one or more 1D control-derivative tables (lookup="row") can be
    appended without a second multiply by qbar*Sw*len):
        <product> qbar Sw [len]
          <sum>
            <table lookup="row" + lookup="column">surface(row, col)</table>
            [<table lookup="row">control derivative …</table> …]
          </sum>
        </product>
    tableData uses the FGTable2 gridded layout — line 1 = column breakpoints
    (inner independent var), then one line per row: the row breakpoint (outer
    var) followed by one value per column.  This is the whole fitted build-up
    surface (it already carries any row*col coupling and control deflection
    dependence), so no base/increment split is needed here.

  SI -> Imperial conversion: forces N->lbf, lengths m->ft, qbar Pa->psf,
  density handled by JSBSim itself (we pass no qbar value of our own).  The
  tables' independent variable is radians (JSBSim <independentVar>alpha-rad).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import _units
from ._clock import generated_utc
from .normalize_coefficients import COEFF_FIELDS

# how an aero coefficient maps onto a JSBSim axis property suffix (body frame)
AXIS_OUTPUT = {
    "DRAG": "along drag (aft)",
    "SIDE": "yaw (right)",
    "LIFT": "lift (up)",
    "ROLL": "roll moment (right-wing-down)",
    "PITCH": "pitch moment (nose-up)",
    "YAW": "yaw moment (nose-right)",
}

# coefficient full names for the description text
COEFF_LONG = {
    "CD": "drag", "CY": "sideforce", "CL": "lift",
    "Cl_roll": "roll", "Cm_pitch": "pitch", "Cn_yaw": "yaw",
}


def _fmt(x: float, nd: int = 6) -> str:
    if x != x:  # NaN
        return "NaN"
    return f"{x:.{nd}f}"


def _table_rows_1d(x_rad, c) -> str:
    """JSBSim 1D row-lookup rows: 'x y' one line each (see module docstring
    for why the rows are built here rather than in the template)."""
    return "\n".join(f"{_fmt(v)}  {_fmt(w)}" for v, w in zip(x_rad, c))


def _table_data_2d(row_rad, col_rad, c2d, nd: int = 6) -> str:
    """JSBSim 2D gridded tableData.

    FGTable2 layout: line 1 = the column breakpoints (inner independent var,
    radians — the table columns are *rad properties), then one line per row:
    row breakpoint (outer, radians) + one value per column.  Every row is a
    physical line (JSBSim tokenizes per line).
    """
    f0 = lambda v: _fmt(v, nd)  # noqa: E731
    lines = [" ".join(f0(c) for c in col_rad)]
    for x, row in zip(row_rad, c2d):
        lines.append(" ".join([f0(x)] + [f0(v) for v in row]))
    return "\n".join(lines)


def _factor_props(conf: dict, prop: dict) -> list[str]:
    """geometry factor properties: qbar-psf always first, then Sw, bw, cbar."""
    factor_props = ["aero/qbar-psf"]
    for f in conf.get("factors", []):
        if f == "Sw":
            factor_props.append(prop["Sw"])
        elif f == "bw":
            factor_props.append(prop["bw"])
        elif f == "cbar":
            factor_props.append(prop["cbar"])
    return factor_props


def generate_xml(
    tables: dict,
    js_config: dict,
    geometry: dict,
    template_dir: str | Path = "",
    template_name: str = "aerodynamics.xml.j2",
) -> str:
    """Render the <aerodynamics> block.  tables = aero_tables.json content."""
    env = Environment(
        loader=FileSystemLoader(str(template_dir or Path(__file__).parent.parent / "templates")),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tmpl = env.get_template(template_name)

    axes = js_config["axes"]
    prop = js_config["property_map"]
    table_to_axis = js_config.get("table_to_axis", {})
    coeff_of_axis = {axis: coeff for coeff, axis in table_to_axis.items()}

    # geometry in Imperial
    ref = geometry["reference"]
    sw_ft = _units.m2_to_ft2(ref["S_ref_m2"])
    bw_ft = _units.m_to_ft(ref["b_ref_m"])
    cbar_ft = _units.m_to_ft(ref["cbar_ref_m"])
    qs_props = {
        "Sw": "aero/qbar-psf",  # placeholder to satisfy overlay; replaced below
    }

    blocks: list[dict] = []
    for axis_name, conf in axes.items():
        coeff = coeff_of_axis.get(axis_name)
        if coeff not in COEFF_FIELDS:
            continue
        tab = tables["axes"].get(axis_name)
        if not tab or tab.get("status") != "ok":
            continue
        ind_var = conf["independent_var"]  # "alpha" or "beta"
        prop_name = prop[ind_var] if ind_var in prop else None
        factor_props = _factor_props(conf, prop)

        if tab.get("dim") == "2d":
            row_var = tab.get("row_var", ind_var)
            col_var = tab.get("col_var", "")
            row_prop = prop.get(row_var, prop_name)
            col_prop = prop.get(col_var, "")
            grid_rows = len(tab.get("row_x_deg", []))
            grid_cols = len(tab.get("col_y_deg", []))
            blocks.append({
                "axis": axis_name,
                "axis_comment": AXIS_OUTPUT[axis_name],
                "coeff": coeff,
                "coeff_long": COEFF_LONG[coeff],
                "dim": "2d",
                "indep_prop": prop_name,
                "row_prop": row_prop,
                "col_prop": col_prop,
                "indep_rad_or_deg": "rad",
                "num_points": grid_rows * grid_cols,
                "cases": tab.get("cases", []),
                # JSBSim FGTable2 gridded layout: line 1 = column breakpoints
                # (radians), then one line per row (row breakpoint + one value
                # per column).
                "table_data": _table_data_2d(
                    tab["row_x_rad"], tab["col_y_rad"], tab["c2d"]),
                "controls": [
                    {
                        "prop": prop.get(c["control"], c["control"]),
                        "rows": _table_rows_1d(c["x_rad"], c["c"]),
                        "num_points": len(c.get("x_rad", [])),
                    }
                    for c in tab.get("controls", [])
                    if c.get("status") == "ok"
                ],
                "factors": factor_props,
            })
            continue

        # ---- 1D single-table path (unchanged) ---------------------------
        x_rad = tab["x_rad"]
        c = tab["c"]
        # JSBSim's handler for a `lookup="row"` 1D table reads rows (2 columns
        # each) separated by newlines.  Building the rows here (rather than a
        # Jinja for-loop, whose whitespace control collapses them onto one
        # line) keeps the emitted table valid for JSBSim's parser.
        break_rows = "\n".join(
            f"{_fmt(v)}  {_fmt(w)}" for v, w in zip(x_rad, c)
        )
        blocks.append({
            "axis": axis_name,
            "axis_comment": AXIS_OUTPUT[axis_name],
            "coeff": coeff,
            "coeff_long": COEFF_LONG[coeff],
            "dim": "1d",
            "indep_prop": prop_name,
            "indep_rad_or_deg": "rad",
            "num_points": len(x_rad),
            "cases": tab.get("cases", []),
            "table_rows": break_rows,
            "factors": factor_props,
        })

    return tmpl.render(
        blocks=blocks,
        has_2d=any(b.get("dim") == "2d" for b in blocks),
        generated_utc=generated_utc(),
        sw_ft=sw_ft, bw_ft=bw_ft, cbar_ft=cbar_ft,
        scale=1.0,
    )


def write_xml(path: str | Path, xml: str) -> None:
    Path(path).write_text(xml, encoding="utf-8")
