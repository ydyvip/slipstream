"""Launch the Slipstream backend, network-accessible by default.

Reads `backend/.env` (or the repo-root `.env`) — the `app` package loads it
on import — for `SLIPSTREAM_HOST` / `SLIPSTREAM_PORT`. Defaults bind to
0.0.0.0 so other machines on your LAN can reach the API (and the built web
UI when `SLIPSTREAM_STATIC` is set). Set `SLIPSTREAM_HOST=127.0.0.1` to stay
local-only, or run the CLI variant instead:

    python run_server.py
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import os

import uvicorn

from app.main import app  # importing the package loads backend/.env first


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def main() -> None:
    host = os.environ.get("SLIPSTREAM_HOST", "0.0.0.0")
    port = _int_env("SLIPSTREAM_PORT", 8000)
    print(f"Slipstream backend: http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
