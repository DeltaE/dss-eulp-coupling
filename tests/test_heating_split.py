# -*- coding: utf-8 -*-
"""
test_heating_split.py
---------------------
heating_split.split_heating (the Phase 7b heating split) on a synthetic list of seven
loads with the three mixes of 0_experimental_design/mixes_fixed.json: exact group
counts by largest remainder, labels that match those counts, and the same labels on a
second call with the same inputs. Also checks that pipeline_utils.peak_day_rule stops
on a missing or unknown peak_day_rule, and that pipeline_config.yaml holds per_circuit
and peak_day_rule returns it.

Run directly (no pytest needed): python tests/test_heating_split.py
Or under pytest: pytest tests/test_heating_split.py
"""
import json
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
from heating_split import is_baseline_only, split_heating  # noqa: E402
from pipeline_utils import peak_day_rule  # noqa: E402

with open(os.path.join(REPO_ROOT, "0_experimental_design", "mixes_fixed.json"), encoding="utf-8") as _f:
    MIXES = json.load(_f)

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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
