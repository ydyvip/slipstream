"""Coordinate transformation and moment-reference translation.

Two concerns, kept separate so tests can exercise each:

1. transform_vector(matrix, v) — rotate a CFD-frame vector into the aero
   frame (config coordinate_mapping.rotation).

2. shift_moment_reference(F, M_O, r_O, r_C, sign_scale=1.0) — move a moment
   M_O (N·m) measured about point O to the CG/about point C:

       M_C = M_O - (r_C - r_O) x F

   applied AFTER the force vector has been expressed in the aero frame.
   The optional sign_scale argument lets callers flip the direction
   convention without creating a second code path (see normalize).
"""
from __future__ import annotations

import math
from typing import Sequence


def transform_vector(
    matrix: Sequence[Sequence[float]], v: Sequence[float]
) -> tuple[float, float, float]:
    """v_aero = matrix * v_cfd (3x3)."""
    if len(v) != 3:
        raise ValueError("vector must be length 3")
    out = []
    for row in matrix:
        if len(row) != 3:
            raise ValueError("rotation matrix rows must be length 3")
        out.append(sum(row[k] * float(v[k]) for k in range(3)))
    return tuple(out)  # type: ignore[return-value]


def shift_moment_reference(
    f: Sequence[float],
    m_o: Sequence[float],
    r_o: Sequence[float],
    r_c: Sequence[float],
) -> tuple[float, float, float]:
    """Translate a moment about point O to point C.

    M_C = M_O - (R) x F, where R = r_C - r_O (both in meters).
    https://en.wikipedia.org/wiki/Torque#Relationship_between_torque...
    """
    if len(f) != 3 or len(m_o) != 3 or len(r_o) != 3 or len(r_c) != 3:
        raise ValueError("force/moment/positions must be length-3 vectors")
    r = (r_c[0] - r_o[0], r_c[1] - r_o[1], r_c[2] - r_o[2])
    cross = (
        r[1] * f[2] - r[2] * f[1],
        r[2] * f[0] - r[0] * f[2],
        r[0] * f[1] - r[1] * f[0],
    )
    return (m_o[0] - cross[0], m_o[1] - cross[1], m_o[2] - cross[2])


def normalize_deg_to_rad(deg: float) -> float:
    return math.radians(deg)
