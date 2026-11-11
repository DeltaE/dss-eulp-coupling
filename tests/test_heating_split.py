# -*- coding: utf-8 -*-
"""
test_heating_split.py
---------------------
heating_split.split_heating (the Phase 7b heating split) on a synthetic list of seven
loads with the three mixes of 0_experimental_design/mixes_fixed.yaml: exact group
counts by largest remainder, labels that match those counts, and the same labels on a
second call with the same inputs. On eight loads that share five loadshapes: the
building unit (exact counts over loadshapes, one label per loadshape) and the customer
unit (the labels of the rule before heating_label_unit). load_segment on residential,
commercial, mixed and missing loadshapes. line_shares on hand-written Load lines: even
and uneven legs, a one-line load, a kvar fallback, a kW sum of 0 and exponents. Also checks that pipeline_utils.peak_day_rule
and heating_label_unit stop on a missing or unknown value, and that
pipeline_config.yaml holds per_circuit and building.

Run directly (no pytest needed): python tests/test_heating_split.py
Or under pytest: pytest tests/test_heating_split.py
"""
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
from heating_split import is_baseline_only, line_shares, load_segment, split_heating  # noqa: E402
from pipeline_utils import heating_label_unit, peak_day_rule  # noqa: E402

with open(os.path.join(REPO_ROOT, "0_experimental_design", "mixes_fixed.yaml"), encoding="utf-8") as _f:
    MIXES = yaml.safe_load(_f)

# Seven loads, one loadshape each. Largest remainder on 7 loads:
# baseline 1.0/0/0 -> 7, 0, 0.
# mixed 0.5/0.3/0.2 -> raw 3.5, 2.1, 1.4; floors 3, 2, 1; the one left goes to the
#   largest remainder, baseline (0.5) -> 4, 2, 1.
# stress 0.2/0.2/0.6 -> raw 1.4, 1.4, 4.2; floors 1, 1, 4; the one left goes to the
#   largest remainder, a tie of 0.4 broken by name in reverse order, dm -> 1, 2, 4.
BASES = {f"load{i}" for i in range(7)}
BASE_TO_DAILY = {b: {f"res_kw_{b[4:]}_pu"} for b in BASES}
EXPECTED = {"baseline": (7, 0, 0), "mixed": (4, 2, 1), "stress": (1, 2, 4)}


def _split(mix_name):
    mix = MIXES[mix_name]
    return split_heating(set(BASES), BASE_TO_DAILY, mix["shares"], mix["heating_seed"],
                         "sub_1247", "sub_1247--feeder1")


def test_counts_by_largest_remainder():
    for mix_name, (n_b, n_dm, n_un) in EXPECTED.items():
        heat = _split(mix_name)
        assert (heat["n_b"], heat["n_dm"], heat["n_un"], heat["N"]) == (n_b, n_dm, n_un, 7), mix_name
        labels = list(heat["daily_to_scen"].values())
        assert len(labels) == 7, mix_name
        assert (labels.count("baseline"), labels.count("dm"), labels.count("un")) == (n_b, n_dm, n_un), mix_name


def test_same_labels_on_second_call():
    for mix_name in EXPECTED:
        first, second = _split(mix_name), _split(mix_name)
        assert first["daily_to_scen"] == second["daily_to_scen"], mix_name
        assert first["bases"] == second["bases"] and first["labels"] == second["labels"], mix_name


def test_baseline_only():
    assert is_baseline_only(MIXES["baseline"]["shares"])
    assert not is_baseline_only(MIXES["mixed"]["shares"])
    assert not is_baseline_only(MIXES["stress"]["shares"])


def _stops(cfg):
    try:
        peak_day_rule(cfg)
    except SystemExit as e:
        return e.code == 1
    return False


def test_unknown_peak_day_rule_stops():
    assert _stops({"peak_day_rule": "per_day"})
    assert _stops({})
    assert peak_day_rule({"peak_day_rule": "per_group"}) == "per_group"
    assert peak_day_rule({"peak_day_rule": "per_circuit"}) == "per_circuit"


def test_committed_rule_is_per_circuit():
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["peak_day_rule"] == "per_circuit"
    assert peak_day_rule(cfg) == "per_circuit"


# Eight loads (customers) on five loadshapes (buildings): res_kw_1_pu is shared by load0
# to load2, com_kw_9_pu by load6 and load7.
SHARED = {"load0": {"res_kw_1_pu"}, "load1": {"res_kw_1_pu"}, "load2": {"res_kw_1_pu"},
          "load3": {"res_kw_2_pu"}, "load4": {"res_kw_3_pu"}, "load5": {"res_kw_4_pu"},
          "load6": {"com_kw_9_pu"}, "load7": {"com_kw_9_pu"}}
# Largest remainder on 5 loadshapes: mixed raw 2.5, 1.5, 1.0; floors 2, 1, 1; the one
# left goes to the tie of 0.5 broken by name in reverse order, dm -> 2, 2, 1.
# stress raw 1.0, 1.0, 3.0 -> 1, 1, 3.
EXPECTED_BUILDING = {"mixed": (2, 2, 1), "stress": (1, 1, 3)}
# The labels of split_heating at 7016fe8 (counts over customers) on SHARED.
EXPECTED_CUSTOMER = {
    "mixed": {"com_kw_9_pu": "un", "res_kw_1_pu": "baseline", "res_kw_2_pu": "baseline",
              "res_kw_3_pu": "un", "res_kw_4_pu": "baseline"},
    "stress": {"com_kw_9_pu": "un", "res_kw_1_pu": "baseline", "res_kw_2_pu": "un",
               "res_kw_3_pu": "un", "res_kw_4_pu": "dm"},
}


def _split_shared(mix_name, unit):
    mix = MIXES[mix_name]
    return split_heating(set(SHARED), SHARED, mix["shares"], mix["heating_seed"],
                         "sub_1247", "sub_1247--feeder1", unit=unit)


def test_building_unit_counts_over_loadshapes():
    for mix_name, counts in EXPECTED_BUILDING.items():
        heat = _split_shared(mix_name, "building")
        assert (heat["n_b"], heat["n_dm"], heat["n_un"], heat["N"]) == counts + (5,), mix_name
        labels = heat["daily_to_scen"]
        assert sorted(labels) == sorted(heat["bases"]), mix_name
        values = list(labels.values())
        assert (values.count("baseline"), values.count("dm"), values.count("un")) == counts, mix_name
        assert dict(zip(heat["bases"], heat["labels"])) == labels, mix_name
        # every load of a loadshape runs in the loadshape's group
        for load, shapes in SHARED.items():
            assert len({labels[ls] for ls in shapes}) == 1, (mix_name, load)


def test_customer_unit_keeps_the_earlier_rule():
    for mix_name, expected in EXPECTED_CUSTOMER.items():
        heat = _split_shared(mix_name, "customer")
        assert heat["daily_to_scen"] == expected, mix_name
        assert heat["N"] == 8, mix_name
        default = split_heating(set(SHARED), SHARED, MIXES[mix_name]["shares"],
                                MIXES[mix_name]["heating_seed"], "sub_1247", "sub_1247--feeder1")
        assert default["daily_to_scen"] == expected, mix_name


def test_load_segment():
    b2d = {"h": {"res_kw_1_pu"}, "h2": {"res_kw_1_pu", "res_kw_2_pu"}, "c": {"com_kw_9_pu"},
           "m": {"res_kw_1_pu", "com_kw_9_pu"}, "e": set(), "o": {"other_kw_3_pu"}}
    assert load_segment("h", b2d) == "residential"
    assert load_segment("h2", b2d) == "residential"
    assert load_segment("c", b2d) == "commercial"
    assert load_segment("m", b2d) is None
    assert load_segment("e", b2d) is None
    assert load_segment("o", b2d) is None
    assert load_segment("absent", b2d) is None


def test_heating_label_unit_setting():
    for value in ("building", "customer"):
        assert heating_label_unit({"heating_label_unit": value}) == value
    for cfg in ({"heating_label_unit": "household"}, {}):
        try:
            heating_label_unit(cfg)
        except SystemExit as e:
            assert e.code == 1
        else:
            raise AssertionError(cfg)
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        assert heating_label_unit(yaml.safe_load(f)) == "building"


def _load(name, kw, kvar):
    return (f"New Load.{name} conn=wye bus1=b.1 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 "
            f"kW={kw} kvar={kvar} Phases=1 yearly=res_kw_1_pu\n")


def test_line_shares():
    lines = [_load("load_a_1", 5.99, 1.67), _load("load_a_2", 5.99, 1.67), "\n",
             _load("load_b_1", 4, 1), _load("load_b_2", 8, 3),
             _load("load_c", 33.5, 6.8),
             _load("load_d_1", 2, 0), _load("load_d_2", 6, 0),
             _load("load_e_1", "5.99e+00", "1.5E-01"), _load("load_e_2", "1.198e1", "4.5e-1")]
    shares, n_fallback = line_shares(lines)
    assert shares["load_a_1"] == (0.5, 0.5) and shares["load_a_2"] == (0.5, 0.5)
    assert abs(shares["load_b_1"][0] - 1 / 3) < 1e-12 and abs(shares["load_b_2"][0] - 2 / 3) < 1e-12
    assert shares["load_b_1"][1] == 0.25 and shares["load_b_2"][1] == 0.75
    assert shares["load_c"] == (1.0, 1.0)
    assert shares["load_d_1"] == (0.25, 0.25) and shares["load_d_2"] == (0.75, 0.75)
    assert n_fallback == 2
    assert abs(shares["load_e_1"][0] - 1 / 3) < 1e-12 and abs(shares["load_e_2"][1] - 0.75) < 1e-12
    assert len(shares) == 9


def test_line_shares_kw_sum_zero_stops():
    try:
        line_shares([_load("load_z_1", 0, 1), _load("load_z_2", 0.0, 1)])
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("kW sum of 0 did not stop")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
