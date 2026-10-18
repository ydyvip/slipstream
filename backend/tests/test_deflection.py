"""prepare_stl(..., deflections) — hinged all-moving control surfaces.

A deflection rotates a rigid connected component about a hinge line: the moving
part keeps its exact shape (watertightness is preserved) and the rest of the
model stays put. Hinge coordinates are given in the oriented, centered frame,
i.e. AFTER the scale -> center -> roll -> pitch -> -yaw chain."""
from __future__ import annotations

import numpy as np
import trimesh

from app.geometry import prepare_stl


def _two_body_stl(path) -> None:
    """Two adjacent 100 mm boxes with a 10 mm gap, so split() yields exactly
    two connected components: a "fuselage" around the origin and a "+X tail"."""
    fuselage = trimesh.creation.box(extents=[100, 100, 100])
    tail = trimesh.creation.box(extents=[100, 100, 100])
    tail.apply_translation([110, 0, 0])
    trimesh.util.concatenate([fuselage, tail]).export(path, file_type="stl")


def _parts(path):
    mesh = trimesh.load(path, file_type="stl", force="mesh")
    return mesh, mesh.split(only_watertight=False)


def test_deflecting_body_0_rotates_it_and_leaves_body_1(tmp_path):
    src = tmp_path / "two.stl"
    _two_body_stl(src)
    out = tmp_path / "prepared.stl"
    # +90° about the Z hinge through the origin (the fuselage/tail interface,
    # which lands on the origin after centering). Body 0 is the fuselage.
    model = prepare_stl(str(src), "mm", 0.0, str(out),
                        deflections=[{"body": 0, "axis": [0, 0, 1],
                                      "point": [0, 0, 0], "angle_deg": 90.0}])
    deflected, parts = _parts(out)
    assert deflected.is_watertight
    assert len(parts) == 2

    # Tail (~[+0.055, 0, 0] in the prepared frame) is untouched.
    static = max(parts, key=lambda p: p.centroid[0])
    assert np.allclose(static.centroid, [0.055, 0.0, 0.0], atol=1e-9)
    # Fuselage (~[-0.055, 0, 0]) rotated +90° about Z through the origin:
    # centroid goes to [0, -0.055, 0].
    moving = min(parts, key=lambda p: p.centroid[0])
    assert np.allclose(moving.centroid, [0.0, -0.055, 0.0], atol=1e-9)

    # Geometry props come from the FINAL (deflected) mesh, not the pre-rotation
    # input: the fuselage now sticks out in Y, so the frontal area grew.
    ref = prepare_stl(str(src), "mm", 0.0, str(tmp_path / "ref.stl"))
    assert model["frontal_area_m2"] > ref["frontal_area_m2"]
    assert model["bbox_m"] != ref["bbox_m"]


def test_static_body_keeps_exact_vertices(tmp_path):
    src = tmp_path / "two.stl"
    _two_body_stl(src)
    ref_path = tmp_path / "ref.stl"
    def_path = tmp_path / "def.stl"
    prepare_stl(str(src), "mm", 0.0, str(ref_path))
    prepare_stl(str(src), "mm", 0.0, str(def_path),
                deflections=[{"body": 0, "axis": [0, 0, 1],
                              "point": [0, 0, 0], "angle_deg": 90.0}])
    _, ref_parts = _parts(ref_path)
    _, got_parts = _parts(def_path)
    # Body 0 rotates: its vertices move. Body 1 keeps every vertex.
    assert not np.array_equal(got_parts[0].vertices, ref_parts[0].vertices)
    assert np.allclose(np.sort(got_parts[1].vertices, axis=0),
                       np.sort(ref_parts[1].vertices, axis=0), atol=1e-12)


def test_body_none_rotates_the_downstream_side_of_the_hinge(tmp_path):
    """body: null selects every component whose centroid satisfies
    dot(centroid - point, axis) > 0 — the all-moving-tail semantics. With the
    hinge plane through the origin normal to +X, only the +X tail is picked."""
    src = tmp_path / "two.stl"
    _two_body_stl(src)
    ref_path = tmp_path / "ref.stl"
    def_path = tmp_path / "def.stl"
    prepare_stl(str(src), "mm", 0.0, str(ref_path))
    prepare_stl(str(src), "mm", 0.0, str(def_path),
                deflections=[{"body": None, "axis": [1, 0, 0],
                              "point": [0, 0, 0], "angle_deg": 90.0}])
    _, ref_parts = _parts(ref_path)
    def_mesh, got_parts = _parts(def_path)
    assert def_mesh.is_watertight
    assert len(got_parts) == 2
    # Upstream (the -X fuselage) is untouched; the downstream tail +X rotated.
    static = min(got_parts, key=lambda p: p.centroid[0])
    ref_static = min(ref_parts, key=lambda p: p.centroid[0])
    assert np.allclose(np.sort(static.vertices, axis=0),
                       np.sort(ref_static.vertices, axis=0), atol=1e-12)
    moving = max(got_parts, key=lambda p: p.centroid[0])
    ref_moving = max(ref_parts, key=lambda p: p.centroid[0])
    assert not np.array_equal(moving.vertices, ref_moving.vertices)


def test_no_deflections_is_identical_to_plain_prepare(tmp_path):
    """deflections=None/[] must not touch anything: byte-identical STL output
    and identical metadata (the pre-existing behavior)."""
    src = tmp_path / "two.stl"
    _two_body_stl(src)
    a = tmp_path / "a.stl"
    b = tmp_path / "b.stl"
    r1 = prepare_stl(str(src), "mm", 7.0, str(a), pitch_deg=3.0, roll_deg=2.0)
    r2 = prepare_stl(str(src), "mm", 7.0, str(b), pitch_deg=3.0, roll_deg=2.0,
                     deflections=[])
    assert a.read_bytes() == b.read_bytes()
    assert r1["bbox_m"] == r2["bbox_m"]
    assert r1["frontal_area_m2"] == r2["frontal_area_m2"]
    assert r1["_c1"] == r2["_c1"] and r1["_c2"] == r2["_c2"]
