"""case_matrix fan-out: the pure expansion logic (product order, cfg mapping,
name suffix, group marker) without any API/HTTP involved."""
from __future__ import annotations

from app import matrix as mx


def _base(name="tail v1"):
    return {
        "name": name, "unit": "mm", "wind_speed": 15.0, "quality": "coarse",
        "yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0,
    }


def test_product_order_first_dim_slowest():
    cfg = mx.expand({"alpha_deg": [0.0, 4.0], "beta_deg": [0.0, 6.0, 8.0]}, _base())
    assert [(c["pitch_deg"], c["yaw_deg"]) for c in cfg] == [
        (0.0, 0.0), (0.0, 6.0), (0.0, 8.0),    # alpha=0, beta fastest
        (4.0, 0.0), (4.0, 6.0), (4.0, 8.0),    # alpha=4
    ]


def test_name_suffix_only_present_dims_in_canonical_order():
    cfg = mx.expand({"alpha_deg": [0.0], "beta_deg": [5.0], "delta_e_deg": [-8.0]},
                    _base())
    assert cfg[0]["name"] == "tail v1 a0 b5 e-8"


def test_name_suffix_subset_and_isolated_dims():
    assert [c["name"] for c in mx.expand({"delta_r_deg": [-10.0, 2.5]}, _base("rudder"))] \
        == ["rudder dr-10", "rudder dr2.5"]
    assert [c["name"] for c in mx.expand({"delta_a_deg": [1.5]}, _base("ail"))] \
        == ["ail da1.5"]
    assert mx.name_suffix({"alpha_deg": 0, "beta_deg": 3, "delta_e_deg": -4}) \
        == " a0 b3 e-4"
    assert mx.name_suffix({}) == ""


def test_cfg_mapping_sets_attitude_and_passes_deltas_verbatim():
    base = _base()
    [child] = mx.expand({"alpha_deg": [3.0], "beta_deg": [2.0],
                         "delta_e_deg": [4.0], "delta_a_deg": [5.0],
                         "delta_r_deg": [6.0]}, base)
    assert child["pitch_deg"] == 3.0  # alpha -> pitch
    assert child["yaw_deg"] == 2.0    # beta -> yaw
    assert (child["delta_e_deg"], child["delta_a_deg"], child["delta_r_deg"]) \
        == (4.0, 5.0, 6.0)           # control deflections pass through
    # The matrix keys live on the child too, so the group endpoint reports the
    # member's point in the program straight from the config.
    assert (child["alpha_deg"], child["beta_deg"]) == (3.0, 2.0)
    assert child["sweep_param"] == "matrix"
    assert child["case_matrix"] == {
        "alpha_deg": [3.0], "beta_deg": [2.0], "delta_e_deg": [4.0],
        "delta_a_deg": [5.0], "delta_r_deg": [6.0]}


def test_marker_is_canonical_regardless_of_input_order():
    cfg = mx.expand({"delta_e_deg": [-4.0], "alpha_deg": [1.0]}, _base())
    assert list(cfg[0]["case_matrix"]) == ["alpha_deg", "delta_e_deg"]
    assert cfg[0]["name"].endswith(mx.name_suffix(cfg[0]))
    assert mx.name_suffix(cfg[0]) == " a1 e-4"


def test_base_config_is_not_mutated():
    base = _base()
    mx.expand({"alpha_deg": [0.0, 1.0], "delta_r_deg": [2.0]}, base)
    assert base == _base()
    assert "case_matrix" not in base and "sweep_param" not in base
