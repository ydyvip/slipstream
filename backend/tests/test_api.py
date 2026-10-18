"""API endpoints end to end, against a throwaway data directory."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

import pytest
import trimesh

if "app.main" in sys.modules:  # pragma: no cover — never touch real run data
    pytest.skip("app.main already imported with the real data dir", allow_module_level=True)
os.environ["SLIPSTREAM_DATA_DIR"] = tempfile.mkdtemp(prefix="slipstream-test-")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from tests.test_repair import SPHERE, _broken_assembly  # noqa: E402

client = TestClient(main.app)  # no lifespan: startup migrations don't run


def _post(path: str, stl_path: Path):
    with open(stl_path, "rb") as fh:
        return client.post(path, files={"stl": (stl_path.name, fh, "model/stl")})


def test_inspect_endpoint():
    res = _post("/api/stl/inspect", SPHERE)
    assert res.status_code == 200
    assert res.json()["watertight"] is True


def test_inspect_rejects_non_stl():
    res = client.post("/api/stl/inspect", files={"stl": ("x.stl", b"not an stl", "model/stl")})
    assert res.status_code == 422


def test_repair_job_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(main.repair, "repair_stl",
                        partial(main.repair.repair_stl, resolution=120,
                                target_triangles=20_000))
    res = _post("/api/repair", _broken_assembly(tmp_path))
    assert res.status_code == 201
    job_id = res.json()["id"]

    deadline = time.time() + 120
    while True:
        job = client.get(f"/api/repair/{job_id}").json()
        if job["status"] != "running" or time.time() > deadline:
            break
        time.sleep(0.2)
    assert job["status"] == "done", job
    assert job["report"]["watertight"] and job["report"]["bodies"] == 1

    stl = client.get(f"/api/repair/{job_id}/stl")
    assert stl.status_code == 200
    out = tmp_path / "from_api.stl"
    out.write_bytes(stl.content)
    assert trimesh.load(out, force="mesh").is_watertight


def test_unknown_job_is_404():
    assert client.get("/api/repair/nope").status_code == 404
    assert client.get("/api/repair/nope/stl").status_code == 404


def test_run_is_refused_without_openfoam(monkeypatch):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: None)
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": '{"unit":"mm","wind_speed":15,"quality":"coarse"}'})
    assert res.status_code == 503
    assert "brew install --cask gerlero/openfoam/openfoam" in res.json()["detail"]
    assert client.get("/api/health").json()["openfoam"] is None


def test_health_reports_openfoam_path(monkeypatch):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    assert client.get("/api/health").json()["openfoam"] == "/opt/homebrew/bin/openfoam"


@pytest.mark.parametrize("extra, fragment", [
    ({"mesh_sweep": {"tol_pct": 2}, "trim": {"weight_g": 700}}, "cannot be combined"),
    ({"mesh_sweep": {"tol_pct": 2}, "yaw_sweep": [0, 15]}, "cannot be combined"),
    ({"mesh_sweep": {"tol_pct": 0}}, "tol_pct"),
    ({"mesh_sweep": {"tol_pct": 80}}, "tol_pct"),
    ({"mesh_sweep": "yes"}, "mesh_sweep must be an object"),
])
def test_mesh_sweep_validation(monkeypatch, extra, fragment):
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    cfg = {"unit": "mm", "wind_speed": 15, "quality": "coarse", **extra}
    if "trim" in extra:
        cfg["props"] = [{"center": [0, 0, 0], "diameter": 127, "thrust_g": 200}]
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": _json.dumps(cfg)})
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]


def _post_run(cfg: dict):
    import json as _json
    with open(SPHERE, "rb") as fh:
        return client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                           data={"config": _json.dumps(cfg)})


PROPS = [{"center": [0, 0, 0], "diameter": 127, "thrust_g": 200}]


@pytest.mark.parametrize("extra, fragment", [
    ({"refinement": "long"}, "refinement must be an object"),
    ({"refinement": {"wake": True}}, "refinement must be an object"),
    ({"refinement": {"long_wake": 1}}, "refinement must be an object"),
    ({"refinement": {"prop_slipstream": True}}, "requires propeller disks"),
])
def test_refinement_validation(monkeypatch, extra, fragment):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse", **extra})
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]


@pytest.mark.parametrize("refinement, stored", [
    ({"long_wake": True, "prop_slipstream": True},
     {"long_wake": True, "prop_slipstream": True}),
    ({"long_wake": True, "prop_slipstream": False}, {"long_wake": True}),
    ({"long_wake": False}, None),
])
def test_refinement_is_normalized_into_run_config(monkeypatch, refinement, stored):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    # Capture the config instead of queuing a real OpenFOAM run.
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg: submitted.append(cfg) or "fake-id")
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse",
                     "props": PROPS, "refinement": refinement})
    assert res.status_code == 201, res.text
    assert submitted[0].get("refinement") == stored


# -- re-solve on an existing mesh ---------------------------------------------

QUAD_CFG = {"name": "quad", "unit": "mm", "wind_speed": 15, "quality": "coarse",
            "props": PROPS * 4, "sweep_param": "yaw"}


@pytest.fixture
def finished_run(monkeypatch):
    """A done run with a mesh on disk, plus a captured (never queued) submit."""
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg, group_id=None: submitted.append(cfg) or "child")
    made = []

    def make(cfg=QUAD_CFG, mesh=True, **state):
        import uuid as _uuid
        rid = f"20260101-000000-{_uuid.uuid4().hex[:6]}"
        rd = main.DATA_DIR / rid
        poly = rd / "case" / "constant" / "polyMesh"
        poly.mkdir(parents=True)
        if mesh:
            (poly / "owner").write_text("mesh")
        (rd / "model.stl").write_bytes(SPHERE.read_bytes())
        (rd / "config.json").write_text(_json.dumps(cfg))
        main.runner.states[rid] = {
            "id": rid, "name": cfg["name"], "status": "done", "progress": 1.0,
            "message": "", "created_at": 0.0, "config": cfg, "group_id": None,
            "model": None, "mesh_cells": 1000, "result": None, "error": None,
            "log": None, **state}
        made.append(rid)
        return rid

    make.submitted = submitted
    yield make
    for rid in made:
        main.runner.states.pop(rid, None)


def test_resolve_inherits_mesh_inputs_and_applies_new_speed_and_thrust(finished_run):
    rid = finished_run()
    assert client.get(f"/api/runs/{rid}").json()["has_mesh"] is True
    res = client.post(f"/api/runs/{rid}/resolve", json={"wind_speed": 25, "thrust_g": 250})
    assert res.status_code == 201, res.text
    cfg, = finished_run.submitted
    assert cfg["mesh_from"] == rid
    assert cfg["wind_speed"] == 25.0
    assert [p["thrust_g"] for p in cfg["props"]] == [250.0] * 4
    assert cfg["name"] == "quad @ 25 m/s re-solve"
    assert cfg["quality"] == "coarse" and "sweep_param" not in cfg


def test_resolve_per_prop_thrust_and_custom_name(finished_run):
    rid = finished_run()
    res = client.post(f"/api/runs/{rid}/resolve",
                      json={"thrust_g": [100, 200, 300, 400], "name": " hover check "})
    assert res.status_code == 201, res.text
    cfg, = finished_run.submitted
    assert [p["thrust_g"] for p in cfg["props"]] == [100.0, 200.0, 300.0, 400.0]
    assert cfg["wind_speed"] == 15.0 and cfg["name"] == "hover check"


def test_resolve_of_a_resolve_keeps_the_base_name(finished_run):
    child_cfg = dict(QUAD_CFG, name="quad @ 25 m/s re-solve", resolve_base_name="quad")
    rid = finished_run(child_cfg)
    assert client.post(f"/api/runs/{rid}/resolve", json={"wind_speed": 10}).status_code == 201
    assert finished_run.submitted[0]["name"] == "quad @ 10 m/s re-solve"


@pytest.mark.parametrize("body, fragment", [
    ({"yaw_deg": 15}, "only wind_speed, thrust_g and name"),
    ({"wind_speed": 0}, "wind_speed must be"),
    ({"thrust_g": [100, 200]}, "list of 4"),
    ({"thrust_g": -1}, "thrust_g must be"),
    ({"name": "  "}, "name must be"),
    ([1, 2], "body must be a JSON object"),
])
def test_resolve_validation(finished_run, body, fragment):
    rid = finished_run()
    res = client.post(f"/api/runs/{rid}/resolve", json=body)
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]
    assert not finished_run.submitted


def test_resolve_thrust_needs_props(finished_run):
    rid = finished_run({k: v for k, v in QUAD_CFG.items() if k != "props"})
    res = client.post(f"/api/runs/{rid}/resolve", json={"thrust_g": 100})
    assert res.status_code == 422 and "propeller disks" in res.json()["detail"]


@pytest.mark.parametrize("kwargs", [
    {"mesh": False},
    {"compacted": True},
    {"mesh_cells": None},
])
def test_resolve_needs_a_mesh_on_disk(finished_run, kwargs):
    rid = finished_run(**kwargs)
    assert client.get(f"/api/runs/{rid}").json()["has_mesh"] is False
    res = client.post(f"/api/runs/{rid}/resolve", json={"wind_speed": 20})
    assert res.status_code == 409 and "Re-run" in res.json()["detail"]


# -- rename -------------------------------------------------------------------

def test_rename_run(finished_run):
    rid = finished_run()
    res = client.patch(f"/api/runs/{rid}", json={"name": "  quad, props at 300 g  "})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "quad, props at 300 g"
    assert client.get(f"/api/runs/{rid}").json()["name"] == "quad, props at 300 g"
    assert any(r["name"] == "quad, props at 300 g" for r in client.get("/api/runs").json())


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "x" * 201}, {"name": 5},
                                  {"name": "ok", "wind_speed": 20}, {}, [1]])
def test_rename_validation(finished_run, body):
    rid = finished_run()
    assert client.patch(f"/api/runs/{rid}", json=body).status_code == 422
    assert client.get(f"/api/runs/{rid}").json()["name"] == "quad"


def test_rename_unknown_run_is_404():
    assert client.patch("/api/runs/nope", json={"name": "x"}).status_code == 404


# -- motor detection ------------------------------------------------------------

QUAD_STL = Path(__file__).resolve().parents[2] / "examples" / "quad_frame.stl"


def test_detect_props_endpoint_finds_quad_motors():
    with open(QUAD_STL, "rb") as fh:
        res = client.post("/api/stl/props", files={"stl": ("q.stl", fh, "model/stl")},
                          data={"unit": "mm"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reason"] is None and len(body["props"]) == 4


def test_detect_props_endpoint_declines_a_sphere():
    res = _post("/api/stl/props", SPHERE)
    assert res.status_code == 200
    assert res.json()["props"] == [] and res.json()["reason"]


def test_detect_props_endpoint_validates_input():
    with open(QUAD_STL, "rb") as fh:
        assert client.post("/api/stl/props", files={"stl": ("q.stl", fh, "model/stl")},
                           data={"unit": "furlong"}).status_code == 422
    assert client.post("/api/stl/props", files={
        "stl": ("x.stl", b"not an stl", "model/stl")}).status_code == 422


# -- mesh import ------------------------------------------------------------------

IMPORT_PATCHES = [
    {"name": "inflow", "type": "patch", "faces": 10, "center_m": [-1.0, 0, 0]},
    {"name": "outflow", "type": "patch", "faces": 10, "center_m": [3.0, 0, 0]},
    {"name": "farfield", "type": "patch", "faces": 40, "center_m": [1.0, 0, 0]},
    {"name": "hull", "type": "wall", "faces": 200, "center_m": [0.0, 0, 0]},
]
IMPORT_ROLES = {"inflow": "inlet", "outflow": "outlet", "farfield": "slip", "hull": "model"}


@pytest.fixture
def inspected(monkeypatch):
    """An inspected import on disk, plus a captured (never queued) submit."""
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    import_id = "abc123" + "0" * 26
    d = main.IMPORT_DIR / import_id
    (d / "case" / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
    (d / "case" / "constant" / "polyMesh" / "owner").write_text("mesh")
    (d / "import.json").write_text(_json.dumps({
        "id": import_id, "filename": "hull_v3.msh", "format": "fluent", "unit": "mm",
        "cells": 123456, "patches": IMPORT_PATCHES}))
    submitted = []
    monkeypatch.setattr(main, "_submit_run", lambda stl, cfg, group_id=None, mesh_src=None:
                        submitted.append((stl, cfg, mesh_src)) or "imported-run")
    yield import_id, submitted
    shutil.rmtree(d, ignore_errors=True)


def test_import_run_is_created_from_an_inspected_mesh(inspected):
    import_id, submitted = inspected
    res = client.post("/api/runs/import", json={
        "import_id": import_id, "roles": IMPORT_ROLES, "wind_speed": 12, "quality": "coarse"})
    assert res.status_code == 201, res.text
    stl, cfg, mesh_src = submitted[0]
    assert stl is None and mesh_src == main.IMPORT_DIR / import_id / "case" / "constant" / "polyMesh"
    assert cfg["name"] == "hull_v3" and cfg["unit"] == "m" and cfg["wind_speed"] == 12.0
    assert cfg["mesh_import"]["roles"] == IMPORT_ROLES
    assert cfg["mesh_import"]["format"] == "fluent" and cfg["mesh_import"]["source_unit"] == "mm"


@pytest.mark.parametrize("change, status, fragment", [
    ({"roles": dict(IMPORT_ROLES, hull="slip")}, 422, "model role"),
    ({"roles": {"inflow": "outlet", "outflow": "inlet", "farfield": "slip", "hull": "model"}},
     422, "upstream"),
    ({"wind_speed": 0}, 422, "wind_speed"),
    ({"quality": "ultra"}, 422, "quality"),
    ({"yaw_deg": 10}, 422, "unknown keys: yaw_deg"),
    ({"ref_area_cm2": -5}, 422, "ref_area_cm2"),
    ({"import_id": "f" * 32}, 404, "inspect the mesh again"),
])
def test_import_run_validation(inspected, change, status, fragment):
    import_id, submitted = inspected
    body = {"import_id": import_id, "roles": IMPORT_ROLES, "wind_speed": 12, **change}
    res = client.post("/api/runs/import", json=body)
    assert res.status_code == status, res.text
    assert fragment in res.json()["detail"]
    assert not submitted


def test_mesh_inspect_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    seen = {}

    def fake_inspect(upload, case, unit, filename):
        seen.update(upload=upload.read_bytes(), unit=unit, filename=filename)
        return {"filename": filename, "format": "gmsh", "cells": 99, "patches": []}

    monkeypatch.setattr(main.meshimport, "inspect_mesh", fake_inspect)
    res = client.post("/api/mesh/inspect", files={"mesh": ("wing.msh", b"$MeshFormat", "text/plain")},
                      data={"unit": "mm"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert seen == {"upload": b"$MeshFormat", "unit": "mm", "filename": "wing.msh"}
    assert (main.IMPORT_DIR / body["id"] / "import.json").exists()
    assert not any((main.IMPORT_DIR / body["id"]).glob("upload*"))  # upload discarded


def test_mesh_inspect_reports_conversion_errors(monkeypatch):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")

    def boom(*a):
        raise main.meshimport.MeshImportError("Gmsh format 4.1 isn't supported")

    before = set(main.IMPORT_DIR.iterdir()) if main.IMPORT_DIR.exists() else set()
    monkeypatch.setattr(main.meshimport, "inspect_mesh", boom)
    res = client.post("/api/mesh/inspect", files={"mesh": ("wing.msh", b"$MeshFormat", "text/plain")})
    assert res.status_code == 422 and "4.1" in res.json()["detail"]
    assert set(main.IMPORT_DIR.iterdir()) == before  # nothing left behind
    assert client.post("/api/mesh/inspect", files={"mesh": ("w.msh", b"x", "text/plain")},
                       data={"unit": "furlong"}).status_code == 422


def test_stl_runs_cannot_claim_an_imported_mesh(monkeypatch):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg, group_id=None, mesh_src=None: submitted.append(cfg) or "x")
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse",
                     "mesh_import": {"roles": {}}, "mesh_from": "someone-else"})
    assert res.status_code == 201, res.text
    assert "mesh_import" not in submitted[0] and "mesh_from" not in submitted[0]


def test_rerun_of_an_imported_run_copies_its_mesh(finished_run, monkeypatch):
    cfg = dict(QUAD_CFG, props=None, mesh_import={"roles": IMPORT_ROLES, "format": "gmsh"})
    cfg.pop("props")
    rid = finished_run(cfg)
    rd = main.DATA_DIR / rid
    (rd / "mesh_import" / "constant" / "polyMesh").mkdir(parents=True)
    (rd / "mesh_import" / "constant" / "polyMesh" / "owner").write_text("mesh")
    calls = []
    monkeypatch.setattr(main, "_submit_run", lambda stl, c, group_id=None, mesh_src=None:
                        calls.append((c, mesh_src)) or "rerun-id")
    assert client.post(f"/api/runs/{rid}/rerun").status_code == 201
    c, mesh_src = calls[0]
    assert mesh_src == rd / "mesh_import" / "constant" / "polyMesh" and c["mesh_import"]
    (rd / "mesh_import" / "constant" / "polyMesh" / "owner").unlink()
    assert client.post(f"/api/runs/{rid}/rerun").status_code == 410


# --- v8.5 prism layers ------------------------------------------------------

@pytest.mark.parametrize("layers, fragment", [
    ("three", "layers must be an object"),
    ({"nLayers": 3}, "layers must be an object"),
    ({"count": 20}, "layers.count"),
    ({"count": -1}, "layers.count"),
    ({"expansion": 3.0}, "layers.expansion"),
    ({"final_thickness": 0}, "layers.final_thickness"),
    ({"ground": "yes"}, "layers.ground must be true or false"),
    ({"ground": True}, "requires ground_plane"),
])
def test_layer_validation(monkeypatch, layers, fragment):
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse",
                     "layers": layers})
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]


def test_layers_are_stored_on_the_run(monkeypatch):
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam", lambda: "/opt/homebrew/bin/openfoam")
    monkeypatch.setattr(main.runner, "submit", lambda *a, **k: None)
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse",
                     "ground_plane": True,
                     "layers": {"count": 6, "expansion": 1.15, "ground": True}})
    assert res.status_code == 201, res.text
    # submit is stubbed, so the run never reaches the runner's state; read the
    # config the API persisted for it instead.
    rd = main.DATA_DIR / res.json()["id"]
    cfg = _json.loads((rd / "config.json").read_text())
    assert cfg["layers"] == {"count": 6, "expansion": 1.15, "ground": True}


# --- flow model API ---------------------------------------------------------

@pytest.mark.parametrize("cfg_extra, fragment", [
    ({"flow_model": "hypersonic"}, "flow_model must be one of"),
    ({"flow_model": "supersonic", "wind_speed": 340}, "Mach 1.05 or more"),
    ({"wind_speed": 680}, "for flow_model 'incompressible'"),
    ({"flow_model": "transonic", "temperature": 5},
     "temperature must be a number"),
])
def test_flow_model_validation(monkeypatch, cfg_extra, fragment):
    monkeypatch.setattr(main.foamenv, "find_openfoam",
                        lambda: "/opt/homebrew/bin/openfoam")
    res = _post_run({"unit": "mm", "wind_speed": 15, "quality": "coarse",
                     **cfg_extra})
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]


def test_props_are_refused_with_a_compressible_model(monkeypatch):
    monkeypatch.setattr(main.foamenv, "find_openfoam",
                        lambda: "/opt/homebrew/bin/openfoam")
    res = _post_run({"unit": "mm", "wind_speed": 500, "quality": "coarse",
                     "flow_model": "transonic", "props": PROPS})
    assert res.status_code == 422
    assert "constant density" in res.json()["detail"]


# -- v10 case_matrix test program ----------------------------------------------

def _post_matrix(monkeypatch, cfg):
    """Post a run config, capturing (never queuing) the fanned-out children."""
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam",
                        lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg, group_id=None: submitted.append(cfg)
                        or f"m{len(submitted)}")
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": _json.dumps(cfg)})
    return res, submitted


@pytest.mark.parametrize("extra, fragment", [
    ({"case_matrix": {}}, "at least one sweep dim"),
    ({"case_matrix": [0, 15]}, "case_matrix must be an object"),
    ({"case_matrix": {"alpha_deg": []}}, "alpha_deg must be a non-empty list"),
    ({"case_matrix": {"alpha_deg": "0,15"}}, "alpha_deg must be a non-empty list"),
    ({"case_matrix": {"alpha_deg": [0, float("nan")]}},
     "alpha_deg must be a non-empty list"),
    ({"case_matrix": {"foo_deg": [0]}}, "unknown dims"),
    ({"case_matrix": {"alpha_deg": [0, 15]}, "yaw_sweep": [0, 30]},
     "cannot be combined"),
    ({"case_matrix": {"alpha_deg": [0, 15]}, "pitch_sweep": [0, 30]},
     "cannot be combined"),
    ({"case_matrix": {"alpha_deg": [0, 15]}, "mesh_sweep": True},
     "cannot be combined"),
    ({"case_matrix": {"alpha_deg": [0, 15]}, "trim": {"weight_g": 700}},
     "cannot be combined"),
    ({"case_matrix": {"alpha_deg": [0] * 30, "beta_deg": [0] * 30}},
     f"over the {main.matrix_program.MAX_PROGRAM_MEMBERS}-run cap"),
])
def test_case_matrix_validation(monkeypatch, extra, fragment):
    cfg = {"unit": "mm", "wind_speed": 15, "quality": "coarse", **extra}
    if "trim" in extra:
        cfg["props"] = [{"center": [0, 0, 0], "diameter": 127, "thrust_g": 200}]
    res, submitted = _post_matrix(monkeypatch, cfg)
    assert res.status_code == 422, res.text
    assert fragment in res.json()["detail"]
    assert not submitted


def test_case_matrix_fans_out_one_run_per_combination(monkeypatch):
    cfg = {"name": "tail", "unit": "mm", "wind_speed": 15, "quality": "coarse",
           "case_matrix": {"alpha_deg": [0, 5], "beta_deg": [-2, 0, 4],
                           "delta_e_deg": [-8, 0]}}
    res, submitted = _post_matrix(monkeypatch, cfg)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "matrix"
    assert len(body["group_id"]) == 32 and len(body["ids"]) == 12
    assert len(submitted) == 12
    # alpha is the slowest dim, delta_e the fastest; alpha -> pitch, beta -> yaw,
    # the deflection passes through verbatim.
    assert submitted[0]["pitch_deg"] == 0.0
    assert submitted[0]["yaw_deg"] == -2.0
    assert submitted[0]["delta_e_deg"] == -8.0
    assert submitted[1]["delta_e_deg"] == 0.0
    assert submitted[6]["pitch_deg"] == 5.0
    assert all(c["sweep_param"] == "matrix" for c in submitted)
    assert all("case_matrix" in c for c in submitted)
    assert submitted[0]["name"] == "tail a0 b-2 e-8"
    assert submitted[1]["name"] == "tail a0 b-2 e0"
    assert submitted[12 - 1]["name"] == "tail a5 b4 e0"


def test_case_matrix_group_reports_metadata_sorted(monkeypatch):
    import json as _json
    monkeypatch.setattr(main.foamenv, "find_openfoam",
                        lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg, group_id=None: submitted.append(cfg)
                        or f"m{len(submitted)}")
    cfg = {"name": "tail", "unit": "mm", "wind_speed": 15, "quality": "coarse",
           "case_matrix": {"alpha_deg": [0, 5], "beta_deg": [-2, 0, 4],
                           "delta_e_deg": [-8, 0]}}
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": _json.dumps(cfg)})
    assert res.status_code == 201, res.text
    gid = res.json()["group_id"]
    made = []
    for i, child in enumerate(submitted):  # group endpoint reads live state
        rid = f"m{i}"
        main.runner.states[rid] = {
            "id": rid, "name": child["name"], "status": "done", "progress": 1.0,
            "message": "Done", "created_at": float(i), "config": child,
            "group_id": gid, "model": None, "mesh_cells": 1000,
            "result": {"cd": 0.01 * i, "drag_N": 0.01 * i}, "error": None,
            "log": None}
        made.append(rid)
    try:
        g = client.get(f"/api/groups/{gid}").json()
        assert g["kind"] == "matrix" and g["name"] == "tail"
        assert g["param"] == "matrix"
        assert len(g["runs"]) == 12

        def _k(v):  # absent dims (None) sort first
            return float("-inf") if v is None else float(v)

        keys = [(_k(r["alpha_deg"]), _k(r["beta_deg"]), _k(r["delta_e_deg"]),
                 _k(r["delta_a_deg"]), _k(r["delta_r_deg"])) for r in g["runs"]]
        assert keys == sorted(keys)
        first = g["runs"][0]
        assert (first["alpha_deg"], first["beta_deg"], first["delta_e_deg"]) \
            == (0, -2, -8)
        assert first["delta_a_deg"] is None and first["delta_r_deg"] is None
    finally:
        for rid in made:
            main.runner.states.pop(rid, None)


def _matrix_children(monkeypatch):
    """Post-matrix capture helper: records (cfg, group_id) per fan-out, never
    queuing a real solve. The ids returned are m1, m2, ... like _post_matrix."""
    monkeypatch.setattr(main.foamenv, "find_openfoam",
                        lambda: "/opt/homebrew/bin/openfoam")
    submitted = []
    monkeypatch.setattr(main, "_submit_run",
                        lambda data, cfg, group_id=None: submitted.append(
                            {"cfg": cfg, "group_id": group_id})
                        or f"m{len(submitted)}")
    return submitted


def _seed_matrix_states(submitted):
    """Write each captured child into the in-memory runner store as a done run,
    so the group/program endpoints can read the members."""
    made = []
    for i, item in enumerate(submitted):
        child = item["cfg"]
        rid = f"m{i}"
        main.runner.states[rid] = {
            "id": rid, "name": child["name"], "status": "done", "progress": 1.0,
            "message": "Done", "created_at": float(i), "config": child,
            "group_id": item["group_id"], "model": None, "mesh_cells": 1000,
            "result": {"cd": 0.01 * (i % 7), "drag_N": 0.01 * (i % 7)},
            "error": None, "log": None}
        made.append(rid)
    return made


def test_case_matrix_program_batches_aggregate(monkeypatch):
    """A >200-member program splits into ≤200-member batches under one
    program_id, and GET /api/programs/{pid} joins them into one
    wind-tunnel-ordered grid; the per-batch group reports its part marker."""
    import json as _json
    submitted = _matrix_children(monkeypatch)
    cfg = {"name": "big", "unit": "mm", "wind_speed": 15, "quality": "coarse",
           "case_matrix": {"alpha_deg": list(range(19)),
                           "beta_deg": list(range(12))}}  # 19 × 12 = 228 = 200 + 28
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": _json.dumps(cfg)})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "matrix"
    assert len(body["program_id"]) == 32
    assert body["total"] == 228 and body["batch_count"] == 2
    assert len(body["ids"]) == 228 and len(body["batches"]) == 2
    assert len(submitted) == 228
    per_batch = sorted(
        (b["batch_index"], sum(1 for item in submitted
                               if item["cfg"]["batch_index"] == b["batch_index"]))
        for b in body["batches"])
    assert per_batch == [(0, 200), (1, 28)]
    assert len({item["group_id"] for item in submitted}) == 2
    assert all(item["cfg"]["program_id"] == body["program_id"]
               for item in submitted)
    assert all(item["cfg"]["batch_count"] == 2 for item in submitted)

    made = _seed_matrix_states(submitted)
    try:
        pid = body["program_id"]
        g = client.get(f"/api/programs/{pid}").json()
        assert g["program_id"] == pid and g["kind"] == "matrix"
        assert g["name"] == "big"
        assert g["batch_count"] == 2 and g["total"] == 228
        assert len(g["runs"]) == 228
        assert {(b["batch_index"], b["total"], b["done"])
                for b in g["batches"]} == {(0, 200, 200), (1, 28, 28)}
        # alpha slowest, beta fastest — the grid stays contiguous across batches.
        keys = [(r["alpha_deg"], r["beta_deg"]) for r in g["runs"]]
        assert keys == sorted(keys)
        assert keys[0] == (0, 0) and keys[-1] == (18, 11)
        # The per-batch group endpoint carries the program markers and the part
        # suffix, so history cards can tell " · part 1/2" apart.
        grp = client.get(f"/api/groups/{body['batches'][0]['group_id']}").json()
        assert grp["program_id"] == pid and grp["batch_index"] == 0
        assert grp["batch_count"] == 2
        assert grp["name"] == "big · part 1/2"
        assert len(grp["runs"]) == 200
        assert client.get("/api/programs/nope").status_code == 404
    finally:
        for rid in made:
            main.runner.states.pop(rid, None)


def test_case_matrix_single_batch_backward_compatible(monkeypatch):
    """A ≤200-member program keeps its old response shape (group_id/ids/kind)
    while adding program_id and a one-element batches list — the aggregate
    endpoint still works for it."""
    import json as _json
    submitted = _matrix_children(monkeypatch)
    cfg = {"name": "tail", "unit": "mm", "wind_speed": 15, "quality": "coarse",
           "case_matrix": {"alpha_deg": [0, 5], "beta_deg": [-2, 0, 4],
                           "delta_e_deg": [-8, 0]}}  # 12 members, one batch
    with open(SPHERE, "rb") as fh:
        res = client.post("/api/runs", files={"stl": ("s.stl", fh, "model/stl")},
                          data={"config": _json.dumps(cfg)})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "matrix"
    assert len(body["group_id"]) == 32
    assert len(body["program_id"]) == 32
    assert body["total"] == 12 and body["batch_count"] == 1
    assert len(body["batches"]) == 1 and body["batches"][0]["batch_index"] == 0
    assert len(body["ids"]) == 12
    assert all(item["cfg"]["program_id"] == body["program_id"]
               for item in submitted)
    assert all(item["cfg"]["batch_index"] == 0 and item["cfg"]["batch_count"] == 1
               for item in submitted)

    made = _seed_matrix_states(submitted)
    try:
        g = client.get(f"/api/programs/{body['program_id']}").json()
        assert g["kind"] == "matrix" and g["name"] == "tail"
        assert g["batch_count"] == 1 and g["total"] == 12
        assert len(g["batches"]) == 1
        assert len(g["runs"]) == 12
    finally:
        for rid in made:
            main.runner.states.pop(rid, None)


