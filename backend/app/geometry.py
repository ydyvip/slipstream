"""STL loading, unit scaling, centering, yaw rotation, bbox and frontal area."""
from __future__ import annotations

import math

import numpy as np
import trimesh

UNIT_SCALE = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254}


def prepare_stl(stl_path: str, unit: str, yaw_deg: float, out_path: str,
                pitch_deg: float = 0.0, roll_deg: float = 0.0,
                deflections: list[dict] | None = None) -> dict:
    """Load an STL, scale to meters, center bbox at origin, rotate the model
    (roll about X, then pitch about Y, then -yaw about Z; wind stays along +X),
    save a binary STL at out_path. Positive pitch = nose-down (forward-flight
    tilt). Optional `deflections` rotate rigid connected components about hinge
    lines (see _apply_deflections) after the orientation chain, so hinge
    coordinates are given in the oriented, centered frame. Returns model
    metadata (SI units)."""
    scale = UNIT_SCALE[unit]
    mesh = trimesh.load(stl_path, file_type="stl", force="mesh")
    if mesh.is_empty or len(mesh.faces) == 0:
        raise ValueError("STL contains no triangles")
    # Watertight (closed, manifold) meshes mesh cleanly; open/degenerate ones
    # are the usual cause of cryptic snappyHexMesh failures — flag, don't block.
    watertight = bool(mesh.is_watertight)

    mesh.apply_scale(scale)

    # Center bounding-box center at origin.
    center = mesh.bounds.mean(axis=0)
    c1 = [float(v) for v in center]
    c2 = [0.0, 0.0, 0.0]
    mesh.apply_translation(-center)

    if roll_deg:
        rot = trimesh.transformations.rotation_matrix(
            math.radians(roll_deg), [1, 0, 0], [0, 0, 0]
        )
        mesh.apply_transform(rot)
    if pitch_deg:
        rot = trimesh.transformations.rotation_matrix(
            math.radians(pitch_deg), [0, 1, 0], [0, 0, 0]
        )
        mesh.apply_transform(rot)
    if yaw_deg:
        rot = trimesh.transformations.rotation_matrix(
            math.radians(-yaw_deg), [0, 0, 1], [0, 0, 0]
        )
        mesh.apply_transform(rot)
    if roll_deg or pitch_deg or yaw_deg:
        # Re-center after rotation (bbox changes).
        center = mesh.bounds.mean(axis=0)
        c2 = [float(v) for v in center]
        mesh.apply_translation(-center)

    # v10 control-surface deflections: hinged all-moving parts (e.g. a
    # stabilator) rotate rigidly about their hinge line, in the oriented,
    # centered frame the hinge coordinates above were given in.
    if deflections:
        mesh = _apply_deflections(mesh, deflections)

    mesh.export(out_path, file_type="stl")  # binary STL

    bbox = mesh.bounds  # (2, 3)
    frontal_area = frontal_area_yz(mesh.triangles, resolution=512)

    sym_error = symmetry_error_y(mesh)

    return {
        "bbox_m": [list(map(float, bbox[0])), list(map(float, bbox[1]))],
        "frontal_area_m2": float(frontal_area),
        "triangles": int(len(mesh.faces)),
        "centroid": [float(c) for c in mesh.bounds.mean(axis=0)],
        "watertight": watertight,
        "symmetry_error": sym_error,
        "symmetric": bool(sym_error < 0.02),
        "_c1": c1,
        "_c2": c2,
    }


def _apply_deflections(mesh: trimesh.Trimesh,
                       deflections: list[dict]) -> trimesh.Trimesh:
    """Rotate selected connected components rigidly about hinge lines.

    Each spec is {"body": int | None, "axis": [x,y,z], "point": [x,y,z],
    "angle_deg": float}. With an int `body`, the component at that split()
    index rotates. With `body: None`, every component whose centroid lies on
    the "downstream" side of the hinge plane rotates —
    dot(centroid - point, axis) > 0 — which is the all-moving-surface
    semantics (the part of the model the hinge swings away from its mount).

    A deflection is a rigid-body rotation (trimesh's rotation_matrix about the
    hinge line through `point` along `axis`), so each rotated component stays a
    closed shell and the reassembled mesh is still watertight. Real-world
    caveat: rotating a connected component about a hinge that sits away from
    its interface to the rest of the model leaves a small gap / overlap at the
    mount — physically the same as a stabilator's hinge gap — which the mesh
    build and solver absorb.
    """
    parts = mesh.split(only_watertight=False)
    n = len(parts)
    rotated = False
    for spec in deflections:
        body = spec.get("body")
        axis = np.asarray(spec["axis"], dtype=float)
        norm = float(np.linalg.norm(axis))
        if norm == 0:
            raise ValueError("deflection axis must be non-zero")
        axis = axis / norm
        point = np.asarray(spec["point"], dtype=float)
        angle_deg = float(spec["angle_deg"])
        if body is None:
            chosen = [i for i, p in enumerate(parts)
                      if np.dot(p.centroid - point, axis) > 0]
        else:
            if not (isinstance(body, int) and not isinstance(body, bool)
                    and 0 <= body < n):
                raise ValueError(
                    f"deflection body must be a component index in [0, {n}) "
                    f"or null, got {body!r}")
            chosen = [int(body)]
        if not chosen:
            continue
        rot = trimesh.transformations.rotation_matrix(
            math.radians(angle_deg), axis, point)
        for i in chosen:
            parts[i] = parts[i].apply_transform(rot)
        rotated = True
    if not rotated:
        return mesh  # nothing selected: leave the prepared mesh untouched
    if n == 1:
        return parts[0]
    return trimesh.util.concatenate(parts)


def symmetry_error_y(mesh) -> float:
    """Mirror-symmetry error about the X-Z plane (Y=0), normalized by the
    model's Y-extent W. Uses the mesh *vertices*: a body that is mirror-
    symmetric about its centerline has vertices in exact ±Y pairs, so each
    Y-mirrored vertex sits right on top of an original one (distance ~0). We
    report the 90th-percentile nearest-neighbour distance / W, so a missing or
    shifted side (whose mirror lands in empty space) scores high. The search is
    against *every* vertex (KD-tree): against a subsample, a large mesh with big
    flat triangles scored ~0.02 even when exactly symmetric. inf for a
    degenerate (zero-width) model."""
    from scipy.spatial import cKDTree

    lo, hi = mesh.bounds
    W = float(hi[1] - lo[1])
    if W <= 0:
        return float("inf")
    V = np.asarray(mesh.vertices, dtype=np.float64)
    if len(V) == 0:
        return float("inf")
    q = V if len(V) <= 20000 else V[np.random.default_rng(1).choice(len(V), 20000, replace=False)]
    dmin, _ = cKDTree(V).query(q * np.array([1.0, -1.0, 1.0]))
    return float(np.percentile(dmin, 90) / W)


def transform_props(props: list[dict], unit: str, yaw_deg: float,
                    pitch_deg: float, model: dict,
                    roll_deg: float = 0.0) -> list[dict]:
    """Map propeller disk specs given in original STL coordinates into the
    prepared model frame (meters, centered, pitched, yawed) — the same
    transform prepare_stl applies to the mesh. Each prop: {"center": [x,y,z]
    original units, "diameter": original units, "thrust_g": grams}. The thrust
    axis is +Z in the model's own frame (rotates with pitch/yaw).

    Reconstructing the exact two centering shifts prepare_stl used would
    require the mesh; instead we replay it: scale/center/rotate the centers
    with the recorded final bbox center of the *model* as reference. To keep
    this exact, prepare_stl is re-run logic-free here: we recompute both
    centering shifts from the raw mesh bounds passed via `model["_c1"]` /
    `model["_c2"]` recorded during preparation."""
    import numpy as np
    scale = UNIT_SCALE[unit]
    c1 = np.asarray(model["_c1"])
    c2 = np.asarray(model["_c2"])
    rr = trimesh.transformations.rotation_matrix(
        math.radians(roll_deg), [1, 0, 0])[:3, :3]
    rp = trimesh.transformations.rotation_matrix(
        math.radians(pitch_deg), [0, 1, 0])[:3, :3]
    ry = trimesh.transformations.rotation_matrix(
        math.radians(-yaw_deg), [0, 0, 1])[:3, :3]
    # Same order prepare_stl applies to the mesh: roll, then pitch, then yaw.
    rot = ry @ rp @ rr
    out = []
    for p in props:
        c = rot @ (np.asarray(p["center"], dtype=float) * scale - c1) - c2
        axis = rot @ np.asarray([0.0, 0.0, 1.0])
        out.append({
            "center_m": [float(v) for v in c],
            "axis": [float(v) for v in axis],
            "diameter_m": float(p["diameter"]) * scale,
            "thrust_N": float(p["thrust_g"]) * 9.81 / 1000.0,
        })
    return out


def frontal_area_yz(triangles: np.ndarray, resolution: int = 512) -> float:
    """Project triangles onto the YZ plane and rasterize to estimate the
    frontal area (as seen by flow along +X). triangles: (n, 3, 3)."""
    # 2D projected triangles: (n, 3, 2) with columns (y, z)
    tri2 = triangles[:, :, 1:3].astype(np.float64)

    lo = tri2.reshape(-1, 2).min(axis=0)
    hi = tri2.reshape(-1, 2).max(axis=0)
    span = hi - lo
    if span[0] <= 0 or span[1] <= 0:
        return 0.0
    # small padding so edge pixels are not clipped
    pad = 1e-9 + span * 1e-6
    lo -= pad
    hi += pad
    span = hi - lo

    cell = span / resolution
    mask = np.zeros((resolution, resolution), dtype=bool)

    # Pixel-center coordinates
    for tri in tri2:
        # Pixel bbox of this triangle
        tmin = np.floor((tri.min(axis=0) - lo) / cell).astype(int)
        tmax = np.ceil((tri.max(axis=0) - lo) / cell).astype(int)
        tmin = np.clip(tmin, 0, resolution - 1)
        tmax = np.clip(tmax, 1, resolution)
        iy = np.arange(tmin[0], tmax[0])
        iz = np.arange(tmin[1], tmax[1])
        if len(iy) == 0 or len(iz) == 0:
            continue
        py = lo[0] + (iy + 0.5) * cell[0]
        pz = lo[1] + (iz + 0.5) * cell[1]
        PY, PZ = np.meshgrid(py, pz, indexing="ij")

        a, b, c = tri[0], tri[1], tri[2]
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-30:
            continue
        w1 = ((b[1] - c[1]) * (PY - c[0]) + (c[0] - b[0]) * (PZ - c[1])) / d
        w2 = ((c[1] - a[1]) * (PY - c[0]) + (a[0] - c[0]) * (PZ - c[1])) / d
        w3 = 1.0 - w1 - w2
        eps = -1e-9
        inside = (w1 >= eps) & (w2 >= eps) & (w3 >= eps)
        mask[tmin[0]:tmax[0], tmin[1]:tmax[1]] |= inside

    return float(mask.sum() * cell[0] * cell[1])
