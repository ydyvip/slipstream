"""Run the real CH-3 CFD case matrix through Docker OpenFOAM -> aero/raw/.

This is the "backend-produced wind-tunnel output" driver: it replaces the
synthetic aero/raw/ sample data with genuinely converged OpenFOAM 2512 runs,
landing them in the exact layout the aero pipeline expects
(aero/raw/forceCoeffs/<id>/coefficient.dat + aero/raw/forces/<id>/forces.dat).

Pipeline per case (reuses the backend's pure-Python machinery):
    repair (once, cached) -> geometry.prepare_stl (alpha/beta attitude) ->
    foamcase.compute_params + generate_case -> copy model.stl into the case ->
    OpenFOAM stages in Docker (surfaceFeatureExtract -> blockMesh -> snappy
    parallel -> reconstructParMesh -> checkMesh -> simpleFoam parallel with
    auto-stop) -> synthesise forces.dat (v2512 splits force.dat/moment.dat
    into the single 4-vector-group file parse_forces expects) -> copy into aero/raw/.

Usage:
    python aero/scripts/run_real_cases.py --case ch3_a00_b00     # one case
    python aero/scripts/run_real_cases.py --all                  # whole matrix
    python aero/scripts/run_real_cases.py --quality medium       # mesh quality
    python aero/scripts/run_real_cases.py --repair-only          # just the STL
    python aero/scripts/run_real_cases.py --list                 # matrix ids
    python aero/scripts/run_real_cases.py --cleanup              # rm runs/

Environment:
    Uses Python 3.12+ (numpy/scipy/trimesh/skimage) — the same py312 env
    that has the backend dependencies. Requires Docker with the
    opencfd/openfoam-default:latest image (OpenFOAM 2512).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

# --------------------------------------------------------------------------
# Paths & imports
# --------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent          # repo root
AERO = ROOT / "aero"
BACKEND = ROOT / "backend"
RUNS = AERO / "runs"                                          # gitignored workspace
REPAIRED_CACHE = RUNS / "repair" / "ch3_repaired.stl"

RAW_FORCECOEFS = AERO / "raw" / "forceCoeffs"
RAW_FORCES = AERO / "raw" / "forces"

STL_SRC = ROOT / "assets" / "ch-3" / "CH3_00_assembly_all.stl"

for p in (str(BACKEND), str(AERO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app import foamcase, geometry, repair            # noqa: E402
from src.geometry_ref import (                        # noqa: E402
    NU_M2S, REF_AREA_CM2, RHO_KGM3, V_INF_MPS,
    pitch_deg, yaw_deg,
)

# --------------------------------------------------------------------------
# Docker / OpenFOAM
# --------------------------------------------------------------------------

IMAGE = "opencfd/openfoam-default:latest"
BASH_RC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"
NPROCS = foamcase.NPROCS          # 6, matches decomposeParDict ${nprocs}

# Copy of backend runner auto-stop policy (self-contained, no runner import).
AUTOSTOP_WINDOW = 60
AUTOSTOP_ABS_TOL = 0.002
AUTOSTOP_REL_TOL = 0.005
AUTOSTOP_MIN_FRAC = 0.4


def _docker() -> str:
    for cand in (
        shutil.which("docker"),
        r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
        "/usr/bin/docker",
    ):
        if cand and Path(cand).exists():
            return cand
    raise RuntimeError("docker not found - install Docker Desktop (OpenFOAM 2512 image)")


def _vec3(v) -> str:
    return f"({v[0]:.9g} {v[1]:.9g} {v[2]:.9g})"


# --------------------------------------------------------------------------
# matrix
# --------------------------------------------------------------------------

def load_matrix() -> list[dict]:
    cfg = yaml.safe_load((AERO / "config" / "cfd_case_matrix.yaml").read_text(encoding="utf-8"))
    return cfg["cases"]


def case_lookup(cid: str) -> dict:
    for c in load_matrix():
        if c["id"] == cid:
            return c
    raise KeyError(f"no case {cid!r} in cfd_case_matrix.yaml")


# --------------------------------------------------------------------------
# repair
# --------------------------------------------------------------------------

def ensure_repaired() -> Path:
    """Repair the CH-3 assembly STL once, cached under aero/runs/ (gitignored).
    snappyHexMesh needs a watertight manifold surface; the CAD assembly has
    non-manifold edges / 9 bodies, so repair is mandatory."""
    if REPAIRED_CACHE.exists():
        print(f"[repair] cache hit: {REPAIRED_CACHE}")
        return REPAIRED_CACHE
    if not STL_SRC.exists():
        raise RuntimeError(f"source STL not found: {STL_SRC}")
    REPAIRED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    print(f"[repair] rebuilding {STL_SRC.name} -> {REPAIRED_CACHE}")
    rep = repair.repair_stl(STL_SRC, REPAIRED_CACHE)
    print(f"[repair] {rep}")
    if not rep.get("watertight"):
        raise RuntimeError("repaired STL is not watertight - cannot mesh")
    return REPAIRED_CACHE


# --------------------------------------------------------------------------
# OpenFOAM stages via Docker
# --------------------------------------------------------------------------

def run_stage(case: Path, cmd: str, log_name: str, check: bool = True,
              timeout: int | None = None) -> subprocess.CompletedProcess:
    """Run one OpenFOAM stage inside the container, working in the mounted
    case dir. Log goes to case/<log_name> on the host."""
    log_path = case / log_name
    docker = _docker()
    shell = (f"source {BASH_RC} && cd /case && {cmd} > {log_name} 2>&1")
    proc = subprocess.run(
        [docker, "run", "--rm",
         "--shm-size=2g",
         "-v", f"{case.resolve()}:/case",
         "-w", "/case",
         IMAGE, "bash", "-lc", shell],
        capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        tail = _tail(log_path and log_path.read_text(errors="replace"))
        raise RuntimeError(
            f"{cmd.split()[0]} failed (exit {proc.returncode}). "
            f"Log tail:\n{tail}")
    return proc


def _tail(text: str, n: int = 30) -> str:
    return "\n".join(text.splitlines()[-n:])


def _converged(cd: list[float], it: int, iterations: int) -> bool:
    if it < AUTOSTOP_MIN_FRAC * iterations or len(cd) < AUTOSTOP_WINDOW:
        return False
    tail = cd[-AUTOSTOP_WINDOW:]
    mean = sum(tail) / len(tail)
    std = (sum((x - mean) ** 2 for x in tail) / len(tail)) ** 0.5
    if mean == 0:
        return std < AUTOSTOP_ABS_TOL
    return std < max(AUTOSTOP_ABS_TOL, AUTOSTOP_REL_TOL * abs(mean))


def _request_stop(case: Path) -> bool:
    """Flip stopAt -> writeNow in the runTimeModifiable controlDict so the
    mounted solver writes the current time and exits cleanly (backend policy)."""
    path = case / "system" / "controlDict"
    try:
        text = path.read_text()
    except OSError:
        return False
    new = re.sub(r"^(\s*stopAt\s+)\w+\s*;", r"\1writeNow;", text,
                 count=1, flags=re.MULTILINE)
    if new == text and "writeNow" not in text:
        return False
    path.write_text(new)
    return True


def _read_history(case: Path) -> dict:
    """Read host-side coefficient.dat + solverInfo (post.read_history)."""
    from app import post
    return post.read_history(case)


def _run_solve(case: Path, iterations: int, u0: float, timeout: int | None) -> None:
    """simpleFoam in parallel with the backend's convergence auto-stop."""
    n = NPROCS
    docker = _docker()
    shell = (f"source {BASH_RC} && cd /case && "
             f"export OMPI_ALLOW_RUN_AS_ROOT=1 "
             f"OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 && "
             f"decomposePar -force > log.decomposePar 2>&1 && "
             f"mpirun -np {n} simpleFoam -parallel > log.simpleFoam 2>&1")
    proc = subprocess.Popen(
        [docker, "run", "--rm",
         "--shm-size=2g",
         "-v", f"{case.resolve()}:/case",
         "-w", "/case",
         IMAGE, "bash", "-lc", shell],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stop_requested = False
    try:
        while proc.poll() is None:
            time.sleep(10)
            try:
                hist = _read_history(case)
            except Exception:
                continue
            iters = hist.get("iters", [])
            cd = hist.get("cd", [])
            if not iters or not cd:
                continue
            it = int(iters[-1])
            if not stop_requested and _converged(cd, it, iterations):
                stop_requested = _request_stop(case)
                print(f"[solve] converged -> stopAt=writeNow at iter {it}")
            print(f"[solve] iter {it}/{iterations} Cd={cd[-1]:.4f}", flush=True)
    except KeyboardInterrupt:
        proc.kill()
        raise
    rc = proc.wait(timeout=timeout)
    if rc != 0:
        # no history at all = solver never really started
        if not _read_history(case).get("iters"):
            raise RuntimeError(f"simpleFoam failed to start (exit {rc}). "
                               f"Log tail:\n{_tail((case/'log.simpleFoam').read_text(errors='replace'))}")
        raise RuntimeError(f"simpleFoam failed mid-run (exit {rc}). "
                           f"Log tail:\n{_tail((case/'log.simpleFoam').read_text(errors='replace'))}")


def _mesh(case: Path) -> None:
    """Mesh stages (backend order/retry policy)."""
    root_export = "export OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 && "

    def st(cmd, log, check=True):
        run_stage(case, cmd, log, check=check)

    st("surfaceFeatureExtract", "log.surfaceFeatureExtract")
    st("blockMesh", "log.blockMesh")
    n = NPROCS
    try:
        st("decomposePar -force", "log.decomposePar.mesh")
        rc = run_stage(case, root_export +
                       f"mpirun -np {n} snappyHexMesh -parallel -overwrite",
                       "log.snappyHexMesh", check=False)
        if rc.returncode != 0:
            txt = (case / "log.snappyHexMesh").read_text(errors="replace")
            if "Reading refinement surfaces." in txt:
                print("[mesh] layer addition failed - retrying without layers")
                foamcase.set_add_layers(case, False)
                st("decomposePar -force", "log.decomposePar.mesh")
                st(root_export +
                   f"mpirun -np {n} snappyHexMesh -parallel -overwrite",
                   "log.snappyHexMesh")
            else:
                raise RuntimeError(
                    f"snappyHexMesh failed: {_tail(txt)}")
        st("reconstructParMesh -constant", "log.reconstructParMesh")
        foamcase.free_processor_dirs(case)
    except RuntimeError:
        # MPI never got started -> mesh serial
        print("[mesh] parallel meshing failed - trying serial")
        foamcase.free_processor_dirs(case)
        rc = run_stage(case, "snappyHexMesh -overwrite", "log.snappyHexMesh",
                       check=False)
        if rc.returncode != 0:
            txt = (case / "log.snappyHexMesh").read_text(errors="replace")
            if "Reading refinement surfaces." in txt:
                print("[mesh] layer addition failed - retrying without layers")
                foamcase.set_add_layers(case, False)
                st("snappyHexMesh -overwrite", "log.snappyHexMesh")
            else:
                raise RuntimeError(f"snappyHexMesh (serial) failed: {_tail(txt)}")
    st("checkMesh", "log.checkMesh", check=False)


# --------------------------------------------------------------------------
# results -> aero/raw
# --------------------------------------------------------------------------

def _latest_dat(case: Path, fo_name: str, fname: str) -> Path:
    base = case / "postProcessing" / fo_name
    hits = sorted(base.glob(f"*/{fname}")) if base.exists() else []
    return hits[-1] if hits else base / "0" / fname


def _synthesise_forces(case: Path, out_path: Path) -> dict:
    """v2512 writes force.dat + moment.dat as SCALAR columns
    (Time total_x..z pressure_x..z viscous_x..z). parse_forces instead needs
    one file with 4 vector groups per row: [Fp, Fv, Mp, Mv]. Merge the two on
    the converged (last finite) time row."""
    from app import post

    f_dat = _latest_dat(case, "forces1", "force.dat")
    m_dat = _latest_dat(case, "forces1", "moment.dat")
    if not f_dat.exists() and not m_dat.exists():
        raise RuntimeError("forces1 function object produced no force.dat/moment.dat")
    fcols = post.parse_dat(f_dat) if f_dat.exists() else {}
    mcols = post.parse_dat(m_dat) if m_dat.exists() else {}

    NEEDED = ["total_x", "total_y", "total_z",
              "pressure_x", "pressure_y", "pressure_z",
              "viscous_x", "viscous_y", "viscous_z"]
    NEEDED_SET = set(NEEDED)

    def last(cls: dict[str, np.ndarray]) -> dict | None:
        if not cls or "Time" not in cls or not NEEDED_SET.issubset(cls):
            return None
        n = len(cls["Time"])
        for i in range(n - 1, -1, -1):
            if all(np.isfinite(cls[k][i]) for k in NEEDED):
                return {k: float(cls[k][i]) for k in cls}
        return None

    frow = last(fcols)
    mrow = last(mcols)
    if frow is None or mrow is None or frow["Time"] != mrow["Time"]:
        raise RuntimeError(f"no aligned finite force/moment rows "
                           f"(f={frow and frow.get('Time')}, m={mrow and mrow.get('Time')})")

    fp = (frow["pressure_x"], frow["pressure_y"], frow["pressure_z"])
    fv = (frow["viscous_x"], frow["viscous_y"], frow["viscous_z"])
    mp = (mrow["pressure_x"], mrow["pressure_y"], mrow["pressure_z"])
    mv = (mrow["viscous_x"], mrow["viscous_y"], mrow["viscous_z"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "# Time  forces(pressure,viscous)  moment(pressure,viscous)\n"
        + f"{frow['Time']:g}   {_vec3(fp)} {_vec3(fv)} "
        + f"{_vec3(mp)} {_vec3(mv)}\n",
        encoding="utf-8")
    return {**{f"F{x}": fp[i] + fv[i] for i, x in enumerate("xyz")},
            **{f"M{x}": mp[i] + mv[i] for i, x in enumerate("xyz")}}


def _copy_results(case: Path, cid: str) -> dict:
    """Copy coefficient.dat + synthesise forces.dat into aero/raw/."""
    coeff_src = _latest_dat(case, "forceCoeffs1", "coefficient.dat")
    forces_dst = RAW_FORCES / cid / "forces.dat"
    coeff_dst = RAW_FORCECOEFS / cid / "coefficient.dat"

    if coeff_src.exists():
        coeff_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(coeff_src, coeff_dst)
    else:
        raise RuntimeError("forceCoeffs coefficient.dat missing")

    fvec = _synthesise_forces(case, forces_dst)

    return {
        "forces": fvec,
        "coefficient": coeff_dst,
        "force_file": forces_dst,
    }


# --------------------------------------------------------------------------
# case driver
# --------------------------------------------------------------------------

def run_case(cid: str, quality: str = "coarse", timeout: int | None = None,
             skip_mesh: bool = False) -> dict:
    case_data = case_lookup(cid)
    alpha = float(case_data.get("alpha_deg", 0.0))
    beta = float(case_data.get("beta_deg", 0.0))

    repaired = ensure_repaired()
    run_dir = RUNS / cid
    case = run_dir / "case"
    run_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()

    # ---- prepare (backend geometry.prepare_stl) --------------------------
    prepared = run_dir / "model_prepared.stl"
    print(f"[{cid}] alpha={alpha:+g} beta={beta:+g} quality={quality}")
    model = geometry.prepare_stl(
        str(repaired), "mm", yaw_deg(beta), str(prepared),
        pitch_deg=pitch_deg(alpha))

    config = {
        "unit": "mm",
        "wind_speed": V_INF_MPS,
        "rho": RHO_KGM3,
        "nu": NU_M2S,
        "quality": quality,
        "flow_model": "incompressible",
        "symmetry": False,
        "ground_plane": False,
        "ref_area_cm2": REF_AREA_CM2,
    }
    params = foamcase.compute_params(model, config)
    iterations = params.pop("iterations")
    iterations_val = iterations

    has_mesh = (case / "constant" / "polyMesh" / "points").exists()
    if skip_mesh and has_mesh and (case / "0" / "U").exists():
        print(f"[{cid}] skipping case regeneration + meshing (reusing existing case)")
    else:
        print(f"[{cid}] generating case (L={model['bbox_m'][1][0]-model['bbox_m'][0][0]:.2f} m, "
              f"S={params['aref']} m^2, cells<={params['maxGlobalCells']})")
        foamcase.generate_case(case, params)
        tri_dir = case / "constant" / "triSurface"
        tri_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(prepared, tri_dir / "model.stl")

    # ---- mesh + solve -----------------------------------------------------
    if skip_mesh and (case / "constant" / "polyMesh" / "points").exists():
        print(f"[{cid}] skipping mesh (existing constant/polyMesh)")
    else:
        _mesh(case)
    print(f"[{cid}] mesh ready -> solving ({iterations_val} iterations)")
    _run_solve(case, iterations_val, float(config["wind_speed"]), timeout)

    run_stage(case, "reconstructPar -latestTime", "log.reconstructPar", check=False)
    foamcase.free_processor_dirs(case)

    # ---- results -> aero/raw ----------------------------------------------
    res = _copy_results(case, cid)
    res["iterations"] = int(iterations_val)
    res["runtime_s"] = round(time.time() - t0, 1)
    res["model"] = {k: model[k] for k in
                    ("bbox_m", "frontal_area_m2", "triangles", "symmetric")}
    print(f"[{cid}] DONE in {res['runtime_s']}s - F={res['forces']['Fx']:.1f},"
          f"{res['forces']['Fy']:.1f},{res['forces']['Fz']:.1f} N "
          f"M={res['forces']['Mx']:.1f},{res['forces']['My']:.1f},"
          f"{res['forces']['Mz']:.1f} Nm")
    return res


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Real CH-3 CFD -> aero/raw driver")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--case", help="one case id (e.g. ch3_a00_b00)")
    g.add_argument("--all", action="store_true", help="the whole matrix")
    g.add_argument("--list", action="store_true", help="print case ids")
    g.add_argument("--repair-only", action="store_true", help="repair+cache STL only")
    g.add_argument("--cleanup", action="store_true", help="delete aero/runs/")
    ap.add_argument("--quality", default="coarse",
                    choices=tuple(foamcase.QUALITY))
    ap.add_argument("--skip-mesh", action="store_true",
                    help="reuse existing case dir + mesh (solve only)")
    ap.add_argument("--timeout", type=int, default=None,
                    help="per-case solve timeout in seconds")
    args = ap.parse_args()

    RUNS.mkdir(parents=True, exist_ok=True)

    if args.list:
        for c in load_matrix():
            print(c["id"], f"alpha={c.get('alpha_deg',0):+g} "
                           f"beta={c.get('beta_deg',0):+g}")
        return
    if args.cleanup:
        shutil.rmtree(RUNS, ignore_errors=True)
        print(f"removed {RUNS}")
        return
    if args.repair_only:
        p = ensure_repaired()
        print(f"repaired STL: {p}")
        return

    if args.case:
        cases = [case_lookup(args.case)]
    elif args.all:
        cases = load_matrix()
    else:
        ap.error("one of --case / --all / --repair-only / --cleanup is required")

    summary = {}
    for c in cases:
        try:
            summary[c["id"]] = run_case(c["id"], args.quality, args.timeout,
                                        skip_mesh=args.skip_mesh)
        except Exception as exc:  # noqa: BLE001
            print(f"[{c['id']}] FAILED: {exc}")
            summary[c["id"]] = {"error": str(exc)}

    (RUNS / "summary.json").write_text(json.dumps(
        summary, indent=1, default=str), encoding="utf-8")
    print("\n=== summary ===")
    for cid, s in summary.items():
        if "error" in s:
            print(f"  {cid}: ERROR {s['error']}")
        else:
            print(f"  {cid}: ok in {s['runtime_s']}s, "
                  f"iterations={s['iterations']}, "
                  f"F={s['forces']['Fx']:.1f}/{s['forces']['Fy']:.1f}/"
                  f"{s['forces']['Fz']:.1f} N")


if __name__ == "__main__":
    main()
