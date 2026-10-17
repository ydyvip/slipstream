# Slipstream backend

FastAPI backend that turns an uploaded STL into an OpenFOAM (simpleFoam, kOmegaSST)
external-aero analysis. See `docs/CONTRACT.md` at the repo root for the API contract.

## Requirements

- OpenFOAM, one of two ways:
  - **macOS** — **OpenFOAM v2606** via [openfoam.app](https://github.com/gerlero/openfoam-app);
    the `openfoam` wrapper must be at `/opt/homebrew/bin/openfoam` (or on `PATH`).
  - **Windows** — Docker Desktop with the `opencfd/openfoam-default:latest` image
    (OpenFOAM 2512); the backend runs every stage through
    `scripts/openfoam.cmd` (see [Windows + Docker](#windows--docker-docker-backed-openfoam)).
- Python 3.12+ (developed on 3.14).

## Setup

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# optional (~170 MB): smaller repaired models via topology-preserving decimation
.venv/bin/pip install pymeshlab
```

## Run

```sh
cd backend
.venv/bin/uvicorn app.main:app --port 8000
```

Launch from a shell where `/opt/homebrew/bin` is on `PATH` (the default on Homebrew
macOS) so the `openfoam` wrapper resolves; the backend calls it with an absolute
path when it exists, and falls back to `PATH` lookup otherwise. On Windows, point
`SLIPSTREAM_OPENFOAM` at `scripts\openfoam.cmd` first — see below.

## Windows + Docker (Docker-backed OpenFOAM)

On Windows there is no native OpenFOAM; the backend runs each OpenFOAM stage
inside the `opencfd/openfoam-default:latest` Docker image (OpenFOAM 2512). The
launcher chain is:

```
runner._foam  →  openfoam -c "<shell>"                 # one call per stage
              →  scripts\openfoam.cmd                  # found via SLIPSTREAM_OPENFOAM
              →  scripts\openfoam_docker.py            # translates the call
              →  docker run --rm -v <run_dir>:/run \
                     opencfd/openfoam-default:latest \
                     bash -lc "cd /run/... && <foam cmd> > log 2>&1"
```

Every stage (`blockMesh`, `snappyHexMesh`, `simpleFoam`, ...) is a short-lived
`docker run --rm` container, so there is no long-running OpenFOAM "service" to
keep alive. The only prerequisites are a running Docker engine and the image
pulled once per machine.

### One-time setup

1. Install and start Docker Desktop.
2. Pull the OpenFOAM image (~2 GB, one time):

   ```sh
   docker pull opencfd/openfoam-default:latest
   ```

3. Point the backend at the Windows wrapper. `foamenv.find_openfoam()` checks
   `SLIPSTREAM_OPENFOAM` first (absolute path preferred):

   ```powershell
   # PowerShell
   $env:SLIPSTREAM_OPENFOAM = "C:\path\to\slipstream\backend\scripts\openfoam.cmd"
   ```
   ```bat
   rem CMD
   set SLIPSTREAM_OPENFOAM=C:\path\to\slipstream\backend\scripts\openfoam.cmd
   ```

   (If unset, the backend also picks up `openfoam` on `PATH`, so adding
   `backend\scripts` to `PATH` works too.)

### Run

```powershell
cd backend
$env:SLIPSTREAM_OPENFOAM = "C:\path\to\slipstream\backend\scripts\openfoam.cmd"
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Confirm the wrapper resolved with `GET /api/health` — it returns
`"openfoam": "C:\\...\\scripts\\openfoam.cmd"`. Stage output lands in
`data\runs\<run_id>\case\` (`log.blockMesh`, `log.snappyHexMesh`,
`log.simpleFoam`, ...).

Notes:

- `scripts\openfoam.cmd` needs `python` on `PATH`; it forwards every argument to
  `scripts\openfoam_docker.py`.
- The wrapper mounts each run's directory at `/run`, rewrites Windows paths to
  container paths, sources the image's OpenFOAM environment via `bash -lc`, and
  injects `mpirun --allow-run-as-root` (the image runs as root, which OpenMPI
  otherwise refuses).
- Override the image/tag with the `SLIPSTREAM_DOCKER_IMAGE` environment variable
  (default `opencfd/openfoam-default:latest`); `aero/scripts/run_real_cases.py`
  is a standalone driver that runs the same image directly.

## Data layout

All run data lives on the filesystem under `backend/data/runs/<run_id>/`:

- `model.stl` — the original upload (unscaled), served by `GET /api/runs/{id}/stl`
- `config.json` — the posted config
- `state.json` — persisted run state; the server restores history from these on restart
  (runs that were mid-execution during a restart are marked `error`, queued runs re-queue)
- `case/` — the generated OpenFOAM case, including per-stage logs
  (`log.blockMesh`, `log.snappyHexMesh`, `log.simpleFoam`, ...)
- `viz_surface.json`, `viz_slice_y.json`, `viz_slice_z.json` — cached viz payloads

Runs execute one at a time (FIFO). Delete a run with `DELETE /api/runs/{id}`
(409 while it is executing).

## Smoke test

```sh
# with the server running; generates a sphere fixture if missing
.venv/bin/python tests/e2e_smoke.py
```

On Windows (PowerShell):

```powershell
.venv\Scripts\python tests\e2e_smoke.py
```
