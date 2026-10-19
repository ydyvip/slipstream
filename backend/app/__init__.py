"""Slipstream backend package.

Loading `.env` happens here, before any submodule reads an environment
variable, so a `backend/.env` (or repo-root `.env`) configuration file works
for every `SLIPSTREAM_*` key — including ones read at import time (e.g.
`SLIPSTREAM_MAX_PROGRAM_MEMBERS` in `matrix.py`). Real environment variables
are never overridden.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is declared in requirements.txt; degrade gracefully
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - environment is always installed
    _load_dotenv = None


def _env_candidates() -> list[Path]:
    here = Path(__file__).resolve().parent  # backend/app/
    return [Path.cwd(), here.parent, here.parent.parent]


def load_dotenv() -> Path | None:
    """Load the first `.env` found (CWD → backend/ → repo root) into
    os.environ without overriding variables already set in the process."""
    if _load_dotenv is None:
        return None
    for d in _env_candidates():
        p = d / ".env"
        if p.is_file():
            _load_dotenv(p)
            return p
    return None


_ENV_FILE = load_dotenv()
