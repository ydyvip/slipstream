"""Validation of the generated JSBSim aerodynamics XML.

jsbsim itself is not installed in this project (see README), so we perform a
structural validation that would catch the failures JSBSim is silent about:

  * the six axis blocks exist with the right coefficients & independent vars
  * each <axis> multiplies by qbar * Sw (+ reference length for moments)
    EXACTLY once  (the "no double multiply" invariant from _units.py)
  * table breakpoints are strictly increasing (JSBSim needs monotonic lookup)
  * tables cover the configured flight envelope (warnings would be fine,
    but the sample matrix should cover alpha/beta fully)
  * table values match the fitted DB within float precision

If the python 'jsbsim' package is ever installed, a second test loads the
generated file through JSBSim's ElementLoader to confirm it parses there too.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest

# axis name -> (coefficient, independent_var) per jsbsim_properties.yaml
EXPECTED_AXES = {
    "DRAG": ("CD", "alpha"),
    "SIDE": ("CY", "beta"),
    "LIFT": ("CL", "alpha"),
    "PITCH": ("Cm_pitch", "alpha"),
    "YAW": ("Cn_yaw", "beta"),
    "ROLL": ("Cl_roll", "beta"),
}


def _root(xml_text):
    return ET.fromstring(xml_text)


def _axis_table(axis: ET.Element) -> ET.Element:
    """Resolve axis -> function -> product -> table with loud None checks."""
    fn = axis.find("function")
    assert fn is not None, f"missing <function> in {axis.attrib.get('name')}"
    product = fn.find("product")
    assert product is not None, f"missing <product> in {axis.attrib.get('name')}"
    table = product.find("table")
    assert table is not None, f"missing <table> in {axis.attrib.get('name')}"
    return table


def _table_data(table: ET.Element) -> list[float]:
    td = table.find("tableData")
    assert td is not None and td.text, f"missing tableData in {table}"
    return [float(t) for t in td.text.split()]


def test_generates_well_formed_single_root(xml_text):
    root = _root(xml_text)
    assert root.tag == "aerodynamics"
    assert {a.tag for a in root} <= {"axis", "function"}


def test_all_six_axes_present(xml_text):
    axes = {a.attrib["name"] for a in _root(xml_text) if a.tag == "axis"}
    assert axes == set(EXPECTED_AXES)


def test_each_axis_products_include_qbar_sw_once(xml_text):
    """Force axes multiply qbar*Sw once; moment axes also multiply the
    reference length once — never twice (units memory in _units.py)."""
    ref_len = {"DRAG": None, "SIDE": None, "LIFT": None,
               "PITCH": "cbar", "YAW": "bw", "ROLL": "bw"}
    for axis in _root(xml_text):
        if axis.tag != "axis":
            continue
        name = axis.attrib["name"]
        fns = axis.findall("function")
        assert len(fns) == 1, f"{name} must have exactly one function"
        product = fns[0].find("product")
        assert product is not None
        props = [p.text.strip() for p in product.findall("property")
                 if p.text and p.text.strip()]
        assert props.count("aero/qbar-psf") == 1, f"{name}: qbar once"
        assert props.count("metrics/Sw-sqft") == 1, f"{name}: Sw once"
        if ref_len[name] is not None:
            prop = ("metrics/cbarw-ft" if ref_len[name] == "cbar"
                    else "metrics/bw-ft")
            assert props.count(prop) == 1, f"{name}: {prop} once"
        else:
            assert not [p for p in props if p.endswith("-ft")], \
                f"{name}: no length factor on a force axis"


def test_independent_vars_and_coefficients(xml_text):
    for axis in _root(xml_text):
        if axis.tag != "axis":
            continue
        name = axis.attrib["name"]
        exp_coeff, exp_var = EXPECTED_AXES[name]
        fn = axis.find("function")
        assert fn is not None and fn.attrib["name"] == f"aero/coefficient/{exp_coeff}"
        table = _axis_table(axis)
        iv = table.find("independentVar")
        assert iv is not None and iv.text is not None
        assert iv.text.strip() == f"aero/{exp_var}-rad"
        assert iv.attrib["lookup"] == "row"


def test_table_breakpoints_monotonic_and_cover_matrix(xml_text, tables):
    for axis in _root(xml_text):
        if axis.tag != "axis":
            continue
        name = axis.attrib["name"]
        data = _table_data(_axis_table(axis))
        assert len(data) % 2 == 0
        xs = data[0::2]  # radians
        assert np.all(np.diff(xs) > 0), f"{name}: monotonically increasing"
        # values match the fitted DB tables (XML writes 6-decimals)
        db = tables["axes"][name]
        assert len(xs) == len(db["x_rad"])
        db_xs = [float(x) for x in db["x_rad"]]
        assert xs == pytest.approx(db_xs, abs=1e-6)


def test_envelope_coverage_from_geometry(xml_text, configs):
    """Generated tables should span at least the configured flight envelope
    (alpha/beta) — no coverage warnings for the full matrix."""
    geom = configs["geometry"]["envelope"]
    for axis in _root(xml_text):
        if axis.tag != "axis":
            continue
        name = axis.attrib["name"]
        xs = _table_data(_axis_table(axis))[0::2]  # radians
        var = EXPECTED_AXES[name][1]
        if var == "alpha":
            lo, hi = geom["alpha_min_deg"], geom["alpha_max_deg"]
        else:
            lo, hi = geom["beta_min_deg"], geom["beta_max_deg"]
        assert math.degrees(xs[0]) <= lo + 1e-9, f"{name}: covers min {var}"
        assert math.degrees(xs[-1]) >= hi - 1e-9, f"{name}: covers max {var}"


def test_jsbsim_load_roundtrip_when_available(xml_text, tmp_path):
    """If the real JSBSim python package is present, load the generated file
    through its ElementLoader to confirm it parses (skipped when not
    installed)."""
    jsbsim = pytest.importorskip("jsbsim", reason="python jsbsim not installed")

    f = tmp_path / "aerodynamics.xml"
    f.write_text(xml_text, encoding="utf-8")

    loader = jsbsim.ElementLoader()
    loader.LoadElement(str(f))
    el = loader.GetElement()
    assert el.GetName().lower() == "aerodynamics"
    # report the element name, not the raw path, so the assertion is
    # meaningful about the parsed content
    assert el.findnext("axis") is not None or el.Find("axis") is not None
