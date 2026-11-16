# -*- coding: utf-8 -*-
"""
Tests of load growth over planning years: the growth.yaml reader and its checks
(pipeline_utils), and the rules of 7_circuit_instantiation/deployer_modules/growth.py on
synthetic counts and one small synthetic feeder. No OpenDSS and no pipeline run.
"""

import copy
import math
import os
import subprocess
import sys

import pandas as pd
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from pipeline_utils import (SETTINGS_FILES, check_settings_dir, growth_infill_share, growth_on,  # noqa: E402
                            growth_rates, growth_settings, load_growth, merge_settings, planning_band,
                            uses_mix_days)
import growth  # noqa: E402
from der_sizing import pick_hosts, segment_count  # noqa: E402
from ev_cars import evwatts_cars, seed as ev_draw_seed  # noqa: E402
from heating_split import split_heating  # noqa: E402

DEFAULTS = load_growth(settings_dir="")
MODERATE = {"households": 0.79, "use_per_household": -0.28, "floorspace": 1.02, "use_per_ft2": -0.65}
LOW = {"households": 0.67, "use_per_household": -0.30, "floorspace": 0.84, "use_per_ft2": -0.61}
HIGH = {"households": 0.82, "use_per_household": -0.25, "floorspace": 1.20, "use_per_ft2": -0.67}
NATIONAL = {"commercial_buildings_million": 5.9, "households_million": 127.6}
# Homes and businesses of four circuits
CIRCUITS = [(494, 272), (868, 111), (742, 22), (719, 20)]


def _stops(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code == 1
    return False


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except growth.GrowthError:
        return True
    return False


def _with(**changes):
    g = copy.deepcopy(DEFAULTS)
    for key, value in changes.items():
        node = g
        parts = key.split("__")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return g


# ---------------------------------------------------------------------------
# Settings (L1 to L3)
# ---------------------------------------------------------------------------
def test_tracked_defaults_are_growth_off():
    g = growth_settings(DEFAULTS, "NC_GSO_urban_uhs13_1247")
    assert g["growth_years"] == 0 and not growth_on(g)
    assert growth_rates(g) == MODERATE
    assert growth_infill_share(g, "NC_GSO_urban_uhs13_1247") == 1.0
    assert g["network_growth"]["mode"] == "as_needed"           # with growth_years 0 nothing of it runs
    assert g["der_resize_with_growth"] is False and g["named_load_mv_line_m"] == 269.0
    assert growth_settings(_with(der_resize_with_growth=True))["der_resize_with_growth"] is True
    assert "growth.yaml" in SETTINGS_FILES
    assert planning_band(g, {"voltage_band": {"low_pu": 0.95, "high_pu": 1.05}}) == (0.95, 1.05)


def test_growth_settings_values():
    g = growth_settings(_with(growth_years=10.0, case="high", rates__households=0, infill_share="metro"),
                        "TX_AUS_urban_p2uhs12_1247")
    assert g["growth_years"] == 10 and growth_on(g)
    assert growth_rates(g) == dict(HIGH, households=0)
    assert growth_infill_share(g, "TX_AUS_urban_p2uhs12_1247") == 0.07
    assert growth_infill_share(growth_settings(_with(infill_share="national")), "x") == 0.21
    assert growth_infill_share(growth_settings(_with(infill_share=0.4)), "x") == 0.4
    cfg = {"voltage_band": {"low_pu": 0.9, "high_pu": 1.1}}
    assert planning_band(growth_settings(_with(planning_limits__voltage_band="range_a")), cfg) == (0.95, 1.05)
    assert planning_band(growth_settings(_with(planning_limits__voltage_band="range_b")), cfg) == (0.9167, 1.0583)
    assert planning_band(growth_settings(_with(planning_limits__voltage_band=[0.94, 1.06])), cfg) == (0.94, 1.06)
    assert planning_band(growth_settings(DEFAULTS), cfg) == (0.9, 1.1)


def test_every_bad_growth_value_stops():
    bad = [
        {"growth_years": -1}, {"growth_years": 2.5}, {"growth_years": True}, {"growth_years": "10"},
        {"case": "medium"}, {"rate_cases__households__low": "x"}, {"rate_cases__floorspace": {"low": 1}},
        {"rates__use_per_ft2": "fast"}, {"rates__households": -100},
        {"infill_share": 1.5}, {"infill_share": "city"}, {"infill_share_metro": [0.2]},
        {"infill_share_metro__NC_GSO_urban_uhs13_1247": 2}, {"infill_share_national": -0.1},
        {"companions": "state"}, {"companions_national__households_million": 0},
        {"companion_excluded_types": "Hospital"}, {"block_attach_buses": ["a"]},
        {"block_attach_buses__f1": "bus"},
        {"named_loads": {"feeder": "f"}}, {"named_loads": [{"feeder": "f", "type": "Hospital", "count": 0, "year": 1}]},
        {"named_loads": [{"feeder": "f", "type": "Hospital", "count": 1}]},
        {"named_loads": [{"feeder": "f", "type": "Hospital", "count": 1, "year": 1, "kw": 5}]},
        {"named_loads": [{"feeder": "f", "type": "Hospital", "count": 1, "year": 1, "bus": ""}]},
        {"named_load_bus": "nearest"}, {"named_load_mv_line_m": 0}, {"named_load_mv_line_m": "269"},
        {"named_load_mv_line_m": None}, {"der_resize_with_growth": "false"}, {"der_resize_with_growth": 0},
        {"der_resize_with_growth": None},
        {"load_factors": [{"feeder": "f", "load": "x"}]},
        {"load_factors": [{"feeder": "f", "load": "x", "factor": 1.1, "peak_factor": 0}]},
        {"load_factors": [{"feeder": "f", "factor": 1.1}]},
        {"planning_limits__voltage_band": "range_c"}, {"planning_limits__voltage_band": [1.05, 0.95]},
        {"planning_limits__voltage_bands__range_a": [0.95]}, {"planning_limits__line_limit_percent": 0},
        {"planning_limits__substation_limit_percent": "100"},
        {"network_growth__mode": "planned"}, {"network_growth__mode": False}, {"network_growth": "off"},
    ]
    for change in bad:
        assert _stops(growth_settings, _with(**change)), change
    # metro needs the run's topology in infill_share_metro
    assert _stops(growth_settings, _with(infill_share="metro"), "some_other_topology")
    assert not _stops(growth_settings, _with(infill_share="metro"), "NC_GSO_urban_uhs13_1247")
    assert _stops(growth_infill_share, _with(infill_share="metro"), "some_other_topology")


def test_off_is_read_as_text():
    """off without quotes is a boolean in YAML; the mode is read as text, "off" in quotes."""
    assert yaml.safe_load("mode: off")["mode"] is False
    assert yaml.safe_load('mode: "off"')["mode"] == "off"
    assert _stops(growth_settings, _with(network_growth__mode=yaml.safe_load("mode: off")["mode"]))
    assert not _stops(growth_settings, _with(network_growth__mode=yaml.safe_load('mode: "off"')["mode"]))
    assert growth_settings(_with(network_growth__mode="off"))["network_growth"]["mode"] == "off"


def test_growth_merge_strict_keys_and_open_maps(tmp_path):
    merged = merge_settings(DEFAULTS, {"growth_years": 10, "rates": {"households": 0}}, "growth.yaml")
    assert merged["growth_years"] == 10 and merged["rates"]["households"] == 0
    assert merged["rates"]["floorspace"] is None and merged["case"] == "moderate"
    assert DEFAULTS["growth_years"] == 0                                   # the base is not changed
    # a key path outside the tracked file stops
    assert _stops(merge_settings, DEFAULTS, {"growth_year": 10}, "growth.yaml")
    assert _stops(merge_settings, DEFAULTS, {"rates": {"homes": 1}}, "growth.yaml")
    assert _stops(merge_settings, DEFAULTS, {"planning_limits": {"voltage_bands": {"range_c": [0.9, 1.1]}}},
                  "growth.yaml")
    # the two maps keyed by topology or feeder take new keys
    merged = merge_settings(DEFAULTS, {"infill_share_metro": {"OTHER_topology": 0.3},
                                       "block_attach_buses": {"feeder_a": ["bus1", "bus2"]}}, "growth.yaml")
    assert merged["infill_share_metro"]["OTHER_topology"] == 0.3
    assert merged["infill_share_metro"]["NC_GSO_urban_uhs13_1247"] == 0.25
    assert merged["block_attach_buses"] == {"feeder_a": ["bus1", "bus2"]}
    # a list replaces the list of the tracked file
    merged = merge_settings(DEFAULTS, {"companion_excluded_types": ["Warehouse"]}, "growth.yaml")
    assert merged["companion_excluded_types"] == ["Warehouse"]
    # the settings folder: growth.yaml is one of its files, and load_growth merges it
    (tmp_path / "growth.yaml").write_text("growth_years: 5\ncase: low\n", encoding="utf-8")
    assert check_settings_dir(tmp_path) == ["growth.yaml"]
    g = growth_settings(load_growth(str(tmp_path)))
    assert g["growth_years"] == 5 and growth_rates(g) == LOW


def test_growth_off_writes_nothing(tmp_path):
    """With growth off phase growth prints one line, writes nothing and exits 0."""
    env = dict(os.environ, PIPELINE_WORK_ROOT=str(tmp_path))
    env.pop("PIPELINE_SETTINGS_DIR", None)
    proc = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "growth_plan.py"), "--topology-id", "any"],
                          cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[growth] growth_years is 0: growth is off, phase growth skipped, nothing written."
    assert list(tmp_path.iterdir()) == []


def test_uses_mix_days_with_growth():
    assert uses_mix_days("per_circuit", True, True) and uses_mix_days("per_circuit", False, True)
    assert not uses_mix_days("per_circuit", True, False) and not uses_mix_days("per_circuit", True)
    assert not uses_mix_days("per_group", True, True) and uses_mix_days("given", True, True)


# ---------------------------------------------------------------------------
# Factors and counts (L4 to L10)
# ---------------------------------------------------------------------------
def test_factors():
    f = growth.segment_factors(MODERATE, 10)
    assert round(f["residential"], 4) == 0.9724 and round(f["commercial"], 4) == 0.9369
    f = growth.segment_factors(LOW, 10)
    assert round(f["residential"], 4) == 0.9704 and round(f["commercial"], 4) == 0.9406
    f = growth.segment_factors(HIGH, 10)
    assert round(f["residential"], 4) == 0.9753 and round(f["commercial"], 4) == 0.9350
    assert round(growth.growth_factor(3.0, 10), 4) == 1.3439 and round(growth.growth_factor(3.0, 20), 4) == 1.8061
    assert growth.segment_factors(MODERATE, 0) == {"residential": 1.0, "commercial": 1.0}
    plan = {"factors": f, "load_factors": {"b": {"factor": 1.2, "peak_factor": None},
                                           "c": {"factor": 1.1, "peak_factor": 1.3}}}
    seg = {"a": "residential", "b": "commercial", "c": "commercial", "d": None}
    got = growth.customer_factors(plan, ["a", "b", "c", "d"], seg.get)
    assert got == {"a": f["residential"], "b": 1.2, "c": 1.0, "d": 1.0}


def test_stretch_worked_example():
    """Peak 900, mean 650 and minimum 500 kW (L7)."""
    a, b = growth.stretch_coefficients(900.0, 650.0, 1.10, 1.30)
    assert math.isclose(a, 1.82) and math.isclose(b, -468.0)
    assert [round(a * v + b, 9) for v in (900.0, 650.0, 500.0)] == [1170.0, 715.0, 442.0]
    a, b = growth.stretch_coefficients(900.0, 650.0, 1.30, 1.10)
    assert math.isclose(a, 0.58) and math.isclose(b, 468.0)
    assert [round(a * v + b, 9) for v in (900.0, 650.0, 500.0)] == [990.0, 845.0, 758.0]
    # on a curve: annual energy grows by factor and annual peak by peak_factor
    values = [500.0, 900.0, 550.0]
    a, b = growth.stretch(values, 1.10, 1.30)
    new = [a * v + b for v in values]
    assert math.isclose(sum(new), 1.10 * sum(values)) and math.isclose(max(new), 1.30 * max(values))
    # stops: a point below 0, and a flat curve
    assert _raises(growth.stretch, [10.0, 900.0, 20.0], 1.0, 3.0)
    assert _raises(growth.stretch, [5.0, 5.0, 5.0], 1.1, 1.3)
    assert _raises(growth.stretch_coefficients, 5.0, 5.0, 1.1, 1.3)


def test_counts_table():
    def table(rates, years, companions, share):
        return [growth.counts(h, n, rates, years, companions, NATIONAL, s)
                for (h, n), s in zip(CIRCUITS, share)]

    full = [1.0] * 4
    got = table(MODERATE, 10, "feeder", full)
    assert [c["new_homes"] for c in got] == [40, 71, 61, 59]
    assert [c["companions"] for c in got] == [22, 9, 2, 2]
    assert all(c["infill_homes"] == c["new_homes"] and c["block_homes"] == 0 for c in got)
    got = table(MODERATE, 10, "feeder", [0.25, 0.25, 0.07, 0.07])
    assert [(c["infill_homes"], c["block_homes"]) for c in got] == [(10, 30), (18, 53), (4, 57), (4, 55)]
    assert [(c["infill_companions"], c["block_companions"]) for c in got] == [(6, 16), (2, 7), (0, 2), (0, 2)]
    assert [c["companions"] for c in table(MODERATE, 10, "national", full)] == [2, 3, 3, 3]
    assert [c["companions"] for c in table(MODERATE, 10, "aeo", full)] == [29, 12, 2, 2]
    got = table(LOW, 10, "feeder", full)
    assert [c["new_homes"] for c in got] == [34, 60, 51, 50] and [c["companions"] for c in got] == [19, 8, 2, 1]
    got = table(HIGH, 10, "feeder", full)
    assert [c["new_homes"] for c in got] == [42, 74, 63, 61] and [c["companions"] for c in got] == [23, 9, 2, 2]
    got = table(MODERATE, 5, "feeder", full)
    assert [c["new_homes"] for c in got] == [20, 35, 30, 29] and [c["companions"] for c in got] == [11, 4, 1, 1]
    # no households growth: no new homes and no companions by the feeder rule
    none = growth.counts(494, 272, dict(MODERATE, households=0, floorspace=0), 10, "feeder", NATIONAL, 1.0)
    assert none["new_homes"] == 0 and none["companions"] == 0
    assert growth.counts(0, 5, MODERATE, 10, "feeder", NATIONAL, 1.0)["companions"] == 0
    # the national ratio: one business per 127.6 / 5.9 new homes
    assert growth.counts(1000, 0, dict(MODERATE, households=10.0), 1, "national", NATIONAL, 1.0)["companions"] \
        == round(100 / (127.6 / 5.9))


def test_year_additions_sum_to_counts_and_nest():
    """Year t adds what the counts at t years hold beyond earlier years: the additions sum
    to growth.counts at every horizon, and a shorter horizon is the start of a longer one."""
    for homes, businesses in CIRCUITS:
        for companions in ("feeder", "national", "aeo"):
            for share in (1.0, 0.25, 0.07):
                by_years = {}
                for years in (5, 10, 20):
                    adds = growth.year_additions(homes, businesses, MODERATE, years, companions, NATIONAL, share)
                    assert len(adds) == years
                    total = {key: sum(a[key] for a in adds) for key in adds[0]}
                    assert total == growth.counts(homes, businesses, MODERATE, years, companions, NATIONAL, share)
                    by_years[years] = adds
                assert by_years[10][:5] == by_years[5] and by_years[20][:10] == by_years[10]
    assert growth.year_additions(494, 272, MODERATE, 0, "feeder", NATIONAL, 1.0) == []


def test_companion_candidates_and_draw():
    buildings = {"b1": {"type": "SmallOffice", "sqft": 1000.0}, "b2": {"type": "Hospital", "sqft": 3000.0},
                 "b3": {"type": "RetailStandalone", "sqft": 8000.0}, "b4": {"type": "Warehouse", "sqft": 4000.0}}
    businesses = ["b1", "b2", "b3", "b4", "b5"]                       # b5 has no known building
    mean = growth.mean_floor_area(businesses, buildings)
    assert mean == 4000.0                                              # the mean keeps the excluded type
    assert growth.mean_floor_area(["b5"], buildings) == 0.0
    # the k-th companion: floor area no larger than k x mean, no excluded type
    assert growth.companion_candidates(1, businesses, buildings, ["Hospital", "PrimarySchool"], mean) == \
        (["b1", "b4"], 4000.0)
    assert growth.companion_candidates(2, businesses, buildings, ["Hospital"], mean) == (["b1", "b3", "b4"], 8000.0)
    assert growth.companion_candidates(0, businesses, buildings, [], mean) == ([], 0.0)
    # the bound of the last companion of a circuit: companions x its mean floor area
    assert round(22 * 16994.5) == 373879
    seed = growth.growth_seed(555, "sub", "feeder")
    pool = ["b1", "b3", "b4"]
    first = growth.companion_draw(1, pool, set(), seed)
    assert first in pool and growth.companion_draw(1, pool, set(), seed) == first
    # a business an earlier companion copied is left out while another is left
    assert growth.companion_draw(2, pool, {"b1", "b4"}, seed) == "b3"
    assert growth.companion_draw(3, pool, {"b1", "b3", "b4"}, seed) in pool
    assert growth.companion_draw(1, [], set(), seed) is None           # an empty pool


# ---------------------------------------------------------------------------
# A small synthetic feeder
# ---------------------------------------------------------------------------
LINECODES = """
New Linecode.3P units=km nphases=3 Rmatrix=(0.2 0.05 0.05 | 0.05 0.2 0.05 | 0.05 0.05 0.2 ) Xmatrix=(0.6 0.2 0.2 | 0.2 0.6 0.2 | 0.2 0.2 0.6 ) normamps=400.0
New Linecode.1P units=km nphases=1 Rmatrix=(0.5 ) Xmatrix=(0.7 ) normamps=100.0
New Linecode.LV units=km nphases=2 Rmatrix=(0.9 0.3 | 0.3 0.9 ) Xmatrix=(0.5 0.4 | 0.4 0.5 ) normamps=200.0
New Linecode.LV3 units=km nphases=3 Rmatrix=(0.3 0.1 0.1 | 0.1 0.3 0.1 | 0.1 0.1 0.3 ) Xmatrix=(0.3 0.1 0.1 | 0.1 0.3 0.1 | 0.1 0.1 0.3 ) normamps=300.0
"""
LINES = """
New Line.head Units=km Length=0.1 bus1=src.1.2.3 bus2=a.1.2.3 switch=n enabled=y phases=3 Linecode=3P

New Line.main2 Units=km Length=0.2 bus1=a.1.2.3 bus2=b.1.2.3 switch=n enabled=y phases=3 Linecode=3P

New Line.main3 Units=km Length=0.3 bus1=b.1.2.3 bus2=c.1.2.3 switch=n enabled=y phases=3 Linecode=3P

New Line.fuse1 Units=km Length=0.001 bus1=a.2 bus2=l1.2 switch=y enabled=y phases=1 Linecode=1P

New Fuse.Fuse_fuse1 monitoredobj=Line.fuse1 enabled=y ratedcurrent=100.0

New Line.lat1 Units=km Length=0.05 bus1=l1.2 bus2=l2.2 switch=n enabled=y phases=1 Linecode=1P

New Line.s1 Units=km Length=0.02 bus1=t1lv.1.2 bus2=h1.1.2 switch=n enabled=y phases=2 Linecode=LV

New Line.s2 Units=km Length=0.03 bus1=t2lv.1.2 bus2=h2.1.2 switch=n enabled=y phases=2 Linecode=LV

New Line.s3 Units=km Length=0.04 bus1=t2lv.1.2 bus2=h3.1.2 switch=n enabled=y phases=2 Linecode=LV

New Line.mvc Units=km Length=0.03 bus1=b.1.2.3 bus2=m1.1.2.3 switch=n enabled=y phases=3 Linecode=3P

New Line.s4 Units=km Length=0.01 bus1=t3lv.1.2.3 bus2=c1.1.2.3 switch=n enabled=y phases=3 Linecode=LV3

New Line.s5 Units=km Length=0.015 bus1=t4lv.1.2.3 bus2=c2.1.2.3 switch=n enabled=y phases=3 Linecode=LV3

New Line.tie Units=km Length=0.001 bus1=c.1.2.3 bus2=zz.1.2.3 switch=y enabled=n phases=3 Linecode=3P
"""
TRANSFORMERS = """
New Transformer.t1 phases=1 windings=3 %loadloss=0.8 wdg=1 conn=wye bus=l1.2 Kv=7.2 kva=25.0 %r=0.27 wdg=2 conn=wye bus=t1lv.1.0 Kv=0.12 kva=25.0 %r=0.53 wdg=3 conn=wye bus=t1lv.0.2 Kv=0.12 kva=25.0 %r=0.53 XHL=2.4 XLT=2.4 XHT=1.6

New Transformer.t2 phases=1 windings=3 %loadloss=0.8 wdg=1 conn=wye bus=l2.2 Kv=7.2 kva=50.0 %r=0.27 wdg=2 conn=wye bus=t2lv.1.0 Kv=0.12 kva=50.0 %r=0.53 wdg=3 conn=wye bus=t2lv.0.2 Kv=0.12 kva=50.0 %r=0.53 XHL=2.4 XLT=2.4 XHT=1.6

New Transformer.t3 phases=3 windings=2 %loadloss=1.0 wdg=1 conn=wye bus=b Kv=12.47 kva=150.0 %r=0.5 wdg=2 conn=wye bus=t3lv Kv=0.48 kva=150.0 %r=0.5 XHL=4.0

New Transformer.t4 phases=3 windings=2 %loadloss=1.1 wdg=1 conn=wye bus=c Kv=12.47 kva=500.0 %r=0.55 wdg=2 conn=wye bus=t4lv Kv=0.48 kva=500.0 %r=0.55 XHL=5.0
"""
LOADS = """
New Load.load_h1_1 conn=wye bus1=h1.1 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=1.5 kvar=0.3 Phases=1 yearly=res_kw_1_pu

New Load.load_h1_2 conn=wye bus1=h1.2 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=0.5 kvar=0.1 Phases=1 yearly=res_kw_1_pu

New Load.load_h2_1 conn=wye bus1=h2.1 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=1.0 kvar=0.2 Phases=1 yearly=res_kw_2_pu

New Load.load_h2_2 conn=wye bus1=h2.2 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=1.0 kvar=0.2 Phases=1 yearly=res_kw_2_pu

New Load.load_h3_1 conn=wye bus1=h3.1 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=2.0 kvar=0.4 Phases=1 yearly=res_kw_1_pu

New Load.load_h3_2 conn=wye bus1=h3.2 kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=2.0 kvar=0.4 Phases=1 yearly=res_kw_1_pu

New Load.load_m1 conn=wye bus1=m1.1.2.3 kV=12.47 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=800.0 kvar=200.0 Phases=3 yearly=com_kw_10_pu

New Load.load_c1 conn=wye bus1=c1.1.2.3 kV=0.48 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=100.0 kvar=30.0 Phases=3 yearly=com_kw_11_pu

New Load.load_c2 conn=wye bus1=c2.1.2.3 kV=0.48 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=300.0 kvar=60.0 Phases=3 yearly=com_kw_12_pu
"""
MASTER = """Clear

New Circuit.feeder_test bus1=src pu=1.03 basekV=12.47 R1=1e-05 X1=1e-05 R0=1e-05 X0=1e-05

Redirect LineCodes.dss
Redirect Lines.dss
new monitor.m1 element=Line.head mode=0
new monitor.m2 element=Line.head mode=1
"""
# 0.001 degree of latitude is about 111 m
BUSCOORDS = """src 0.0 0.0
a 0.001 0.0
b 0.003 0.0
c 0.006 0.0
l1 0.001 0.0001
l2 0.001 0.0006
t1lv 0.001 0.0001
h1 0.0012 0.0001
t2lv 0.001 0.0006
h2 0.0012 0.0006
h3 0.0008 0.0006
m1 0.003 0.0003
t3lv 0.003 0.0
c1 0.003 -0.0001
t4lv 0.006 0.0
c2 0.006 -0.0001
"""
TEXTS = {"lines.dss": LINES, "transformers.dss": TRANSFORMERS, "loads.dss": LOADS, "master.dss": MASTER,
         "linecodes.dss": LINECODES, "buscoords.dss": BUSCOORDS}


def _net():
    net = growth.read_feeder(TEXTS)
    tr_map, served = growth.transformer_map(net, TEXTS)
    return net, tr_map, served


def test_read_feeder():
    net, tr_map, served = _net()
    assert net["source"] == "src"
    assert len(net["lines"]) == 12 and len(net["transformers"]) == 4 and len(net["loads"]) == 9
    seg = {b: c["segment"] for b, c in net["customers"].items()}
    assert seg == {"load_h1": "residential", "load_h2": "residential", "load_h3": "residential",
                   "load_m1": "commercial", "load_c1": "commercial", "load_c2": "commercial"}
    assert net["customers"]["load_h1"]["kw"] == 2.0 and net["customers"]["load_h1"]["bus"] == "h1"
    assert net["mv"] == {"src", "a", "b", "c", "l1", "l2", "m1"}          # no bus behind a transformer
    assert "zz" not in net["parent"] and not net["extra_lines"]           # the open tie is left out
    assert growth.three_phase_mv_buses(net) == ["a", "b", "c", "m1"]
    assert served == {"t1": ["load_h1"], "t2": ["load_h2", "load_h3"], "t3": ["load_c1"], "t4": ["load_c2"]}
    assert tr_map["load_m1"] is None
    assert net["linecodes"]["3p"]["normamps"] == 400.0
    assert abs(net["linecodes"]["3p"]["z1"] - complex(0.15, 0.4)) < 1e-12
    fuse = next(ln for ln in net["lines"] if ln["name"] == "fuse1")
    assert fuse["length_m"] == 1.0 and fuse["switch"] and fuse["phases"] == 1
    assert _raises(growth.read_feeder, dict(TEXTS, **{"master.dss": "Clear\n"}))


def test_three_connection_cases():
    net, tr_map, served = _net()
    # a customer under a shared transformer: a new drop from the bus where its last line starts
    conn = growth.customer_connection(net, "load_h2", tr_map, served)
    assert conn["pattern"] == "drop" and conn["line"]["name"] == "s2" and conn["transformer"]["name"] == "t2"
    new = growth.copy_customer(net, "load_h2", "h1", conn)
    assert new["pattern"] == "drop" and new["transformer"] == "t2" and new["transformers"] == []
    assert new["lines"] == ["New Line.s2_gh1 Units=km Length=0.03 bus1=t2lv.1.2 bus2=h2_gh1.1.2 switch=n "
                            "enabled=y phases=2 Linecode=LV"]
    assert [(ld["name"], ld["template"], ld["bus1"]) for ld in new["loads"]] == [
        ("load_h2_gh1_1", "load_h2_1", "h2_gh1.1"), ("load_h2_gh1_2", "load_h2_2", "h2_gh1.2")]
    assert new["buses"] == {"h2_gh1": "h2"}
    # a customer alone on its transformer: its own copy of the transformer and of its secondary
    conn = growth.customer_connection(net, "load_h1", tr_map, served)
    assert conn["pattern"] == "transformer"
    new = growth.copy_customer(net, "load_h1", "h2", conn)
    assert new["transformer"] == "t1_gh2" and len(new["transformers"]) == 1
    tr = new["transformers"][0]
    assert tr.startswith("New Transformer.t1_gh2 phases=1 windings=3 %loadloss=0.8 wdg=1 conn=wye bus=l1.2 Kv=7.2 kva=25.0")
    assert "bus=t1lv_gh2.1.0" in tr and "bus=t1lv_gh2.0.2" in tr and "XHL=2.4 XLT=2.4 XHT=1.6" in tr
    assert new["lines"] == ["New Line.s1_gh2 Units=km Length=0.02 bus1=t1lv_gh2.1.2 bus2=h1_gh2.1.2 switch=n "
                            "enabled=y phases=2 Linecode=LV"]
    assert new["buses"] == {"h1_gh2": "h1", "t1lv_gh2": "t1lv"}
    # a medium-voltage customer: a copy of the line that feeds its bus, from the same upstream bus
    conn = growth.customer_connection(net, "load_m1", tr_map, served)
    assert conn["pattern"] == "mv_line" and conn["up"] == "b"
    new = growth.copy_customer(net, "load_m1", "c1", conn)
    assert new["lines"] == ["New Line.mvc_gc1 Units=km Length=0.03 bus1=b.1.2.3 bus2=m1_gc1.1.2.3 switch=n "
                            "enabled=y phases=3 Linecode=3P"]
    assert [(ld["name"], ld["bus1"]) for ld in new["loads"]] == [("load_m1_gc1", "m1_gc1.1.2.3")]
    assert new["transformer"] == ""
    # at a block's attach bus a business gets its own transformer copy on that bus
    conn = growth.customer_connection(net, "load_c1", tr_map, served)
    new = growth.copy_customer(net, "load_c1", "d1", conn, at="c", own_transformer=True)
    assert "wdg=1 conn=wye bus=c Kv=12.47" in new["transformers"][0] and "bus=t3lv_gd1 " in new["transformers"][0]
    # every new name is unique and no customer name ends in _<digits>
    assert growth.new_name("load_h2_1", "h12") == "load_h2_gh12_1" and growth.new_name("load_m1", "n1x1") == "load_m1_gn1x1"
    assert growth._base("load_h2_gh12_1") == "load_h2_gh12" and growth._base("load_m1_gn1x1") == "load_m1_gn1x1"


def test_customer_on_its_own_bus():
    """A customer whose load bus is not the end of exactly one line is copied onto its bus."""
    texts = dict(TEXTS)
    texts["loads.dss"] = LOADS + ("\nNew Load.load_d1 conn=wye bus1=t3lv.1.2.3 kV=0.48 model=1 kW=10.0 kvar=2.0 "
                                  "Phases=3 yearly=com_kw_13_pu\n")
    net = growth.read_feeder(texts)
    tr_map, served = growth.transformer_map(net, texts)
    conn = growth.customer_connection(net, "load_d1", tr_map, served)
    assert conn["pattern"] == "own_bus"
    new = growth.copy_customer(net, "load_d1", "c3", conn)
    assert new["lines"] == [] and new["transformers"] == [] and new["buses"] == {}
    assert [(ld["name"], ld["bus1"]) for ld in new["loads"]] == [("load_d1_gc3", "t3lv.1.2.3")]


def test_find_laterals_and_copy():
    net, _, _ = _net()
    laterals = growth.find_laterals(net)
    assert len(laterals) == 1
    lat = laterals[0]
    assert (lat["root"], lat["tap"], lat["kind"], lat["homes"], lat["businesses"]) == ("l1", "a", "homes", 3, 0)
    assert [ln["name"] for ln in lat["lines"]] == ["fuse1", "lat1", "s1", "s2", "s3"]
    assert [t["name"] for t in lat["transformers"]] == ["t1", "t2"]
    assert lat["customers"] == ["load_h1", "load_h2", "load_h3"]
    new = growth.copy_lateral(net, lat, "b1", "c")
    # the copy keeps its own phase at the attach bus and every other bus is new
    assert new["lines"][0] == ("New Line.fuse1_gb1 Units=km Length=0.001 bus1=c.2 bus2=l1_gb1.2 switch=y enabled=y "
                               "phases=1 Linecode=1P")
    assert len(new["lines"]) == 5 and len(new["transformers"]) == 2 and len(new["loads"]) == 6
    assert "bus=l1_gb1.2" in new["transformers"][0] and "bus=l2_gb1.2" in new["transformers"][1]
    assert set(new["buses"].values()) == {"l1", "l2", "t1lv", "t2lv", "h1", "h2", "h3"}
    names = [text.split()[1] for text in new["lines"] + new["transformers"]] + [ld["name"] for ld in new["loads"]]
    assert len(set(names)) == len(names)
    # the new buses: the template's coordinates shifted so the tap sits on the attach bus
    coords = growth.shifted_coords(net, new["buses"], "a", "c")
    assert math.isclose(coords["l1_gb1"][0], 0.006) and math.isclose(coords["l1_gb1"][1], 0.0001)
    # a lateral of businesses only is never a template; one with a customer of neither segment is none
    texts = dict(TEXTS, **{"loads.dss": LOADS.replace("res_kw_", "com_kw_9")})
    assert [x["kind"] for x in growth.find_laterals(growth.read_feeder(texts))] == ["businesses"]
    texts = dict(TEXTS, **{"loads.dss": LOADS.replace("yearly=res_kw_2_pu", "yearly=other_2")})
    assert [x["kind"] for x in growth.find_laterals(growth.read_feeder(texts))] == ["none"]


def _add(infill_homes=0, infill_companions=0, block_homes=0, block_companions=0):
    return {"new_homes": infill_homes + block_homes, "companions": infill_companions + block_companions,
            "infill_homes": infill_homes, "block_homes": block_homes, "infill_companions": infill_companions,
            "block_companions": block_companions}


BIZ = {f"biz{i}": {"type": "SmallOffice", "sqft": 1000.0 * i} for i in range(1, 7)}   # mean 3,500 ft2


def test_block_eligibility():
    net, _, _ = _net()
    laterals = growth.find_laterals(net)
    none = ([], {}, [], 0.0)
    assert growth.eligible_templates(laterals, 3, 0, 0, *none) == laterals
    assert growth.eligible_templates(laterals, 2, 0, 0, *none) == []              # more homes than are waiting
    assert growth.eligible_templates([dict(laterals[0], kind="businesses")], 9, 9, 0, *none) == []
    # a mixed lateral: its business is companion placed + 1 and has to fit that companion's bound
    mixed = [dict(laterals[0], kind="mixed", businesses=1, customers=laterals[0]["customers"] + ["biz6"])]
    args = (sorted(BIZ), BIZ, ["Hospital"], 3500.0)
    assert growth.eligible_templates(mixed, 3, 1, 0, *args) == []                 # 6,000 ft2 above 1 x 3,500
    assert growth.eligible_templates(mixed, 3, 1, 1, *args) == mixed              # no larger than 2 x 3,500
    assert growth.eligible_templates(mixed, 3, 0, 1, *args) == []                 # no companion waiting
    assert growth.eligible_templates(mixed, 3, 1, 1, sorted(BIZ), BIZ, ["SmallOffice"], 3500.0) == []
    assert growth.eligible_templates(mixed, 3, 1, 1, sorted(BIZ), {}, [], 3500.0) == []   # no known building


def test_block_spacing():
    net, _, _ = _net()
    laterals = growth.find_laterals(net)
    seed = growth.growth_seed(555, "sub", "feeder")
    # spacing: the attach buses are at least r(new) + r(earlier) apart, r the reach of the lateral
    xy = growth.project(net["coords"])
    r = growth.lateral_radius(laterals[0], xy)
    assert 60 < r < 75                                                            # tap a to h3: about 70 m
    events = growth.plan_years(net, laterals, [_add(block_homes=7)], ["x"], [], {}, [], seed)
    built = [e for e in events if e["event"] == "block" and e["attach"]]
    assert len(built) == 2 and built[0]["attach"] != built[1]["attach"]
    d = math.hypot(xy[built[0]["attach"]][0] - xy[built[1]["attach"]][0],
                   xy[built[0]["attach"]][1] - xy[built[1]["attach"]][1])
    assert d >= 2 * r
    # the outermost bus along a bearing: east of the load centre it is c, west it is a
    centre = growth.load_centre(net, xy)
    buses = growth.three_phase_mv_buses(net)
    assert growth.attach_bus(buses, xy, centre, 0.0, r, []) == "c"
    assert growth.attach_bus(buses, xy, centre, math.pi, r, []) == "a"
    assert growth.attach_bus(buses, xy, centre, 0.0, r, [("c", r)]) == "b"        # c is taken, m1 is too near
    assert growth.attach_bus(buses, xy, centre, 0.0, 1000.0, [("c", r)]) is None  # nothing far enough
    # given attach buses are used in order before any drawn bearing, and must be three-phase buses
    events = growth.plan_years(net, laterals, [_add(block_homes=3)], ["x"], [], {}, [], seed, ["B"])
    assert events[0]["attach"] == "b" and events[0]["given"]
    assert _raises(growth.plan_years, net, laterals, [_add(block_homes=3)], ["x"], [], {}, [], seed, ["l1"])


def test_plan_years_order_waiting_and_dealing():
    net, _, _ = _net()
    laterals = growth.find_laterals(net)                                          # one lateral of 3 homes
    seed = growth.growth_seed(555, "sub", "feeder")
    order = [f"home{i}" for i in range(4)]
    args = (order, sorted(BIZ), BIZ, [], seed)

    def brief(events):
        return [(e["event"], e["year"], e.get("position") or e["k"]) for e in events]

    # year 1: infill homes, then infill companions; 2 block homes and 1 block companion wait
    one = growth.plan_years(net, laterals, [_add(2, 1, 2, 1)], *args)
    assert brief(one) == [("home", 1, 1), ("home", 1, 2), ("companion", 1, 1), ("home", 1, 3), ("home", 1, 4),
                          ("companion", 1, 2)]
    assert [e["template"] for e in one if e["event"] == "home"] == order
    assert [(e["remainder"], e["waiting"]) for e in one] == [(False, False)] * 3 + [(True, True)] * 3
    assert one[5]["block"] is None                                # a waiting companion arrives as infill
    # a second year brings the third block home: the block is built and the waiting companion dealt to it
    two = growth.plan_years(net, laterals, [_add(2, 1, 2, 1), _add(0, 0, 1, 0)], *args, ["b"])
    assert two[:3] == one[:3]                                     # the units that are not waiting are kept
    assert brief(two[3:]) == [("block", 2, 1), ("companion", 2, 2)]
    assert two[3]["attach"] == "b" and two[4]["block"] == 1 and not two[4]["waiting"]
    # the k-th companion: its bound is k x the mean floor area, and no business is copied twice
    comps = [e for e in growth.plan_years(net, laterals, [_add(0, 2), _add(0, 2), _add(0, 2)], *args)
             if e["event"] == "companion"]
    assert [e["k"] for e in comps] == [1, 2, 3, 4, 5, 6] and [e["year"] for e in comps] == [1, 1, 2, 2, 3, 3]
    assert [e["bound"] for e in comps] == [3500.0 * k for k in range(1, 7)]
    assert [e["pool"] for e in comps] == [3, 6, 6, 6, 6, 6]
    assert all(BIZ[e["template"]]["sqft"] <= e["bound"] for e in comps)
    assert sorted(e["template"] for e in comps) == sorted(BIZ)
    # dealing: the j-th dealt companion goes to block ((j - 1) mod B) + 1, B the blocks built by then
    deal = growth.plan_years(net, laterals, [_add(0, 0, 3, 2), _add(0, 0, 3, 2)], *args, ["a", "c"])
    assert [(e["k"], e["year"], e["block"]) for e in deal if e["event"] == "companion"] == \
        [(1, 1, 1), (2, 1, 1), (3, 2, 1), (4, 2, 2)]
    both = growth.plan_years(net, laterals, [_add(0, 0, 6, 5)], *args, ["a", "c"])
    assert [e["block"] for e in both if e["event"] == "companion"] == [1, 2, 1, 2, 1]
    # a block without an attach bus is not built: its homes arrive as infill, marked remainder
    far = [dict(laterals[0], tap="c")]                            # a reach of about 580 m
    events = growth.plan_years(net, far, [_add(1, 0, 6, 0)], *args)
    assert [(e["event"], e.get("attach") is not None) for e in events if e["event"] == "block"] == \
        [("block", True), ("block", False)]
    homes = [e for e in events if e["event"] == "home"]
    assert [(e["position"], e["remainder"], e["waiting"]) for e in homes] == \
        [(1, False, False), (2, True, False), (3, True, False), (4, True, False)]
    # no template fits and no block is built: block homes and block companions all wait
    events = growth.plan_years(net, laterals, [_add(0, 0, 2, 1)], *args)
    assert [(e["event"], e["waiting"]) for e in events] == [("home", True), ("home", True), ("companion", True)]
    # an empty pool leaves the companion without a template; it keeps its number
    events = growth.plan_years(net, laterals, [_add(0, 2)], order, [], {}, [], seed)
    assert [(e["k"], e["template"], e["pool"]) for e in events] == [(1, None, 0), (2, None, 0)]


def test_plans_nest_across_horizons():
    """The events of a 5-year plan that are not waiting open the 10-year and 20-year plans."""
    net, _, _ = _net()
    laterals = growth.find_laterals(net)
    mixed = dict(laterals[0], kind="mixed", businesses=1, customers=laterals[0]["customers"] + ["biz2"], root="lx")
    seed = growth.growth_seed(555, "uhs13_1247", "uhs13_1247--udt4015")
    order = growth.seeded_order([f"load_h{i}" for i in range(494)], "infill_homes", seed)
    for share in (1.0, 0.25, 0.07):
        plans = {}
        for years in (5, 10, 20):
            adds = growth.year_additions(494, 6, MODERATE, years, "national", NATIONAL, share)
            plans[years] = growth.plan_years(net, laterals + [mixed], adds, order, sorted(BIZ), BIZ, [], seed)
        for short, long in ((5, 10), (10, 20), (5, 20)):
            kept = [e for e in plans[short] if not e.get("waiting")]
            assert kept == plans[long][:len(kept)]
            assert all(e["year"] <= short for e in kept)
            assert all(e["waiting"] for e in plans[short][len(kept):])


def test_named_load_rules():
    net, tr_map, served = _net()
    seed = growth.growth_seed(555, "sub", "feeder")
    buses = growth.three_phase_mv_buses(net)
    # the bus: given, seeded, strongest (lowest impedance from the source) or weakest
    assert growth.named_bus(net, "seeded", "named_bus_1_1", seed, "B") == ("b", "given")
    assert _raises(growth.named_bus, net, "seeded", "named_bus_1_1", seed, "l1")
    assert _raises(growth.named_bus, net, "seeded", "named_bus_1_1", seed, "nowhere")
    bus, why = growth.named_bus(net, "seeded", "named_bus_1_1", seed)
    assert bus in buses and why == "seeded"
    assert growth.named_bus(net, "seeded", "named_bus_1_1", seed) == (bus, why)   # the draw keeps its value
    assert growth.named_bus(net, "strongest", "x", seed) == ("a", "strongest")
    assert growth.named_bus(net, "weakest", "x", seed) == ("c", "weakest")
    z1 = abs(complex(0.15, 0.4))
    assert math.isclose(growth.path_impedance(net, "a"), 0.1 * z1)
    assert math.isclose(growth.path_impedance(net, "c"), 0.6 * z1)
    assert math.isclose(growth.path_length_m(net, "c"), 600.0)
    # the template: the business whose SMART-DS kW is closest to the new load's peak
    assert growth.named_template(net, 90.0, tr_map, served)[0] == "load_c1"
    assert growth.named_template(net, 420.0, tr_map, served)[0] == "load_c2"
    assert growth.named_template(net, 5000.0, tr_map, served)[0] == "load_m1"
    # the transformer: the smallest rating at or above the peak kVA, else the largest
    t3 = next(t for t in net["transformers"] if t["name"] == "t3")
    assert [growth.pick_transformer(net, t3, kva)[0]["name"] for kva in (100.0, 150.0, 151.0, 500.0)] == \
        ["t3", "t3", "t4", "t4"]
    assert growth.pick_transformer(net, t3, 600.0) == (next(t for t in net["transformers"] if t["name"] == "t4"), False)
    assert growth.pick_transformer(net, t3, 100.0)[1] is True
    # the connection behind a transformer: a transformer of the chosen rating and the template's secondary
    template, conn = growth.named_template(net, 140.0, tr_map, served)
    new = growth.connect_named(net, "n1x1", template, conn, "a", 420.0, "com_kw_g77_pu")
    assert new["pattern"] == "transformer" and new["transformer"] == "t4_gn1x1" and new["transformer_kva"] == 500.0
    assert "wdg=1 conn=wye bus=a Kv=12.47 kva=500.0" in new["transformers"][0]
    assert "bus=t3lv_gn1x1 " in new["transformers"][0] and "XHL=5.0" in new["transformers"][0]
    assert new["lines"] == ["New Line.s4_gn1x1 Units=km Length=0.01 bus1=t3lv_gn1x1.1.2.3 bus2=c1_gn1x1.1.2.3 "
                            "switch=n enabled=y phases=3 Linecode=LV3"]
    assert [(ld["name"], ld["bus1"], ld["yearly"]) for ld in new["loads"]] == [
        ("load_c1_gn1x1", "c1_gn1x1.1.2.3", "com_kw_g77_pu")]
    # a medium-voltage template: a copy of its line from the chosen bus
    template, conn = growth.named_template(net, 5000.0, tr_map, served)
    new = growth.connect_named(net, "n1x2", template, conn, "c", 5200.0, "com_kw_10_pu")
    assert new["pattern"] == "mv_line" and new["transformers"] == []
    assert new["lines"][0].startswith("New Line.mvc_gn1x2 Units=km Length=0.03 bus1=c.1.2.3 bus2=m1_gn1x2.1.2.3")


def test_named_load_at_medium_voltage():
    """A named load whose template sits behind a service transformer and that no transformer
    of the feeder can carry connects at medium voltage on a new line and bus of its own."""
    net, tr_map, served = _net()
    assert net["base_kv"] == 12.47
    mv_lines = [growth.customer_connection(net, b, tr_map, served)["line"] for b in ("load_m1",)]
    template, conn = growth.named_template(net, 140.0, tr_map, served)
    assert template == "load_c1" and conn["pattern"] == "transformer"
    # a load a transformer can carry keeps the transformer pattern
    kept = growth.connect_named(net, "n1x1", template, conn, "a", 420.0, "com_kw_g77_pu", mv_lines, 269.0)
    assert kept["pattern"] == "transformer" and kept["large_enough"] and kept["mv"] is None
    assert kept == growth.connect_named(net, "n1x1", template, conn, "a", 420.0, "com_kw_g77_pu")
    # above every rating (500 kVA): pattern mv_new, the feeder's median length (one customer, 30 m)
    new = growth.connect_named(net, "n1x1", template, conn, "a", 600.0, "com_kw_g77_pu", mv_lines, 269.0)
    assert new["pattern"] == "mv_new" and new["transformers"] == [] and new["transformer"] == ""
    assert not new["large_enough"] and new["transformer_kva"] is None
    assert new["lines"] == ["New Line.s4_gn1x1 Units=m Length=30.0 bus1=a.1.2.3 bus2=c1_gn1x1.1.2.3 switch=n "
                            "enabled=y phases=3 Linecode=3P"]
    assert new["loads"] == [{"name": "load_c1_gn1x1", "template": "load_c1", "bus1": "c1_gn1x1.1.2.3",
                             "base": "load_c1_gn1x1", "yearly": "com_kw_g77_pu", "mv_new": 12.47,
                             "templates": ["load_c1"]}]
    assert new["buses"] == {"c1_gn1x1": "c1"}
    mv = new["mv"]
    assert math.isclose(mv["peak_amps"], 600.0 / (math.sqrt(3.0) * 12.47))
    # no overhead code on this feeder: the choice is over all three-phase medium-voltage codes
    assert (mv["linecode"], mv["normamps"], mv["carries"], mv["length_m"], mv["length_rule"]) == \
        ("3P", 400.0, True, 30.0, "feeder_median")
    # the new line reads back as a three-phase medium-voltage line of 30 m
    line = growth.read_feeder(dict(TEXTS, **{"lines.dss": LINES + new["lines"][0] + "\n"}))["lines"][-1]
    assert (line["b1"], line["b2"], line["phases"], line["length_m"], line["linecode"]) == \
        ("a", "c1_gn1x1", 3, 30.0, "3p")
    # a feeder without a medium-voltage customer takes named_load_mv_line_m
    assert growth.mv_new_line(net, [], 600.0, 269.0)["length_m"] == 269.0
    assert growth.mv_new_line(net, [], 600.0, 269.0)["length_rule"] == "named_load_mv_line_m"
    two = growth.mv_new_line(net, [{"length_m": 100.0}, {"length_m": 300.0}], 600.0, 269.0)
    assert two["length_m"] == 200.0 and two["length_rule"] == "feeder_median"
    # overhead codes: the smallest normamps at or above the peak current; the largest when none is
    codes = LINECODES + (
        "New Linecode.3P_OH_A units=km nphases=3 Rmatrix=(0.2 ) Xmatrix=(0.6 ) normamps=20.0\n"
        "New Linecode.3P_OH_B units=km nphases=3 Rmatrix=(0.2 ) Xmatrix=(0.6 ) normamps=30.0\n"
        "New Linecode.3P_UG_C units=km nphases=3 Rmatrix=(0.2 ) Xmatrix=(0.6 ) normamps=28.0\n")
    lines = LINES.replace("bus2=b.1.2.3 switch=n enabled=y phases=3 Linecode=3P", "bus2=b.1.2.3 switch=n "
                          "enabled=y phases=3 Linecode=3P_OH_A")
    lines = lines.replace("bus2=c.1.2.3 switch=n enabled=y phases=3 Linecode=3P", "bus2=c.1.2.3 switch=n "
                          "enabled=y phases=3 Linecode=3P_OH_B")
    lines = lines.replace("bus2=m1.1.2.3 switch=n enabled=y phases=3 Linecode=3P", "bus2=m1.1.2.3 switch=n "
                          "enabled=y phases=3 Linecode=3P_UG_C")
    oh = growth.read_feeder(dict(TEXTS, **{"lines.dss": lines, "linecodes.dss": codes}))
    pick = growth.mv_new_line(oh, [], 600.0, 269.0)                      # 27.8 A: above A, the UG code is no choice
    assert (pick["linecode"], pick["normamps"], pick["carries"]) == ("3P_OH_B", 30.0, True)
    pick = growth.mv_new_line(oh, [], 400.0, 269.0)                      # 18.5 A
    assert (pick["linecode"], pick["normamps"], pick["carries"]) == ("3P_OH_A", 20.0, True)
    pick = growth.mv_new_line(oh, [], 700.0, 269.0)                      # 32.4 A: none carries it
    assert (pick["linecode"], pick["normamps"], pick["carries"]) == ("3P_OH_B", 30.0, False)
    assert _raises(growth.mv_new_line, dict(net, base_kv=None), [], 600.0, 269.0)
    # a medium-voltage template keeps the copy of its own line
    template, conn = growth.named_template(net, 5000.0, tr_map, served)
    new = growth.connect_named(net, "n1x2", template, conn, "c", 9000.0, "com_kw_10_pu", mv_lines, 269.0)
    assert new["pattern"] == "mv_line" and new["mv"] is None
    assert new["lines"][0].startswith("New Line.mvc_gn1x2 Units=km Length=0.03 bus1=c.1.2.3 bus2=m1_gn1x2.1.2.3")
    # the Load line Phase 7b writes for pattern mv_new
    text = growth.mv_load_line("New Load.load_c1 conn=wye bus1=c1.1.2.3 kV=0.48 Vminpu=0.8 Vmaxpu=1.2 model=1 "
                               "kW=1 kvar=1 Phases=3 daily=com_kw_11_pu", "load_c1_gn1x1", "c1_gn1x1.1.2.3", 12.47,
                               0.5 * 1.25, 1.25, "com_kw_g77_pu")
    assert text == ("New Load.load_c1_gn1x1 conn=wye bus1=c1_gn1x1.1.2.3 kV=12.47 Vminpu=0.8 Vmaxpu=1.2 model=1 "
                    "kW=0.625 kvar=1.25 Phases=3 daily=com_kw_g77_pu")
    load = growth.read_feeder(dict(TEXTS, **{"loads.dss": text.replace("daily=", "yearly=")}))["loads"][0]
    assert (load["bus"], load["kv"], load["phases"], load["base"]) == ("c1_gn1x1", 12.47, 3, "load_c1_gn1x1")


def test_named_candidates_and_stops():
    final = [{"bldg_id": "11.0", "in.comstock_building_type": "Hospital"},
             {"bldg_id": "12", "in.comstock_building_type": "SmallOffice"}]
    header = ["bldg_id", "in.comstock_building_type", "in.building_america_climate_zone"]
    metadata = [dict(zip(header, row)) for row in (("21", "Hospital", "Hot-Humid"), ("22", "Hospital", "Hot-Dry"),
                                                   ("23", "PrimarySchool", "Hot-Humid"))]

    def never():
        raise AssertionError("the metadata is read only when the selection has no building of the type")

    found, source = growth.named_candidates(final, never, "Hospital", "Hot-Humid", "TX")
    assert list(found) == ["11"] and source == "phase4_selection"
    # no building of the type in the selection: the metadata, in the circuit's most common zone
    found, source = growth.named_candidates(final[1:], lambda: (header, metadata), "Hospital", "Hot-Humid", "TX")
    assert list(found) == ["21"] and source == "metadata_zone"
    # stops: none in that zone, and metadata without the zone column
    for args in ((lambda: (header, metadata), "Hospital", "Marine"),
                 (lambda: (header, metadata), "SecondarySchool", "Hot-Humid"),
                 (lambda: (header[:2], metadata), "Hospital", "Hot-Humid")):
        try:
            growth.named_candidates(final[1:], args[0], args[1], args[2], "TX")
        except growth.GrowthError as e:
            assert args[1] in str(e) and "TX" in str(e) and args[2] in str(e)
        else:
            raise AssertionError("expected a stop")
    seed = growth.growth_seed(555, "sub", "feeder")
    ids = {"21": 0, "22": 0, "30": 0}
    assert growth.named_building(ids, "named_building_1_1", seed) in ids
    assert growth.named_building(ids, "named_building_1_1", seed) == growth.named_building(ids, "named_building_1_1", seed)


# ---------------------------------------------------------------------------
# Seeds and nesting (L22, L23, L25)
# ---------------------------------------------------------------------------
def test_infill_draws_nest_across_horizons():
    homes = [f"load_h{i}" for i in range(494)]
    seed = growth.growth_seed(555, "uhs13_1247", "uhs13_1247--udt4015")
    assert seed == 555 + growth._stable_seed_offset("uhs13_1247|uhs13_1247--udt4015")
    order = growth.seeded_order(homes, "infill_homes", seed)
    assert sorted(order) == sorted(homes) and order != sorted(homes)
    five, ten = growth.take(order, 20), growth.take(order, 40)
    assert ten[:20] == five and len(set(ten)) == 40                      # the longer horizon holds the shorter
    # a draw has its own name: another draw on the same seed is another order, and adding it moves nothing
    assert growth.seeded_order(homes, "infill_companions", seed) != order
    assert growth.seeded_order(homes, "infill_homes", seed) == order
    assert growth.seeded_order(homes, "infill_homes", seed + 1) != order
    # past the end of the order it starts again
    assert growth.take(["a", "b"], 5) == ["a", "b", "a", "b", "a"] and growth.take([], 3) == []


def test_existing_draws_are_those_of_a_run_without_growth():
    """New loads never enter an existing shuffle: the heating labels and the EV, PV and
    storage hosts of the existing customers come from the same calls on the existing
    customers alone, and the new loads have draws of their own."""
    bases = {f"load_{i}" for i in range(40)}
    base_to_daily = {b: {f"res_kw_{i % 7}_pu"} for i, b in enumerate(sorted(bases))}
    shares = {"baseline": 0.5, "dm": 0.3, "un": 0.2}
    before = split_heating(bases, base_to_daily, shares, 123, "sub", "feeder", unit="building")
    new_labels = growth.label_new_shapes(["com_kw_g1_pu", "com_kw_g2_pu", "com_kw_g3_pu"], shares,
                                         123 + before["mix_seed_offset"])
    after = split_heating(bases, base_to_daily, shares, 123, "sub", "feeder", unit="building")
    assert after["daily_to_scen"] == before["daily_to_scen"] and after["bases"] == before["bases"]
    assert set(new_labels) == {"com_kw_g1_pu", "com_kw_g2_pu", "com_kw_g3_pu"}
    assert sorted(new_labels.values()) == ["baseline", "dm", "un"]          # largest remainder, one each
    assert growth.label_new_shapes([], shares, 1) == {}
    # no minimum of one for the new loads: 1 % of 10 new homes is no host
    new_homes = [f"load_{i}_gh{i}" for i in range(10)]
    assert growth.pick_new(new_homes, 0.01, "growth_ev_hosts", 99) == []
    assert len(growth.pick_new(new_homes, 0.26, "growth_ev_hosts", 99)) == 3
    assert set(growth.pick_new(new_homes, 1.0, "growth_ev_hosts", 99)) == set(new_homes)
    assert segment_count(0.01, 10, True) == 1 and segment_count(0.01, 10, True, min_one=False) == 0
    assert segment_count(0.26, 10, True, min_one=False) == 3 and segment_count(0.5, 10, False, min_one=False) == 0
    # PV and storage hosts among the existing customers: the same call gives the same hosts
    existing = sorted(bases)
    pv, sto = pick_hosts(existing, 8, 4, 123, 123, 77, "with_pv")
    pv_new, sto_new = pick_hosts(new_homes, 3, 1, 123 + growth._stable_seed_offset("growth_pv_hosts"),
                                 123 + growth._stable_seed_offset("growth_storage_hosts"), 77, "with_pv")
    assert pick_hosts(existing, 8, 4, 123, 123, 77, "with_pv") == (pv, sto)
    assert set(pv_new) <= set(new_homes) and not set(pv_new) & set(existing)
    # EV cars: the cars of the existing hosts are built on the existing hosts alone; the cars of
    # the new hosts on a seed of their own
    pool = pd.DataFrame({"session_id": range(1, 51), "energy_kwh": [8.0 + i for i in range(50)],
                         "charge_h": [2.0] * 50, "start_min": [1000.0 + 5 * i for i in range(50)],
                         "plug_min": [600.0] * 50})
    inputs = {"level2_kw": 7.2, "level1_kw": 1.0}
    hosts = existing[:12]
    alone = evwatts_cars("uncontrolled", hosts, pool, 0.6, 0.8, inputs, 4242)
    new_seed = ev_draw_seed("growth_new_loads", 4242)
    assert new_seed != 4242
    new_cars = evwatts_cars("uncontrolled", new_homes[:5], pool, 0.6, 0.8, inputs, new_seed)
    again = evwatts_cars("uncontrolled", hosts, pool, 0.6, 0.8, inputs, 4242)
    assert [(c["host"], c["source_id"], c["level"], c["charges_today"]) for c in alone] == \
        [(c["host"], c["source_id"], c["level"], c["charges_today"]) for c in again]
    assert len(new_cars) == 5 and {c["host"] for c in new_cars} == set(new_homes[:5])
