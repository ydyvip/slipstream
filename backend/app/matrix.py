"""Multi-dimensional case_matrix fan-out (v10 test program).

A `case_matrix` config fans one POST /api/runs submit out into a group of runs,
one per Cartesian-product combination of the swept dimensions (alpha / beta /
control deflections), so a whole wind-tunnel-style test matrix runs as one
batch. This generalises the existing one-axis yaw/pitch sweep mechanism: the
sweep submits N runs along one axis; a matrix submits the full grid.
"""
from __future__ import annotations

import itertools

# Canonical dimension order. Each row is (case_matrix key, child config key,
# name-suffix letter). alpha_deg maps to pitch_deg (angle of attack) and
# beta_deg to yaw_deg (sideslip) — the attitude fields the solver already
# understands; the delta_*_deg keys pass through to the child config verbatim.
# The suffix letters follow the documented " a0 b5 e-8" style; the aileron and
# rudder rows use two-character letters so alpha's "a" stays unambiguous when
# a program sweeps alpha and delta_a together.
DIMS = (
    ("alpha_deg", "pitch_deg", "a"),
    ("beta_deg", "yaw_deg", "b"),
    ("delta_e_deg", "delta_e_deg", "e"),
    ("delta_a_deg", "delta_a_deg", "da"),
    ("delta_r_deg", "delta_r_deg", "dr"),
)
MATRIX_KEYS = tuple(d[0] for d in DIMS)

# Program-level cap: the largest a whole case_matrix may fan out to, however
# many batches it takes. It is a hard cap so a typo can't queue thousands of
# solves.
MAX_PROGRAM_MEMBERS = 500

# A yaw/pitch sweep batches up to 8 members; a matrix programs a whole sweep
# grid, so it gets a documented, looser ceiling that the frontend also warns at
# (TestProgramView.CASE_CAP). It is still a hard cap so a typo can't queue
# hundreds of solves. It also doubles as the chunk size: a program larger than
# this is split into several ≤200-member batches (each its own group, all
# sharing one program_id).
MAX_MATRIX_MEMBERS = 200


def name_suffix(member_cfg: dict) -> str:
    """The " a0 b5 e-8" name suffix for one matrix member, in canonical order.

    Only dims present in the member's config appear, single-spaced, with a
    leading space. Values render with `:g`: a sign on negatives, no leading-
    zero padding (0 -> "a0", 5 -> "b5", -8 -> "e-8"). This is also what the
    group endpoint strips off a member's name to recover the base name."""
    parts = []
    for key, _cfg_key, letter in DIMS:
        value = member_cfg.get(key)
        if value is None:
            continue
        parts.append(f"{letter}{value:g}")
    return (" " + " ".join(parts)) if parts else ""


def expand(matrix: dict, base_cfg: dict) -> list[dict]:
    """Expand a validated case_matrix into one child cfg per combination.

    The first dimension is the slowest (alpha, then beta, then the deflection
    dims fastest), so the returned list is already sorted by
    (alpha, beta, delta_e, delta_a, delta_r) ascending — the order the group
    endpoint presents members in. Each child:
      * maps alpha_deg -> pitch_deg and beta_deg -> yaw_deg,
      * passes delta_*_deg through verbatim,
      * carries the full (canonical) case_matrix as a group marker and
        `sweep_param: "matrix"`, and
      * gets a "<base> a0 b5 e-8"-style name suffix (present dims only).

    `base_cfg` is never mutated."""
    dims = [(key, cfg_key, _letter) for key, cfg_key, _letter in DIMS
            if key in matrix]
    base_name = base_cfg["name"]
    out = []
    for combo in itertools.product(*(matrix[key] for key, _cfg, _l in dims)):
        child = dict(base_cfg)
        for (key, cfg_key, _letter), value in zip(dims, combo):
            child[cfg_key] = float(value)
            # The matrix key lives on the child too, so the group endpoint can
            # report alpha_deg / beta_deg / delta_*_deg straight from the cfg.
            child[key] = float(value)
        child["case_matrix"] = {key: list(matrix[key]) for key, _c, _l in dims}
        child["sweep_param"] = "matrix"
        child["name"] = base_name + name_suffix(child)
        out.append(child)
    return out
