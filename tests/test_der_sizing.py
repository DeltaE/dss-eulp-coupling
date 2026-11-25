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
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from der_sizing import (FT2_TO_M2, annual_yield, der_choice, der_number, der_switch, der_value,  # noqa: E402
                        pick, pick_hosts, pv_kw_roof_and_use, roof_area_m2, segment_count, standby_pct,
                        storage_size)
from growth import der_use_factor  # noqa: E402

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



def test_window_choices_and_helpers():
    """schedule_start takes best_window; a loadshape name gives its building as text; the
    peak of a profile of several days is read on one day (tests/test_multi_day.py)."""
    from der_sizing import CHOICES, day_peak, loadshape_building
    assert der_choice({"der_sizing": {"schedule_start": "best_window"}}, "schedule_start") == "best_window"
    assert _stops(der_choice, {"der_sizing": {"schedule_start": "window"}}, "schedule_start")
    assert CHOICES["schedule_start"] == ("best", "best_window", "fixed")
    assert loadshape_building("res_kw_9312-North_pu") == ("res", "9312-North")
    assert loadshape_building("com_kw_12815_pu") == ("com", "12815")
    assert day_peak([1.0] * 96 + [3.0] * 96) == 3.0 and day_peak([1.0] * 96 + [3.0] * 96, 0) == 1.0


def test_sizes_under_load_growth():
    """der_resize_with_growth: an existing host keeps the size of a run without growth
    unless the setting is true; a new host is sized on its grown use in both cases."""
    new = {"load_9_gh1"}
    factor = 1.03 ** 10
    assert der_use_factor("load_1", factor, new, False) == 1.0
    assert der_use_factor("load_1", factor, new, True) == factor
    assert der_use_factor("load_9_gh1", factor, new, False) == factor
    assert der_use_factor("load_9_gh1", factor, new, True) == factor
    # the use cap binds (a large roof): the size follows the use that sizes it
    use, yld = 12000.0, 1500.0
    without = pv_kw_roof_and_use(400.0, 0.5, 0.2, 1.0, use, yld)[0]
    assert without == 8.0
    existing_off = pv_kw_roof_and_use(400.0, 0.5, 0.2, 1.0, use * der_use_factor("load_1", factor, new, False), yld)
    existing_on = pv_kw_roof_and_use(400.0, 0.5, 0.2, 1.0, use * der_use_factor("load_1", factor, new, True), yld)
    new_host = pv_kw_roof_and_use(400.0, 0.5, 0.2, 1.0, use * der_use_factor("load_9_gh1", factor, new, False), yld)
    assert existing_off[0] == without                                     # the size of a run without growth
    assert math.isclose(existing_on[0], 8.0 * factor) and new_host == existing_on
    # the roof binds: the size is the roof's under both values
    small_roof = [pv_kw_roof_and_use(20.0, 0.5, 0.2, 1.0, use * f, yld) for f in (1.0, factor)]
    assert small_roof[0][0] == small_roof[1][0] == 2.0 and small_roof[1][3]
    # the storage size follows the PV size
    assert storage_size(existing_off[0], 1.0, 0.5, 100.0, 2.0) == storage_size(without, 1.0, 0.5, 100.0, 2.0)


def test_peak_ratio_under_load_growth():
    """pv_rule peak_ratio with load growth: the peak that sizes a host is its day X peak x
    the factor of its annual use (der_use_factor), as the deploy's host_sizes takes it: an
    existing host keeps the peak of a run without growth unless der_resize_with_growth is
    true; a new host is sized on its grown peak in both cases."""
    from der_sizing import day_peak
    new = {"load_9_gh1"}
    factor, day_x = 1.05 ** 20, day_peak([20.0] * 96 + [40.0] * 96 + [10.0] * 96, 1)
    assert day_x == 40.0
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    pv_per, pv_min = der_number(cfg, "pv_kw_per_peak_kw"), der_number(cfg, "pv_min_kw")
    st_per, st_min = der_number(cfg, "storage_kw_per_peak_kw"), der_number(cfg, "storage_min_kw")

    def sizes(base, resize):
        pk = day_x * der_use_factor(base, factor, new, resize)
        return pk, max(pv_min, round(pv_per * pk, 1)), max(st_min, round(st_per * pk, 3))

    assert sizes("load_1", False) == (40.0, max(pv_min, round(pv_per * 40.0, 1)), max(st_min, round(st_per * 40.0, 3)))
    assert math.isclose(sizes("load_1", True)[0], 40.0 * factor)
    assert sizes("load_9_gh1", False) == sizes("load_9_gh1", True) == sizes("load_1", True)
    assert sizes("load_1", True)[1] > sizes("load_1", False)[1] and sizes("load_1", True)[2] > sizes("load_1", False)[2]
    # the deploy multiplies the peak of peak_kw_for_load by the factor it puts on the annual use
    with open(os.path.join(REPO_ROOT, "7_circuit_instantiation", "power_flow_sim_daily_EV_STO_DG_deploy.py"),
              encoding="utf-8") as f:
        deploy = f.read()
    assert "pk = peak_kw_for_load(base) * use_factor" in deploy
    assert "host_sizes(b, seg, bldg_of_host, annual_yield_kwh_per_kw, use_factor)" in deploy


def _deploy_sizing(profiles, resize, new_customers=()):
    """host_sizes and peak_kw_for_load of the deploy, taken from its source text, with
    pv_rule peak_ratio, load growth on and the loadshape CSVs of the folder profiles.
    Host load_s (stretched) points at its own loadshape res_kw_1x1_pu, stretched from
    res_kw_1_pu; host load_o (ordinary) points at res_kw_2_pu. Three days, day X second.
    Returns size(base), the der_hosts.csv row of a host with factor 1.10."""
    import ast
    import re
    import pandas as pd
    from der_sizing import day_peak
    path = os.path.join(REPO_ROOT, "7_circuit_instantiation", "power_flow_sim_daily_EV_STO_DG_deploy.py")
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    seg = "residential"
    ns = {"os": os, "re": re, "sys": sys, "pd": pd, "day_peak": day_peak, "roof_area_m2": roof_area_m2,
          "read_lines": None, "try_float": None,
          "PROFILES_PATH": profiles, "HORIZON_DAYS": 3, "X_INDEX": 1, "IRRADIANCE_NPTS": 96,
          "PATH_LOADS_DSS_ORIG": os.path.join(profiles, "no_such_Loads_original.dss"),
          "PEAK_FROM_ORIGINAL_KW": [],
          "base_to_daily": {"load_s": {"res_kw_1x1_pu"}, "load_o": {"res_kw_2_pu"}},
          "GROWTH": {"shape_building": {"res_kw_1x1_pu": "res_kw_1_pu"}},
          "GROWTH_SETTINGS": {"der_resize_with_growth": resize}, "NEW_CUSTOMERS": set(new_customers),
          "SIZE": {seg: {"roof_tilt_deg": 20.0, "inverter_loading_ratio": 1.2}},
          "PV_HOSTS": {seg: ["load_s", "load_o"]}, "STORAGE_HOSTS": {seg: ["load_s", "load_o"]},
          "PV_RULE": {seg: "peak_ratio"}, "SIZING_CASE": "moderate",
          "PV_KW_PER_PEAK": der_number(cfg, "pv_kw_per_peak_kw"), "PV_MIN_KW": der_number(cfg, "pv_min_kw"),
          "STORAGE_KW_PER_PEAK": der_number(cfg, "storage_kw_per_peak_kw"),
          "STORAGE_MIN_KW": der_number(cfg, "storage_min_kw"),
          "STORAGE_ENERGY_HOURS": der_number(cfg, "storage_hours"), "STORAGE_PF": der_number(cfg, "storage_pf")}
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in ("host_sizes", "peak_kw_for_load"):
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)

    def size(base):
        use_factor = der_use_factor(base, 1.10, set(new_customers), resize)
        bldg = {"loadshape": "", "bldg_id": 1, "floor_ft2": 2000.0, "stories": 1.0, "building_type": "x",
                "annual_use_kwh": 10000.0 * use_factor, "roof_column": 1000.0}
        return ns["host_sizes"](base, seg, bldg, 1500.0, use_factor)
    return size


def _readme_loadshapes(folder):
    """README's worked example on made-up loadshapes: res_kw_1_pu with a day X peak of
    900 kW (mean 650 kW) and its stretch a x old + b with a 1.82 and b -468 (factor 1.10,
    peak_factor 1.30), day X peak 1,170 kW; res_kw_2_pu equal to res_kw_1_pu. Day 3 holds
    a higher value, so a peak of the window would show."""
    old = [500.0] * 96 + [400.0] * 48 + [900.0] * 48 + [950.0] * 96
    for name, values in (("res_kw_1_pu", old), ("res_kw_1x1_pu", [1.82 * v - 468.0 for v in old]),
                         ("res_kw_2_pu", old)):
        with open(os.path.join(folder, f"{name}.csv"), "w", encoding="utf-8") as f:
            f.write("".join(f"{v!r}\n" for v in values))


def test_peak_ratio_stretched_host_sized_once():
    """pv_rule peak_ratio with load growth (README "Load growth", worked example): a
    stretched customer is sized on the day X peak of the loadshape it was stretched from
    under der_resize_with_growth false (900 kW) and on its own loadshape under true
    (1,170 kW), with no further factor; an ordinary host with the same factor 1.10 keeps
    peak x factor (900 kW and 990 kW). PV kW is 0.30 x peak and storage kW 0.75 x peak."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        _readme_loadshapes(folder)
        false, true = _deploy_sizing(folder, False), _deploy_sizing(folder, True)
        for size, base, peak in ((false, "load_s", 900.0), (true, "load_s", 1170.0),
                                 (false, "load_o", 900.0), (true, "load_o", 990.0)):
            row = size(base)
            assert math.isclose(row["peak_kw"], peak), (base, row["peak_kw"], peak)
            assert row["pv_kw"] == round(0.30 * peak, 1), (base, row["pv_kw"])
            assert row["storage_kw"] == round(0.75 * peak, 3), (base, row["storage_kw"])
        # a new stretched customer is sized on its own loadshape under false too
        assert math.isclose(_deploy_sizing(folder, False, {"load_s"})("load_s")["peak_kw"], 1170.0)


def test_peak_ratio_stretched_host_missing_csv_stops():
    """The loadshape CSV a stretched host is sized on is missing: [FAIL] and exit 1."""
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        _readme_loadshapes(folder)
        os.remove(os.path.join(folder, "res_kw_1_pu.csv"))
        assert _stops(_deploy_sizing(folder, False), "load_s")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
