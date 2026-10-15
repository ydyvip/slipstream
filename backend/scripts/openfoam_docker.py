#!/usr/bin/env python3
"""Docker-backed `openfoam` wrapper for the Slipstream backend on Windows.

The backend launches every OpenFOAM stage as a shell passed to an `openfoam`
wrapper executable:

    openfoam -c "cd '<case_dir>' && <foam cmd> > '<log>' 2>&1"

(see runner._foam, meshimport.run_foam). ondemand uses double quotes:
    cd "<case_dir>" && ...

On this machine OpenFOAM lives in a Docker image (opencfd/openfoam-default),
so this wrapper translates that call into a `docker run`:

  * mounts the run's directory (the parent of the case dir) at /run
  * rewrites the command's Windows paths to the container mount paths
  * runs the shell under `bash -lc` so the image's OpenFOAM environment is
    sourced (this is how the image exposes its preinstalled OpenFOAM)
  * OpenMPI refuses to launch as root, which is the image's default user:
    any `mpirun` in the command gets `--allow-run-as-root`

Environment:
  SLIPSTREAM_DOCKER_IMAGE   image/tag to run (default opencfd/openfoam-default:latest)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

IMAGE = os.environ.get("SLIPSTREAM_DOCKER_IMAGE", "opencfd/openfoam-default:latest")
MOUNT = "/run"


def _rewrite_case(shell: str, rd_win: str) -> str:
    """Rewrite a Windows run-dir shell into container-path form (`/run/...`)."""
    rd_back = rd_win.replace("/", "\\").rstrip("\\")
    rd_forw = rd_back.replace("\\", "/")
    out = shell.replace(rd_back, MOUNT)
    if rd_forw != rd_back:
        out = out.replace(rd_forw, MOUNT)
    out = out.replace("\\", "/")
    # The image runs as root; OpenMPI refuses without this flag.
    out = re.sub(r"(?<![A-Za-z0-9_])mpirun\b",
                 "mpirun --allow-run-as-root", out)
    return out


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "-c":
        shell = args[1]
    else:
        print(f"[openfoam-docker] unexpected invocation: {args!r}", file=sys.stderr)
        return 2

    # Accept both `cd '...'` and `cd "..."` (ondemand.py uses double quotes).
    m = re.match(r"^\s*cd\s+(['\"])([^'\"]+)\1\s*&&\s*(.*)$", shell)
    if not m:
        print(f"[openfoam-docker] cannot parse shell: {shell!r}", file=sys.stderr)
        return 2
    workdir_win = m.group(2)
    rd_win = os.path.dirname(workdir_win) or workdir_win
    inner = _rewrite_case(f"cd '{workdir_win}' && {m.group(3)}", rd_win)

    cmdline = [
        "docker", "run", "--rm",
        "-v", f"{rd_win}:{MOUNT}",
        "-w", MOUNT,
        IMAGE,
        "bash", "-lc", inner,
    ]
    try:
        proc = subprocess.run(cmdline)
        return proc.returncode
    except FileNotFoundError:
        print("[openfoam-docker] `docker` not found on PATH", file=sys.stderr)
        return 2
    except OSError as exc:  # noqa: BLE001
        print(f"[openfoam-docker] docker run failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
