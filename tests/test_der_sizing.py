# -*- coding: utf-8 -*-
"""
test_der_sizing.py
------------------
der_sizing.py (Phase 7b hosts and Phase 7 deploy sizes) on hand-made data: host picks
per segment with the min-one rule and the switches, the three storage_hosts values, the
roof area under both sources and both segments, the PV size with the use cap or the roof
binding, the ComStock rule on the CaraDonna (2025) example, the annual yield of a
hand-made year, the inverter kVA, the storage size by segment with the small and large
split, the standby percent of a storage unit, and the der_sizing setting readers.

Run directly (no pytest needed): python tests/test_der_sizing.py
Or under pytest: pytest tests/test_der_sizing.py
"""
import math
import os
import sys

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from der_sizing import (FT2_TO_M2, annual_yield, der_choice, der_number, der_switch, der_value,  # noqa: E402
                        pick, pick_hosts, pv_kw_roof_and_use, roof_area_m2, segment_count, standby_pct,
                        storage_size)

BASES = [f"load_{i:03d}" for i in range(40)]


def _stops(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code == 1
    return False


def test_segment_count_min_one_and_switch():
    assert segment_count(0.05, 40) == 2
    assert segment_count(0.05, 5) == 1          # round(0.25) = 0, raised to one
    assert segment_count(0.0, 40) == 0
    assert segment_count(0.10, 0) == 0
    assert segment_count(0.15, 40, enabled=False) == 0
    assert segment_count(1.0, 3) == 3


def test_pick_is_the_phase7b_draw():
    import random
    rng = random.Random(555 + 1234)
    expected = list(BASES)
    rng.shuffle(expected)
    assert pick(555, 1234, BASES, 5) == expected[:5]
    assert pick(555, 1234, BASES, 0) == []
    assert pick(555, 1234, [], 3) == []


def test_storage_hosts_with_pv():
    pv, sto = pick_hosts(BASES, 6, 4, 555, 777, 99, "with_pv")
    assert len(pv) == 6 and len(sto) == 4 and set(sto) <= set(pv)
    assert sto == pick(777, 99, pv, 4)
    # more storage than PV hosts: the rest from the other bases
    pv, sto = pick_hosts(BASES, 3, 5, 555, 777, 99, "with_pv")
    assert set(pv) <= set(sto) and len(set(sto)) == 5
    assert sto[3:] == pick(777, 99, [b for b in BASES if b not in pv], 2)


def test_storage_hosts_independent_and_apart():
    pv, sto = pick_hosts(BASES, 6, 4, 555, 777, 99, "independent")
    assert sto == pick(777, 99, BASES, 4)
    pv, sto = pick_hosts(BASES, 6, 4, 555, 777, 99, "apart")
    assert not set(pv) & set(sto)
    assert sto == pick(777, 99, [b for b in BASES if b not in pv], 4)
    # every base has PV: storage falls back to all bases
    pv, sto = pick_hosts(BASES[:3], 3, 2, 555, 777, 99, "apart")
    assert len(pv) == 3 and len(sto) == 2 and set(sto) <= set(BASES[:3])


def test_roof_area_both_sources_and_segments():
    # residential floor_stories: 2,000 ft2 over 2 stories, 20 degree tilt
    r = roof_area_m2("residential", "floor_stories", 2000.0, 2.0, 999.0, 20.0)
    assert math.isclose(r, 1000.0 * FT2_TO_M2 / math.cos(math.radians(20.0)))
    # commercial floor_stories: flat
    assert math.isclose(roof_area_m2("commercial", "floor_stories", 10000.0, 2.0, 999.0), 5000.0 * FT2_TO_M2)
    # metadata: ft2 for homes, m2 for commercial buildings
    assert math.isclose(roof_area_m2("residential", "metadata", 2000.0, 2.0, 1100.0, 20.0), 1100.0 * FT2_TO_M2)
    assert roof_area_m2("commercial", "metadata", 10000.0, 2.0, 464.5) == 464.5


def test_pv_use_cap_and_roof_binding():
    # roof binds: 0.25 x 100 m2 x 0.21 = 5.25 kW < 1.0 x 13,000 kWh / 1,300 = 10 kW
    kw, cap_roof, cap_use, binds = pv_kw_roof_and_use(100.0, 0.25, 0.21, 1.0, 13000.0, 1300.0)
    assert math.isclose(kw, 5.25) and math.isclose(cap_use, 10.0) and binds
    # use cap binds: 0.5 x 6,500 / 1,300 = 2.5 kW < 5.25 kW
    kw, cap_roof, cap_use, binds = pv_kw_roof_and_use(100.0, 0.25, 0.21, 0.5, 6500.0, 1300.0)
    assert math.isclose(kw, 2.5) and math.isclose(cap_roof, 5.25) and not binds


def test_comstock_rule_caradonna_example():
    # CaraDonna 2025, section 5.1: 8,750 ft2 of roof gives 68 kW at 40 % coverage, 21 %
    roof = roof_area_m2("commercial", "metadata", 0.0, 1.0, 8750.0 * FT2_TO_M2)
    assert math.isclose(roof, 812.9, abs_tol=0.05)
    kw, _, _, binds = pv_kw_roof_and_use(roof, 0.40, 0.21, 1.0, 1.0e6, 1300.0)
    assert math.isclose(kw, 68.3, abs_tol=0.05) and binds


def test_annual_yield_and_inverter_kva():
    year = [0.0] * 35040
    for d in range(365):
        for i in range(40, 56):               # 4 hours a day at 0.5 kW per kW
            year[d * 96 + i] = 0.5
    assert math.isclose(annual_yield(year, 0.25), 365 * 16 * 0.5 * 0.25)
    pv_kw, ilr = 10.0, 1.24
    assert math.isclose(pv_kw / ilr, 8.0645, abs_tol=1e-4)


def test_storage_size_by_segment():
    # residential: ratio 1.0 whatever the size
    assert storage_size(150.0, 1.0, 1.0, 100.0, 2.0) == (150.0, 300.0)
    # commercial: small (<= 100 kW DC) ratio 1.0, large ratio 0.5
    assert storage_size(100.0, 1.0, 0.5, 100.0, 2.0) == (100.0, 200.0)
    assert storage_size(200.0, 1.0, 0.5, 100.0, 4.0) == (100.0, 400.0)


def test_setting_readers():
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key in ("pv_residential", "pv_commercial", "storage_residential", "storage_commercial"):
        assert der_switch(cfg, key) is True
    assert der_choice(cfg, "storage_hosts") == "with_pv"
    assert der_choice(cfg, "sizing_case") == "moderate"
    assert der_choice(cfg, "storage_rule") == "schedule"
    assert der_value(cfg, "residential", "roof_coverage", "moderate") == 0.25
    assert der_value(cfg, "commercial", "large_pv_kw") == 100.0
    assert der_number(cfg, "storage_reserve_pct") == 20.0
    assert _stops(der_switch, {"der_sizing": {}}, "pv_residential")
    assert _stops(der_switch, {"der_sizing": {"pv_residential": "yes"}}, "pv_residential")
    assert _stops(der_choice, {"der_sizing": {"storage_hosts": "nearby"}}, "storage_hosts")
    assert _stops(der_choice, {"der_sizing": {}}, "storage_rule")
    assert _stops(der_choice, {"der_sizing": {"storage_rule": "original"}}, "storage_rule")
    assert _stops(der_choice, {}, "storage_view")
    assert _stops(der_number, {"der_sizing": {"storage_pf": "high"}}, "storage_pf")
    assert _stops(der_value, {"der_sizing": {"residential": {}}}, "residential", "roof_coverage", "low")


def test_standby_pct():
    assert abs(standby_pct("residential", 6.0, 12.0, 0.24) - 0.2) < 1e-12
    assert standby_pct("commercial", 250.0, 12.0, 0.24) == 0.24
    for case in ("low", "moderate", "high"):
        assert der_choice({"der_sizing": {"storage_standby_case": case}}, "storage_standby_case") == case
    assert _stops(der_choice, {"der_sizing": {"storage_standby_case": "median"}}, "storage_standby_case")


def test_standby_element():
    for value in ("load", "idling"):
        assert der_choice({"der_sizing": {"storage_standby_element": value}}, "storage_standby_element") == value
    assert _stops(der_choice, {"der_sizing": {"storage_standby_element": "storage"}}, "storage_standby_element")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
