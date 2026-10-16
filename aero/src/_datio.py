"""Shared reader for OpenFOAM function-object .dat files.

All post-processing .dat files produced by OpenFOAM function objects share one
shape:

  #  comment / header line(s)
  #  Time      Cd        Cl        ...
  5.0        0.1234    0.4567    ...

- every header line starts with '#'
- the LAST header line carries the column names
- data rows may be temporarily incomplete while the solver is still writing
  (a run in progress), and a trailing feed may be cut mid-line

This module returns the parsed header + data rows once and lets each parser
apply its own column semantics.  The parser is header-driven (reads the column
names instead of assuming index 0/1/2), per the plan's requirement that
"解析器必须读取输出文件头，不要写死列序".
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

# A parenthesised group whose contents include whitespace = a vector column
# (forces FO writes "(Fx Fy Fz)" style groups). Scalar columns like
# "Cd(f)" keep their parentheses.
_VEC_GROUP_RE = None  # placeholder; see _split_row


class DatReadError(ValueError):
    """Raised when a .dat file cannot be parsed as OpenFOAM post data."""


def _split_row(line: str) -> list[str]:
    """Tokenize one .dat row. Parenthesised vector groups are flattened:
    '(a b c)' becomes the three tokens 'a', 'b', 'c'; the group marker itself
    is discarded ('(f)' column suffixes survive as 'Cd(f)' since they contain
    no whitespace)."""
    return line.replace("(", " ").replace(")", " ").split()


# a parenthesised group that CONTAINS whitespace => an inline vector column
_WS_VEC_GROUP_RE = re.compile(r"\(([^()]*\s[^()]*)\)")


def _flat_header(tokens: list[str]) -> list[str]:
    """Expand only vector-group header tokens (those with whitespace inside
    the parens, e.g. '(x y z)'); scalar tokens like 'Cd(f)' or
    'forces(pressure)' stay intact because they contain no whitespace."""
    out: list[str] = []
    for tok in tokens:
        expanded = _WS_VEC_GROUP_RE.sub(lambda m: " " + m.group(1) + " ", tok)
        out.extend(expanded.split())
    return out


def read_dat_fields(path: str | Path) -> tuple[list[str], list[list[str]]]:
    """Read a .dat file.

    Returns (header_tokens, rows) where header_tokens are the tokens of the
    last '#' line and each row is the token list of a non-comment line whose
    token count equals the header length (partial/trailing lines are dropped).
    Raises DatReadError if the file is missing/unreadable or has no header.
    """
    p = Path(path)
    if not p.exists():
        raise DatReadError(f"no such file: {p}")
    header: list[str] = []
    lines: list[str] = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    cols = line.lstrip("#").split()
                    if cols:
                        header = cols
                    continue
                lines.append(line)
    except OSError as exc:
        raise DatReadError(f"cannot read {p}: {exc}") from exc

    if not header:
        raise DatReadError(f"no header line in {p}")
    # Expand only parenthesised vector groups that CONTAIN whitespace (e.g. a
    # "( x y z )" style header column); scalar tokens like "Cd(f)" or
    # "forces(pressure)" keep their parentheses and stay single tokens.
    header = list(_flat_header(header))

    rows: list[list[str]] = []
    for line in lines:
        parts = _split_row(line)
        if not parts:
            continue
        if len(parts) != len(header):
            # partial last line while the solver is writing
            continue
        rows.append(parts)
    if not rows:
        raise DatReadError(f"no data rows in {p}")
    return header, rows


def to_array(header: list[str], rows: list[list[str]]) -> dict[str, np.ndarray]:
    """Convert rows to {column_token: float array}, non-numeric -> NaN."""
    n = len(header)
    arr = np.empty((len(rows), n), dtype=np.float64)
    for i, row in enumerate(rows):
        for j, tok in enumerate(row):
            try:
                arr[i, j] = float(tok)
            except ValueError:
                arr[i, j] = np.nan
    return {name: arr[:, i] for i, name in enumerate(header)}


def last_converged_row(
    data: dict[str, np.ndarray],
    force_keys: tuple[str, ...] = ("Time",),
) -> dict[str, float]:
    """Return the last fully-finite row as a plain dict, skipping trailing
    rows where a required key is NaN/absent. This is the 'converged' sample:
    the solver appends one row per output write, the newest stable one is at
    the tail."""
    n = next(iter(data.values())).shape[0] if data else 0
    for i in range(n - 1, -1, -1):
        ok = True
        for k in force_keys:
            col = data.get(k)
            if col is None or i >= col.shape[0] or np.isnan(col[i]):
                ok = False
                break
        if ok:
            return {name: float(row[i]) for name, row in data.items()}
    raise DatReadError(f"no finite row with keys {force_keys}")
