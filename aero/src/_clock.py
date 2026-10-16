"""Deterministic generation timestamp.

Plan §8 requires *same inputs -> reproducible XML* for the aero toolchain.
A wall-clock "now" stamp in generated artifacts (metadata.json, aero_tables,
aerodynamics.xml) would break that: identical runs would produce different
bytes.  Resolution order:

  1. SOURCE_DATE_EPOCH  (reproducible-builds convention; value is a unix
     epoch integer, or an ISO-8601 string) -> deterministic across runs.
  2. current UTC time (traceability metadata when nothing is pinned).

Tests test_reproducibility.py pin SOURCE_DATE_EPOCH and assert the emitted
timestamp equals the derived value.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


def _parse_epoch(value: str) -> datetime:
    value = value.strip()
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except ValueError:
        pass
    # tolerate an ISO-8601 string for readability
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        # a naive ISO string is treated as UTC so the emitted timestamp always
        # carries an explicit offset ("+00:00")
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    raise ValueError(
        "SOURCE_DATE_EPOCH must be a unix epoch integer or ISO-8601 string, "
        f"got: {value!r}")


def generated_utc() -> str:
    """ISO-8601 UTC timestamp pinned by SOURCE_DATE_EPOCH when set."""
    env = os.environ.get("SOURCE_DATE_EPOCH")
    if env is None or not env.strip():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return _parse_epoch(env).isoformat(timespec="seconds")
