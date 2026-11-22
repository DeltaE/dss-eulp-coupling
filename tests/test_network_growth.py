# -*- coding: utf-8 -*-
"""
Tests of network growth driven by the planning limits: the settings of network_growth in
growth.yaml (pipeline_utils) and the rules of
7_circuit_instantiation/deployer_modules/network_growth.py on one small synthetic feeder
and hand-made tables. No OpenDSS and no pipeline run.
"""

import copy
import json
import math
import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
sys.path.insert(0, os.path.join(REPO_ROOT, "8_results_analysis"))
from pipeline_utils import (growth_settings, load_growth, network_growth_items, network_growth_on,  # noqa: E402
                            network_item_error)
import growth  # noqa: E402
import network_growth as ng  # noqa: E402
import planning_limits as pl  # noqa: E402

DEFAULTS = load_growth(settings_dir="")
LIMITS = {"line_limit_percent": 100, "head_limit_percent": 100, "transformer_limit_percent": 100,
          "substation_limit_percent": 100}
NG = dict(growth_settings(DEFAULTS)["network_growth"])
# the settings that build nothing at a regulator: no regulator_rating step, no new feeder on a regulator head
NG_T = dict(NG, steps=["new_feeder", "reconductor", "service_transformer", "regulator"], new_feeder_regulator="skip")
DATES = ["2018-06-16"]

# ---------------------------------------------------------------------------
# A small synthetic feeder: a three-phase main src-a-b-c-d-e-f with two switches, a
# branch a-x-y behind a third switch, three single-phase laterals and one business
# ---------------------------------------------------------------------------
LINECODES = """New Linecode.3P_OH_A units=km nphases=3 Rmatrix=(0.2 ) Xmatrix=(0.6 ) normamps=100.0
New Linecode.3P_OH_B units=km nphases=3 Rmatrix=(0.2 ) Xmatrix=(0.6 ) normamps=200.0
New Linecode.1P_OH_X units=km nphases=1 Rmatrix=(0.5 ) Xmatrix=(0.7 ) normamps=50.0
New Linecode.LV_TRI units=km nphases=2 Rmatrix=(0.9 0.3 | 0.3 0.9 ) Xmatrix=(0.5 0.4 | 0.4 0.5 ) normamps=200.0
New Linecode.LV3 units=km nphases=3 Rmatrix=(0.3 ) Xmatrix=(0.3 ) normamps=300.0
"""
LINES = """New Line.head Units=km Length=0.1 bus1=src.1.2.3 bus2=a.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_B
New Line.m1 Units=km Length=0.2 bus1=a.1.2.3 bus2=b.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_B
New Line.sw1 Units=km Length=0.001 bus1=b.1.2.3 bus2=c.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_B
New Line.m2 Units=km Length=0.3 bus1=c.1.2.3 bus2=d.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_A
New Line.sw2 Units=km Length=0.001 bus1=d.1.2.3 bus2=e.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_B
New Line.m3 Units=km Length=0.1 bus1=e.1.2.3 bus2=f.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_A
New Line.sw3 Units=km Length=0.001 bus1=a.1.2.3 bus2=x.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_B
New Line.mx Units=km Length=0.15 bus1=x.1.2.3 bus2=y.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_A
New Line.fz1 Units=km Length=0.001 bus1=b.1 bus2=l1.1 switch=y enabled=y phases=1 Linecode=1P_OH_X
New Fuse.Fuse_fz1 monitoredobj=Line.fz1 enabled=y ratedcurrent=100.0
New Line.lat1 Units=km Length=0.05 bus1=l1.1 bus2=l2.1 switch=n enabled=y phases=1 Linecode=1P_OH_X
New Line.lb Units=km Length=0.08 bus1=d.2 bus2=g.2 switch=n enabled=y phases=1 Linecode=1P_OH_X
New Line.lc Units=km Length=0.06 bus1=y.1 bus2=h.1 switch=n enabled=y phases=1 Linecode=1P_OH_X
New Line.s1 Units=km Length=0.02 bus1=t1lv.1.2 bus2=h1.1.2 switch=n enabled=y phases=2 Linecode=LV_TRI
New Line.s2 Units=km Length=0.02 bus1=t2lv.1.2 bus2=h2.1.2 switch=n enabled=y phases=2 Linecode=LV_TRI
New Line.s3 Units=km Length=0.02 bus1=t3lv.1.2 bus2=h3.1.2 switch=n enabled=y phases=2 Linecode=LV_TRI
New Line.s5 Units=km Length=0.02 bus1=t5lv.1.2 bus2=h5.1.2 switch=n enabled=y phases=2 Linecode=LV_TRI
New Line.s4 Units=km Length=0.01 bus1=t4lv.1.2.3 bus2=c1.1.2.3 switch=n enabled=y phases=3 Linecode=LV3
New Line.tie Units=km Length=0.001 bus1=f.1.2.3 bus2=zz.1.2.3 switch=y enabled=n phases=3 Linecode=3P_OH_B
"""


def _tr(name, bus, node, kva):
    return (f"New Transformer.{name} phases=1 windings=3 %loadloss=0.8 wdg=1 conn=wye bus={bus}.{node} Kv=7.2 "
            f"kva={kva} %r=0.27 wdg=2 conn=wye bus={name}lv.1.0 Kv=0.12 kva={kva} %r=0.53 wdg=3 conn=wye "
            f"bus={name}lv.0.2 Kv=0.12 kva={kva} %r=0.53 XHL=2.4 XLT=2.4 XHT=1.6\n")


TRANSFORMERS = (_tr("t1", "l1", 1, 25.0) + _tr("t2", "l2", 1, 50.0) + _tr("t3", "g", 2, 25.0)
                + _tr("t5", "h", 1, 25.0)
                + "New Transformer.t4 phases=3 windings=2 %loadloss=1.0 wdg=1 conn=wye bus=f Kv=12.47 kva=150.0 "
                  "%r=0.5 wdg=2 conn=wye bus=t4lv Kv=0.48 kva=150.0 %r=0.5 XHL=4.0\n")


def _home(n):
    return "".join(f"New Load.load_h{n}_{leg} conn=wye bus1=h{n}.{leg} kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=1.0 "
                   f"kvar=0.2 Phases=1 yearly=res_kw_{n}_pu\n" for leg in (1, 2))


LOADS = (_home(1) + _home(2) + _home(3) + _home(5)
         + "New Load.load_c1 conn=wye bus1=c1.1.2.3 kV=0.48 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=100.0 kvar=30.0 "
           "Phases=3 yearly=com_kw_11_pu\n")
MASTER = """Clear

New Circuit.feeder_t bus1=src pu=1.03 basekV=12.47 R1=1e-05 X1=1e-05 R0=1e-05 X0=1e-05

Redirect LineCodes.dss
Redirect Lines.dss
Redirect Transformers.dss
Redirect Loads.dss
Redirect Capacitors.dss
new monitor.m1 element=Line.head mode=0
new monitor.m2 element=Line.head mode=1
new energymeter.m3 Line.head

Solve mode=daily stepsize=15m number=96
Export monitors m1
Export monitors m2
"""
CAPACITORS = "New Capacitor.cap1 bus1=h.1 phases=1 Kv=7.2 conn=Wye Kvar=50.0\n"
BUSCOORDS = "src 0.0 0.0\na 0.001 0.0\nb 0.003 0.0\nc 0.003 0.0001\n"
FILES = {"LineCodes.dss": LINECODES, "Lines.dss": LINES, "Transformers.dss": TRANSFORMERS, "Loads.dss": LOADS,
         "Master.dss": MASTER, "Capacitors.dss": CAPACITORS, "Buscoords.dss": BUSCOORDS}
# another feeder folder of the region: a larger three-phase code and a larger transformer
OTHER = {"linecodes.dss": LINECODES + "New Linecode.3P_OH_C units=km nphases=3 Rmatrix=(0.1 ) Xmatrix=(0.5 ) "
                                      "normamps=400.0\n",
         "lines.dss": "New Line.o1 Units=km Length=0.5 bus1=src.1.2.3 bus2=o.1.2.3 switch=n enabled=y phases=3 "
                      "Linecode=3P_OH_C\nNew Line.o2 Units=km Length=0.0005 bus1=o.1.2.3 bus2=p.1.2.3 switch=y "
                      "enabled=y phases=3 Linecode=3P_OH_A\n",
         "transformers.dss": _tr("big", "o", 1, 75.0) + _tr("same", "o", 1, 50.0).replace("%loadloss=0.8",
                                                                                       "%loadloss=0.9"),
         "loads.dss": "", "master.dss": "New Circuit.other bus1=src basekV=12.47\n"}
SUBSTATION = {"transformers": [{"name": "sub_1", "kva": 40000.0}],
              "regcontrol": {"vreg": 123.6, "band": 1.992, "ptratio": 60.0}}
EXPRESS = {"linecode": "3P_OH_B", "normamps": 200.0}


def _text(files=FILES):
    return "\n".join(files[name] for name in sorted(files))


def _own(files=FILES):
    return ng.inventory({name.lower(): text for name, text in files.items()})


def _catalog(region=False):
    return ng.build_catalog(_own(), [ng.inventory(OTHER)] if region else [])


def _head(amps, percent=None, step=5, line="head", k=1, normamps=200.0):
    top = max(amps.values())
    measure = 100.0 * top / normamps if percent is None else percent
    return {"head": k, "line": line, "linecode": "3p_oh_b", "normamps": normamps, "kva_percent": measure,
            "phase_percent": measure, "phase_step": step, "amps_1": amps[1], "amps_2": amps[2], "amps_3": amps[3]}


def _amps(a, b, c):
    return {1: a, 2: b, 3: c}


def _rows(net, peaks):
    return pl.line_rows(net, {name: (amps, 5) for name, amps in peaks.items()}, DATES)


def _with(**changes):
    g = copy.deepcopy(DEFAULTS)
    for key, value in changes.items():
        g["network_growth"][key] = value
    return g


def _stops(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code == 1
    return False


def _raises(fn, *args):
    try:
        fn(*args)
    except ng.NetworkGrowthError:
        return True
    return False


# ---------------------------------------------------------------------------
# Settings (N1 to N3)
# ---------------------------------------------------------------------------
def test_tracked_network_growth_block():
    g = growth_settings(DEFAULTS)
    assert g["network_growth"] == {
        "mode": "as_needed",
        "steps": ["new_feeder", "reconductor", "service_transformer", "regulator_rating", "regulator"],
        "new_feeder_regulator": "copy",
        "rebalance_phases": False, "open_point": "switch", "head_metric": "largest_phase", "sizing_percent": 75,
        "max_rounds": 5, "catalog": "region", "carry_forward": None, "planned": []}
    assert tuple(g["network_growth"]["steps"]) == ng.STEPS
    # with growth_years 0, the tracked value, no network growth code runs
    assert g["growth_years"] == 0 and not network_growth_on(g)
    on = growth_settings(dict(_with(), growth_years=10))
    assert network_growth_on(on)
    # mode "off": the planning limits are reported and nothing is built
    assert not network_growth_on(growth_settings(dict(_with(mode="off"), growth_years=10)))
    assert growth_settings(_with(max_rounds=0.0))["network_growth"]["max_rounds"] == 0
    assert growth_settings(_with(steps=[]))["network_growth"]["steps"] == []


def test_every_bad_network_growth_value_stops():
    item = {"feeder": "f", "mix": "all", "step": "regulator", "line": "m2"}
    bad = [{"mode": False}, {"mode": True}, {"mode": "on"}, {"mode": None}, {"mode": "planned"},
           {"steps": "reconductor"}, {"steps": ["reconductor", "new_substation"]},
           {"steps": ["regulator", "regulator"]}, {"rebalance_phases": "yes"}, {"rebalance_phases": 1},
           {"open_point": "fuse"}, {"head_metric": "kva"}, {"catalog": "state"},
           {"sizing_percent": 0}, {"sizing_percent": 101}, {"sizing_percent": "75"},
           {"max_rounds": -1}, {"max_rounds": 2.5}, {"max_rounds": None},
           {"carry_forward": ""}, {"carry_forward": 3}, {"planned": None}, {"planned": ["m2"]},
           {"planned": [dict(item, step="new_substation")]}, {"planned": [dict(item, line="")]},
           {"planned": [dict(item, extra=1)]}, {"planned": [{"feeder": "f", "step": "regulator", "line": "m2"}]}]
    for changes in bad:
        assert _stops(growth_settings, _with(**changes)), changes
    g = copy.deepcopy(DEFAULTS)
    del g["network_growth"]
    assert _stops(growth_settings, g)
    # mode planned needs an item: one in planned, or a carry_forward file
    assert growth_settings(_with(mode="planned", planned=[item]))["network_growth"]["mode"] == "planned"
    assert growth_settings(_with(mode="planned", carry_forward="built.yaml"))


def test_items_of_the_built_format(tmp_path):
    good = [{"feeder": "f", "mix": "baseline", "step": "rebalance_phases", "lateral": "h", "to_phase": 2},
            {"feeder": "f", "mix": "baseline", "step": "new_feeder", "open": "sw1"},
            {"feeder": "f", "mix": "all", "step": "new_feeder", "cut_bus": "c"},
            {"feeder": "f", "mix": "baseline", "step": "reconductor", "line": "l(r:a-b)", "linecode": "3P_OH_B",
             "circuits": 2, "round": 1},
            {"feeder": "f", "mix": "baseline", "step": "service_transformer", "transformer": "t1", "kva": 50.0,
             "units": 1},
            {"feeder": "g", "mix": "stress", "step": "regulator", "line": "fz1", "round": "planned"}]
    assert all(network_item_error(i) is None for i in good)
    for item in ({"feeder": "f", "mix": "all", "step": "new_feeder"},
                 {"feeder": "f", "mix": "all", "step": "new_feeder", "open": "a", "cut_bus": "b"},
                 {"feeder": "f", "mix": "all", "step": "rebalance_phases", "lateral": "h", "to_phase": 4},
                 {"feeder": "f", "mix": "all", "step": "reconductor", "line": "m", "linecode": "c", "circuits": 0},
                 {"feeder": "f", "mix": "all", "step": "service_transformer", "transformer": "t", "kva": 0,
                  "units": 1},
                 {"feeder": "", "mix": "all", "step": "regulator", "line": "m"}, "regulator"):
        assert network_item_error(item) is not None, item
    # the round trip: one flow mapping per item, read back as written
    path = tmp_path / ng.BUILT_FILE
    ng.write_built(path, good)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("- {feeder: f, mix: baseline, step: rebalance_phases, lateral: h, to_phase: 2}\n")
    assert len(text.splitlines()) == len(good) and ng.read_built(path) == good
    ng.write_built(path, [dict(good[1], _peak=3.0)])
    assert ng.read_built(path) == [good[1]]                       # the keys of the tables are left out
    ng.write_built(tmp_path / "none.yaml", [])
    assert ng.read_built(tmp_path / "none.yaml") == []
    # the items of one circuit folder: its feeder, and its mix or all, in file order
    assert ng.items_for(good, "f", "stress") == [good[2]]
    assert ng.items_for(good, "f", "baseline") == good[:5]
    # carry_forward (relative to the settings folder) first, then planned; round is ignored
    planned = {"feeder": "f", "mix": "all", "step": "regulator", "line": "m2"}
    g = growth_settings(_with(carry_forward=ng.BUILT_FILE, planned=[planned]))
    ng.write_built(path, good)
    items = network_growth_items(g, str(tmp_path))
    assert len(items) == 7 and items[-1] == planned and all("round" not in i for i in items)
    assert items[3] == {k: v for k, v in good[3].items() if k != "round"}
    assert _stops(network_growth_items, growth_settings(_with(carry_forward="missing.yaml")), str(tmp_path))
    path.write_text("- {feeder: f, mix: all, step: regulator}\n", encoding="utf-8")
    assert _stops(network_growth_items, g, str(tmp_path))
    path.write_text("", encoding="utf-8")
    assert _stops(network_growth_items, growth_settings(_with(mode="planned", carry_forward=ng.BUILT_FILE)),
                  str(tmp_path))


# ---------------------------------------------------------------------------
# The catalog (N11)
# ---------------------------------------------------------------------------
def test_catalog_levels_construction_and_scopes(tmp_path):
    assert [ng.construction(c) for c in ("3P_OH_AL_x", "3p_ug_al_500", "padswitch_1")] == ["OH", "UG", ""]
    own = _own()
    # classes: phases, level (medium voltage up to the first transformer) and construction
    assert own["uses"] == {"3|mv|OH": ["3p_oh_a", "3p_oh_b"], "1|mv|OH": ["1p_oh_x"], "2|lv|": ["lv_tri"],
                           "3|lv|": ["lv3"]}
    assert own["linecodes"]["3p_oh_b"]["normamps"] == 200.0
    assert own["linecodes"]["3p_oh_b"]["statement"].startswith("New Linecode.3P_OH_B units=km")
    # the open tie and the switches of 1 m or less give no use; a rating is kept once, the first in file order
    assert [r["kva"] for r in own["transformers"]["1|7.2,0.12,0.12"]] == [25.0, 50.0]
    assert own["transformers"]["1|7.2,0.12,0.12"][0]["statement"].startswith("New Transformer.t1 ")
    feeder = _catalog()
    assert [(e["linecode"], e["normamps"]) for e in feeder["lines"]["3|mv|OH"]] == [("3P_OH_A", 100.0),
                                                                                    ("3P_OH_B", 200.0)]
    region = _catalog(region=True)
    assert [e["linecode"] for e in region["lines"]["3|mv|OH"]] == ["3P_OH_A", "3P_OH_B", "3P_OH_C"]
    assert [e["kva"] for e in region["transformers"]["1|7.2,0.12,0.12"]] == [25.0, 50.0, 75.0]
    # a statement comes from the circuit's own feeder when it has the rating, else from the other folder
    by_kva = {e["kva"]: e["statement"] for e in region["transformers"]["1|7.2,0.12,0.12"]}
    assert "New Transformer.t2 " in by_kva[50.0] and "%loadloss=0.8" in by_kva[50.0]
    assert "New Transformer.big " in by_kva[75.0]
    # the short line of the other folder (0.5 m) is no use of its code
    assert "3p_oh_a" not in ng.inventory(OTHER)["uses"].get("3|mv|OH", [])
    record = ng.substation_record({
        "transformers.dss": "New Transformer.sub_1 phases=3 windings=2 wdg=1 conn=delta Kv=69.0 kva=40000.0 bus=n9 "
                            "wdg=2 conn=wye Kv=12.47 kva=40000.0 bus=n4 XHL=6.7\n",
        "regulators.dss": "New RegControl.reg transformer=sub_1 winding=2 ptratio=60.0 band=1.992 vreg = 123.6\n"})
    assert record == SUBSTATION
    assert ng.substation_record({"transformers.dss": ""}) == {"transformers": [], "regcontrol": None}

    # the three scopes, as phase growth writes them: region, substation, feeder
    import growth_plan
    for sub, name, files in (("sub1", "sub1--own", {k.lower(): v for k, v in FILES.items()}),
                             ("sub1", "sub1--near", dict(OTHER, **{"linecodes.dss": LINECODES})),
                             ("sub2", "sub2--far", OTHER)):
        folder = tmp_path / "region" / sub / name
        folder.mkdir(parents=True)
        for fn, text in files.items():
            (folder / fn).write_text(text, encoding="utf-8")
    (tmp_path / "region" / "sub1" / "Transformers.dss").write_text(
        "New Transformer.sub_1 phases=3 windings=2 wdg=1 Kv=69.0 kva=40000.0 bus=n9 wdg=2 Kv=12.47 kva=40000.0 "
        "bus=n4\n", encoding="utf-8")
    assert [f.name for f in growth_plan.feeder_folders(tmp_path / "region" / "sub1")] == ["sub1--near", "sub1--own"]
    cfg = {"smart_ds_root": str(tmp_path / "region" / "sub1")}
    feeders = [tmp_path / "region" / "sub1" / "sub1--own"]
    found = {}
    for scope in ("region", "substation", "feeder"):
        out = tmp_path / f"out_{scope}"
        out.mkdir()
        growth_plan.write_catalog(growth_settings(dict(_with(catalog=scope), growth_years=10)), cfg, feeders, out)
        cat = json.loads((out / ng.CATALOG_FILE).read_text(encoding="utf-8"))
        assert cat["catalog"] == scope and cat["substation"]["transformers"] == [{"name": "sub_1", "kva": 40000.0}]
        found[scope] = ([e["linecode"] for e in cat["feeders"]["sub1--own"]["lines"]["3|mv|OH"]],
                        [e["kva"] for e in cat["feeders"]["sub1--own"]["transformers"]["1|7.2,0.12,0.12"]],
                        cat["feeder_folders"])
    assert found["region"] == (["3P_OH_A", "3P_OH_B", "3P_OH_C"], [25.0, 50.0, 75.0], 3)
    # the near folder uses the code 3P_OH_C without defining it: no statement, no entry
    assert found["substation"] == (["3P_OH_A", "3P_OH_B"], [25.0, 50.0, 75.0], 2)
    assert found["feeder"] == (["3P_OH_A", "3P_OH_B"], [25.0, 50.0], 1)


# ---------------------------------------------------------------------------
# The network and the tests on the last solve (N9)
# ---------------------------------------------------------------------------
def test_network_heads_and_paths():
    net = ng.read_network(_text())
    assert net["source"] == "src" and net["base_kv"] == 12.47
    assert {"a", "b", "c", "d", "e", "f", "x", "y", "l1", "l2", "g", "h"} <= net["mv"] and "t1lv" not in net["mv"]
    assert ng.orientation(net, net["line_of"]["m2"]) == ("c", "d")
    assert ng.orientation(net, net["line_of"]["tie"]) is None            # a disabled line
    assert [ln["name"] for ln in ng.mv_path(net, "l2")] == ["head", "m1", "fz1", "lat1"]
    assert ng.mv_path(net, "h1") is None and ng.path_length_m(net, "c") == 301.0
    assert pl.head_lines(MASTER) == [(1, "head")]
    assert net["line_of"]["m2"]["text_code"] == "3P_OH_A"
    assert [ln["name"] for ln in ng.customer_path(net, "load_h2")] == ["head", "m1", "fz1", "lat1"]
    assert [ln["name"] for ln in ng.customer_path(net, "load_c1")] == ["head", "m1", "sw1", "m2", "sw2", "m3"]
    assert ng.phase_table(net, {"lb": [7.0], "m2": [1.0, 2.0, 3.0], "nope": [9.0]}) == {
        "lb": {2: 7.0}, "m2": {1: 1.0, 2: 2.0, 3: 3.0}}


def test_limit_tests_and_the_one_metre_rule():
    net = ng.read_network(_text())
    rows = _rows(net, {"head": 150.0, "m2": 120.0, "sw1": 900.0, "fz1": 60.0, "lat1": 40.0, "tie": 500.0})
    over = [r["line"] for r in ng.lines_over(rows, 100)]
    assert over == ["m2"]                       # the switch (1 m), the fuse (1 m) and the open tie are never tested
    assert [r["line"] for r in ng.lines_over(rows, 70)] == ["head", "m2", "lat1"]
    trs = pl.transformer_rows(net, {"t1": (30.0, 3), "t2": (40.0, 3), "t4": (150.0, 9)}, DATES)
    assert [r["transformer"] for r in ng.transformers_over(trs, 100)] == ["t1"]
    assert [r["transformer"] for r in ng.transformers_over(trs, 75)] == ["t1", "t2", "t4"]
    # a customer is under the band when any step of any of its Load lines is below the low value
    load_min = {"load_h1_1": 0.96, "load_h1_2": 0.93, "load_h2_1": 0.97, "load_h2_2": 0.955, "load_c1": 0.94}
    assert ng.customers_under(load_min, 0.95) == {"load_h1": 0.93, "load_c1": 0.94}
    assert ng.customers_under(load_min, 0.90) == {}
    # the head by two measures
    row = dict(_head(_amps(230.0, 210.0, 205.0)), kva_percent=98.0)
    assert ng.head_measure(row, "largest_phase") == 115.0 and ng.head_measure(row, "three_phase_kva") == 98.0
    at = {1: {"head": _amps(230.0, 210.0, 205.0)}}
    (group,) = ng.head_groups(net, [row], at, "largest_phase")
    assert (group["k"], group["lines"], group["down"], group["normamps"], group["percent"]) == \
        (1, ["head"], "a", 200.0, 115.0)
    assert group["amps"] == _amps(230.0, 210.0, 205.0)
    assert ng.head_groups(net, [row], at, "three_phase_kva")[0]["percent"] == 98.0


def test_head_rows_and_the_head_phase_row():
    net = ng.read_network(_text())
    m1 = pd.DataFrame({"hour": [0, 0, 0], " t(sec)": [900, 1800, 2700], " V1": [7400.0] * 3, " VAngle1": [0.0] * 3,
                       " I1": [100.0, 230.0, 90.0], " IAngle1": [-10.0] * 3, " I2": [110.0, 150.0, 95.0],
                       " IAngle2": [-130.0] * 3, " I3": [120.0, 170.0, 240.0], " IAngle3": [110.0] * 3})
    m2 = pd.DataFrame({"hour": [0, 0, 0], " t(sec)": [900, 1800, 2700], " S1 (kVA)": [700.0, 1700.0, 600.0],
                       " Ang1": [0.0] * 3, " S2 (kVA)": [800.0, 1100.0, 700.0], " Ang2": [0.0] * 3,
                       " S3 (kVA)": [900.0, 1200.0, 1700.0], " Ang3": [0.0] * 3})
    (row,) = pl.head_rows(net, [(1, "head")], {1: (m1, m2)}, ["2018-06-16"])
    rating = 200.0 * 12.47 * math.sqrt(3.0)
    assert row["head"] == 1 and row["line"] == "head" and row["linecode"] == "3p_oh_b" and row["normamps"] == 200.0
    assert math.isclose(row["rating_kva"], rating) and row["peak_kva"] == 4000.0 and row["kva_step"] == 2
    assert math.isclose(row["kva_percent"], 100.0 * 4000.0 / rating)
    # the largest phase current is phase 3 at step 3, another step than the kVA peak
    assert (row["peak_phase_amps"], row["phase_step"], row["phase_percent"]) == (240.0, 3, 120.0)
    assert (row["amps_1"], row["amps_2"], row["amps_3"]) == (90.0, 95.0, 240.0)
    rows = {r["limit"]: r for r in pl.limit_rows([], [], [row], LIMITS, ["2018-06-16"])}
    assert rows["head"]["elements_over"] == 0 and math.isclose(rows["head"]["worst_value"], row["kva_percent"])
    assert rows["head_phase"]["elements_over"] == 1 and rows["head_phase"]["worst_value"] == 120.0
    assert rows["head_phase"]["worst_step"] == 3 and rows["head_phase"]["worst_element"] == "head"
    # several heads: both rows count the heads and give the worst
    second = dict(row, head=2, line="ng_express_2", kva_percent=130.0, phase_percent=60.0, kva_step=7)
    rows = {r["limit"]: r for r in pl.limit_rows([], [], [row, second], LIMITS, ["2018-06-16"])}
    assert (rows["head"]["elements_checked"], rows["head"]["elements_over"], rows["head"]["worst_element"]) == \
        (2, 1, "ng_express_2")
    assert (rows["head_phase"]["elements_over"], rows["head_phase"]["worst_element"]) == (1, "head")
    # the totals of two heads: P and Q added per phase, the currents added as phasors
    t1, t2 = pl.head_totals([m1, m1], [m2, m2.assign(**{" Ang1": [90.0] * 3})])
    assert np.allclose(t1[" I1"], 2 * m1[" I1"]) and np.allclose(t1[" IAngle1"], -10.0)
    assert np.allclose(t1[" V1"], 7400.0)
    assert np.allclose(t2[" S1 (kVA)"], m2[" S1 (kVA)"] * math.sqrt(2.0)) and np.allclose(t2[" Ang1"], 45.0)
    assert np.allclose(t2[" S2 (kVA)"], 2 * m2[" S2 (kVA)"])
    cur = pl.read_phase_currents(_Circuit({"ml_1": {" V1": [1.0, 1.0], " I1": [5.0, -7.0], " I2": [6.0, 8.0]}}),
                                 {"ml_1": "M2"}, [2])
    assert cur == {2: {"m2": [7.0, 8.0]}}


class _Monitors:
    def __init__(self, data):
        self.data, self.Name = data, None

    @property
    def Header(self):
        return list(self.data[self.Name])

    def Channel(self, i):
        return self.data[self.Name][list(self.data[self.Name])[i - 1]]


class _Circuit:
    def __init__(self, data):
        self.Monitors = _Monitors(data)


# ---------------------------------------------------------------------------
# Phase rebalancing (N12)
# ---------------------------------------------------------------------------
def test_rebalancing_moves_and_rewritten_nodes():
    net = ng.read_network(_text())
    laterals = {lat["root"]: lat["node"] for lat in ng.single_phase_laterals(net)}
    assert laterals == {"g": 2, "h": 1, "l1": 1}
    at = {1: {"head": _amps(220.0, 150.0, 180.0), "fz1": {1: 45.0}, "lc": {1: 30.0}, "lb": {2: 20.0}}}
    groups = ng.head_groups(net, [_head(_amps(220.0, 150.0, 180.0))], at, "largest_phase")
    # phase 1 is the heaviest and phase 2 the lightest: moving h (30 A) leaves max(190, 180), moving l1
    # (45 A) max(175, 195); h moves. Then no move lowers 190 A, and the rule stops
    items = ng.rebalance_moves(net, groups, at)
    assert [ng.public(i) for i in items] == [{"step": "rebalance_phases", "lateral": "h", "to_phase": 2}]
    assert items[0]["_peak"] == 30.0
    balanced = {1: dict(at[1], head=_amps(200.0, 200.0, 200.0))}
    assert ng.rebalance_moves(net, ng.head_groups(net, [_head(_amps(200.0, 200.0, 200.0))], balanced,
                                                  "largest_phase"), balanced) == []
    # two moves in a row: 240, 100, 180 -> l1 (45 A) then h (30 A) both leave phase 1
    wide = {1: dict(at[1], head=_amps(240.0, 100.0, 180.0))}
    moved = ng.rebalance_moves(net, ng.head_groups(net, [_head(_amps(240.0, 100.0, 180.0))], wide, "largest_phase"),
                               wide)
    assert sorted((i["lateral"], i["to_phase"]) for i in moved) == [("h", 2), ("l1", 2)]
    # the step applies first, once, when a head or a three-phase medium-voltage line is over its limit
    state = ng.new_state()
    args = (net, [_head(_amps(220.0, 150.0, 180.0))], _rows(net, {"head": 220.0}), [], at, {}, _catalog(),
            SUBSTATION, dict(NG, rebalance_phases=True), LIMITS, 0.95, EXPRESS, state)
    step, found, _ = ng.next_step(*args)
    assert step == "rebalance_phases" and [i["lateral"] for i in found] == ["h"] and state["rebalanced"]
    assert ng.next_step(*args)[0] != "rebalance_phases"                   # at most once per circuit folder
    assert ng.next_step(*args[:8], dict(NG, rebalance_phases=False), *args[9:12], ng.new_state())[0] != \
        "rebalance_phases"

    # the statements: the phase node of every medium-voltage line, transformer primary and medium-voltage
    # element of the lateral; the secondary side keeps its nodes
    changed, rows = ng.apply_items(FILES, [{"step": "rebalance_phases", "lateral": "h", "to_phase": 2}], _catalog(),
                                   SUBSTATION, EXPRESS)
    assert sorted(changed) == ["Capacitors.dss", "Lines.dss", "Transformers.dss"]
    assert "New Line.lc Units=km Length=0.06 bus1=y.2 bus2=h.2 switch=n" in changed["Lines.dss"]
    assert "bus=h.2 Kv=7.2" in changed["Transformers.dss"] and "bus=t5lv.1.0" in changed["Transformers.dss"]
    assert "bus=l1.1 Kv=7.2" in changed["Transformers.dss"]                  # another lateral is left alone
    assert changed["Capacitors.dss"] == "New Capacitor.cap1 bus1=h.2 phases=1 Kv=7.2 conn=Wye Kvar=50.0\n"
    assert changed["Lines.dss"].count("\n") == LINES.count("\n")
    assert (rows[0]["element"], rows[0]["was"], rows[0]["now"], rows[0]["length_m"]) == ("h", "phase 1", "phase 2", 60.0)
    assert rows[0]["changed"] == [("line", "lc"), ("transformer", "t5")]
    assert _raises(ng.apply_items, FILES, [{"step": "rebalance_phases", "lateral": "c", "to_phase": 2}], _catalog(),
                   SUBSTATION, EXPRESS)


# ---------------------------------------------------------------------------
# A new feeder (N13)
# ---------------------------------------------------------------------------
def _feeder(head_amps, at, peaks=None, lines=LINES, **settings):
    files = dict(FILES, **{"Lines.dss": lines})
    net = ng.read_network(_text(files))
    table = {1: dict({k: v for k, v in at.items()}, head=head_amps)}
    state = ng.new_state()
    groups = ng.head_groups(net, [_head(head_amps)], table, "largest_phase")
    items, notes = ng.new_feeder_choice(net, groups, _rows(net, dict({"head": max(head_amps.values())},
                                                                     **(peaks or {}))),
                                        table, _catalog(), dict(NG, **settings), LIMITS, EXPRESS, state)
    return items, notes, state


def test_new_feeder_need_sets_and_ties():
    head = _amps(230.0, 210.0, 205.0)                       # 200 A rating: 30, 10 and 5 A must be lost
    at = {"sw1": _amps(90.0, 80.0, 85.0), "sw2": _amps(40.0, 8.0, 30.0), "sw3": _amps(60.0, 50.0, 45.0)}
    items, notes, state = _feeder(head, at)
    # sw1 leaves the old head at 140 A (0.70 of 200 A); sw3 leaves it at 170 A (0.85): sw1 is taken
    assert ng.public(items[0]) == {"step": "new_feeder", "open": "sw1"} and not notes and not state["no_feeder"]
    assert items[0]["_peak"] == 230.0
    detail = dict(part.split("=", 1) for part in items[0]["_detail"].split(";"))
    assert detail["need"] == "[30.0, 10.0, 5.0]" and detail["amps"] == "[90.0, 80.0, 85.0]"
    assert (detail["candidates"], detail["set"], detail["kind"], detail["head_over"]) == ("2", "sizing", "switch", "1")
    # a candidate that fails on one phase only: sw2 carries 8 A on phase 2, 10 A must be lost there
    items, notes, state = _feeder(head, {"sw1": _amps(20.0, 20.0, 20.0), "sw2": _amps(40.0, 8.0, 30.0),
                                         "sw3": _amps(25.0, 9.0, 30.0)})
    assert items == [] and notes == ["no switch qualifies for head 1 (head)"] and state["no_feeder"] == {"head"}
    # the head is left out from then on
    net = ng.read_network(_text())
    table = {1: dict(at, head=head)}
    groups = ng.head_groups(net, [_head(head)], table, "largest_phase")
    assert ng.new_feeder_choice(net, groups, _rows(net, {"head": 230.0}), table, _catalog(), NG, LIMITS, EXPRESS,
                                state) == ([], [])
    # the 75 percent set comes first: sw1 (160 A, above 150 A) would leave the lower maximum, sw3 is taken
    big = {"sw1": _amps(160.0, 150.0, 155.0), "sw3": _amps(60.0, 50.0, 45.0)}
    assert _feeder(head, big)[0][0]["open"] == "sw3"
    # with no candidate in the 75 percent set, those within head_limit_percent
    items, _, _ = _feeder(head, {"sw1": _amps(160.0, 150.0, 155.0)})
    assert items[0]["open"] == "sw1" and "set=limit" in items[0]["_detail"]
    # above the head limit of the express code (200 A): no switch qualifies
    assert _feeder(_amps(460.0, 420.0, 410.0), {"sw1": _amps(300.0, 280.0, 270.0)})[0] == []
    # a tie on the maximum: the shorter express line (sw3: 101 m, sw1: 301 m), then the name
    tie = {"sw1": _amps(90.0, 80.0, 85.0), "sw3": _amps(90.0, 80.0, 85.0)}
    assert _feeder(head, tie)[0][0]["open"] == "sw3"
    # a head within its limit and no stuck line: the step does not apply
    assert _feeder(_amps(190.0, 180.0, 170.0), at) == ([], [], ng.new_state())
    # a head over its limit while the catalog holds a larger code is no call for a new feeder (it is rebuilt)
    net = ng.read_network(_text())
    groups = ng.head_groups(net, [_head(head)], table, "largest_phase")
    assert ng.new_feeder_choice(net, groups, _rows(net, {"head": 230.0}), table, _catalog(region=True), NG, LIMITS,
                                EXPRESS, ng.new_state()) == ([], [])


def test_new_feeder_stuck_lines_and_open_points():
    head = _amps(190.0, 180.0, 170.0)                       # the head is within its limit
    # m1 (200 A, no larger code) is over its limit: 30, 0 and 0 A must be lost beyond it
    at = {"m1": _amps(230.0, 190.0, 180.0), "sw1": _amps(90.0, 80.0, 85.0), "sw2": _amps(40.0, 30.0, 30.0),
          "sw3": _amps(70.0, 60.0, 60.0)}
    items, _, _ = _feeder(head, at, {"m1": 230.0})
    assert items[0]["open"] == "sw1"                        # sw3 is not beyond m1; sw2 leaves the higher maximum
    detail = dict(part.split("=", 1) for part in items[0]["_detail"].split(";"))
    assert detail["need"] == "[30.0, 0.0, 0.0]" and detail["stuck"] == "['m1']" and detail["head_over"] == "0"
    # a line with a larger code in the catalog is not stuck: m2 (100 A) over its limit calls no feeder
    assert _feeder(head, at, {"m2": 130.0})[0] == []
    # two stuck lines, none beyond both: the farthest (m3, at the end) leaves the set
    far = LINES.replace("bus2=f.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_A",
                        "bus2=f.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_B")
    items, _, _ = _feeder(head, dict(at, m3=_amps(210.0, 100.0, 100.0)), {"m1": 230.0, "m3": 210.0}, lines=far)
    assert items[0]["open"] == "sw1"
    detail = dict(part.split("=", 1) for part in items[0]["_detail"].split(";"))
    assert detail["stuck"] == "['m1', 'm3']" and detail["kept"] == "['m1']"
    # only a stuck line with no switch beyond it, and a head within its limit: no candidate under switch
    items, notes, state = _feeder(head, {"m3": _amps(210.0, 100.0, 100.0), "sw1": _amps(90.0, 80.0, 85.0)},
                                  {"m3": 210.0}, lines=far)
    assert items == [] and notes and state["no_feeder"] == {"head"}
    # switch_then_bus: no switch carries what must be lost, a bus does (bus d, fed by m2)
    weak = {"m1": _amps(230.0, 190.0, 180.0), "sw1": _amps(20.0, 20.0, 20.0), "sw2": _amps(10.0, 10.0, 10.0),
            "m2": _amps(35.0, 20.0, 20.0), "m3": _amps(10.0, 10.0, 10.0), "sw3": _amps(70.0, 60.0, 60.0)}
    assert _feeder(head, weak, {"m1": 230.0})[0] == []
    items, _, _ = _feeder(head, weak, {"m1": 230.0}, open_point="switch_then_bus")
    assert ng.public(items[0]) == {"step": "new_feeder", "cut_bus": "d"} and "kind=bus" in items[0]["_detail"]
    # bus: the buses from the start; every three-phase medium-voltage line stands for the bus it feeds
    items, _, _ = _feeder(head, at, {"m1": 230.0}, open_point="bus")
    assert ng.public(items[0]) == {"step": "new_feeder", "cut_bus": "c"}
    # under bus, when no bus passes the limits, the smallest maximum is taken whatever the limits
    heavy = _amps(460.0, 420.0, 410.0)
    all_big = {"m1": _amps(450.0, 410.0, 400.0), "sw1": _amps(300.0, 280.0, 270.0), "m2": _amps(290.0, 270.0, 260.0),
               "sw2": _amps(250.0, 240.0, 230.0), "m3": _amps(240.0, 230.0, 220.0), "sw3": _amps(5.0, 5.0, 5.0),
               "mx": _amps(5.0, 5.0, 5.0)}
    items, _, _ = _feeder(heavy, all_big, open_point="bus")
    # 260, 220 and 210 A must be lost: buses b, c and d carry that; d leaves max(170, 290) / 200
    assert items[0]["cut_bus"] == "d" and "set=any" in items[0]["_detail"]
    assert _feeder(heavy, all_big, open_point="switch")[0] == []
    # a line a CapControl watches is never the open point
    watched = ng.watched_lines("New CapControl.c1 Capacitor=cap1 Element=Line.SW1 Terminal=1\n"
                               "New Monitor.x element=Line.sw3\n")
    assert watched == {"sw1"}
    net = ng.read_network(_text())
    table = {1: dict(at, head=_amps(230.0, 210.0, 205.0))}
    groups = ng.head_groups(net, [_head(_amps(230.0, 210.0, 205.0))], table, "largest_phase")
    items, _ = ng.new_feeder_choice(net, groups, _rows(net, {"head": 230.0}), table, _catalog(), NG, LIMITS, EXPRESS,
                                    ng.new_state(), watched)
    assert items[0]["open"] == "sw3"


def test_new_feeder_statements_and_monitor_names():
    changed, rows = ng.apply_items(FILES, [{"step": "new_feeder", "open": "sw1", "_peak": 230.0}], _catalog(),
                                   SUBSTATION, EXPRESS)
    assert sorted(changed) == ["Lines.dss", "Master.dss"]
    lines = changed["Lines.dss"]
    assert "New Line.sw1 Units=km Length=0.001 bus1=b.1.2.3 bus2=c.1.2.3 switch=y enabled=n phases=3" in lines
    assert lines.endswith("New Line.ng_express_2 Units=m Length=301.0 bus1=src.1.2.3 bus2=c.1.2.3 switch=n "
                          "enabled=y phases=3 Linecode=3P_OH_B\n")
    master = changed["Master.dss"].splitlines()
    i = master.index("new monitor.m2 element=Line.head mode=1")
    assert master[i + 1:i + 3] == ["New Monitor.h2m1 element=Line.ng_express_2 mode=0",
                                   "New Monitor.h2m2 element=Line.ng_express_2 mode=1"]
    assert master[-4:] == ["Export monitors m1", "Export monitors m2", "Export monitors h2m1", "Export monitors h2m2"]
    assert pl.head_lines(changed["Master.dss"]) == [(1, "head"), (2, "ng_express_2")]
    row = rows[0]
    assert (row["element"], row["was"], row["now"], row["count"], row["length_m"], row["peak"]) == \
        ("ng_express_2", "sw1", "3P_OH_B", 1, 301.0, 230.0)
    assert row["changed"] == [("line", "ng_express_2"), ("line", "sw1")]
    # Phase 8 finds the exports of head 1 by the tokens m1 and m2; the names of a new head do not match them
    from aggregate_m1_m2_with_circuits import M1_RE, M2_RE
    assert M1_RE.search("feeder_t_Mon_m1_1.csv") and M2_RE.search("feeder_t_Mon_m2_1.csv")
    for name in ("feeder_t_Mon_h2m1_1.csv", "feeder_t_Mon_h2m2_1.csv", "feeder_t_Mon_h12m1_1.csv"):
        assert not M1_RE.search(name) and not M2_RE.search(name)
    # the circuit after the step: bus c and everything beyond it hang on the express line, and stay radial
    files = dict(FILES, **changed)
    net = ng.read_network(_text(files))
    assert net["parent"]["c"][1]["name"] == "ng_express_2" and not net["extra_lines"]
    assert [ln["name"] for ln in ng.mv_path(net, "f")] == ["ng_express_2", "m2", "sw2", "m3"]
    assert not net["line_of"]["sw1"]["enabled"] and "b" in net["mv"] and "l2" in net["mv"]
    # a cut at a bus: the line that feeds it is the element opened; a second new feeder is head 3
    more, rows = ng.apply_items(files, [{"step": "new_feeder", "cut_bus": "y"}], _catalog(), SUBSTATION, EXPRESS)
    assert "New Line.mx Units=km Length=0.15 bus1=x.1.2.3 bus2=y.1.2.3 switch=n enabled=n" in more["Lines.dss"]
    assert "New Line.ng_express_3 Units=m Length=251.0 bus1=src.1.2.3 bus2=y.1.2.3" in more["Lines.dss"]
    assert pl.head_lines(more["Master.dss"])[-1] == (3, "ng_express_3") and rows[0]["was"] == "mx (bus y)"
    # a fuse on an opened line goes out with it
    fused, _ = ng.apply_items(FILES, [{"step": "new_feeder", "open": "fz1"}], _catalog(), SUBSTATION, EXPRESS)
    assert "New Fuse.Fuse_fz1 monitoredobj=Line.fz1 enabled=n ratedcurrent=100.0" in fused["Lines.dss"]


# ---------------------------------------------------------------------------
# Rebuilt lines (N14) and service transformers (N15)
# ---------------------------------------------------------------------------
def _reconductor(peaks, region=False, heads=None, **settings):
    net = ng.read_network(_text())
    head = heads or _head(_amps(100.0, 100.0, 100.0))
    groups = ng.head_groups(net, [head], {1: {"head": _amps(head["amps_1"], head["amps_2"], head["amps_3"])}},
                            "largest_phase")
    return [(i["line"], i["linecode"], i["circuits"]) for i in ng.reconductor_items(
        net, groups, _rows(net, peaks), _catalog(region), dict(NG, **settings), LIMITS)]


def test_reconductor_rules():
    # m2: 100 A, three-phase, medium voltage, overhead. 75 percent of 200 A is 150 A
    assert _reconductor({"m2": 140.0}) == [("m2", "3P_OH_B", 1)]             # the next code by sizing
    assert _reconductor({"m2": 170.0}, region=True) == [("m2", "3P_OH_C", 1)]
    assert _reconductor({"m2": 170.0}) == [("m2", "3P_OH_B", 1)]             # the largest, within its limit
    assert _reconductor({"m2": 230.0}) == [("m2", "3P_OH_B", 2)]             # second circuits: ceil(230 / 150)
    assert _reconductor({"m2": 460.0}) == [("m2", "3P_OH_B", 4)]
    assert _reconductor({"m2": 99.0}) == [] and _reconductor({"sw1": 900.0, "fz1": 90.0}) == []
    # sizing_percent 60: 120 A of 200 A is below 140 A, and 140 A is within the limit of the largest code
    assert _reconductor({"m2": 140.0}, sizing_percent=60) == [("m2", "3P_OH_B", 1)]
    assert _reconductor({"m2": 230.0}, sizing_percent=60) == [("m2", "3P_OH_B", 2)]   # ceil(230 / 120)
    # no larger code (the largest of its class): second circuits of its own code
    assert _reconductor({"m1": 230.0}) == [("m1", "3P_OH_B", 2)]
    # a construction that is not shown: its own code, second circuits (300 A: ceil(500 / 225))
    assert _reconductor({"s4": 500.0}) == [("s4", "LV3", 3)]
    # a single-phase lateral with no larger code of its class
    assert _reconductor({"lat1": 60.0}) == [("lat1", "1P_OH_X", 2)]
    # a head over its limit with a larger code in the catalog is rebuilt as a line (230 A: 400 A x 0.75)
    over_head = _head(_amps(230.0, 210.0, 205.0))
    assert _reconductor({"head": 230.0}, region=True, heads=over_head) == [("head", "3P_OH_C", 1)]
    # a head over the head limit and within the line limit is rebuilt too
    lines = _rows(ng.read_network(_text()), {"head": 150.0})
    net = ng.read_network(_text())
    groups = ng.head_groups(net, [_head(_amps(150.0, 150.0, 150.0), percent=120.0)],
                            {1: {"head": _amps(150.0, 150.0, 150.0)}}, "three_phase_kva")
    found = ng.reconductor_items(net, groups, lines, _catalog(region=True), NG, LIMITS)
    assert [(i["line"], i["linecode"], i["circuits"]) for i in found] == [("head", "3P_OH_C", 1)]


def test_reconductor_statements():
    catalog = _catalog(region=True)
    item = {"step": "reconductor", "line": "m2", "linecode": "3P_OH_C", "circuits": 1, "_peak": 170.0}
    changed, rows = ng.apply_items(FILES, [item], catalog, SUBSTATION, EXPRESS)
    assert "New Line.m2 Units=km Length=0.3 bus1=c.1.2.3 bus2=d.1.2.3 switch=n enabled=y phases=3 " \
           "Linecode=3P_OH_C\n" in changed["Lines.dss"]
    # a LineCode new to the circuit is appended to its LineCodes file
    assert changed["LineCodes.dss"] == LINECODES + ("New Linecode.3P_OH_C units=km nphases=3 Rmatrix=(0.1 ) "
                                                    "Xmatrix=(0.5 ) normamps=400.0\n")
    assert (rows[0]["was"], rows[0]["now"], rows[0]["count_before"], rows[0]["count"], rows[0]["length_m"]) == \
        ("3P_OH_A", "3P_OH_C", 1, 1, 300.0)
    # two lines of one round that take the same new code: its statement is appended once
    both = [item, dict(item, line="m3")]
    changed, rows = ng.apply_items(FILES, both, catalog, SUBSTATION, EXPRESS)
    assert changed["LineCodes.dss"].count("New Linecode.3P_OH_C ") == 1
    assert changed["Lines.dss"].count("Linecode=3P_OH_C") == 2 and [r["element"] for r in rows] == ["m2", "m3"]
    # second circuits: the same buses and length, named <line>_ng<j>
    two = {"step": "reconductor", "line": "m2", "linecode": "3P_OH_B", "circuits": 3}
    changed, rows = ng.apply_items(FILES, [two], catalog, SUBSTATION, EXPRESS)
    assert sorted(changed) == ["Lines.dss"]
    tail = changed["Lines.dss"].splitlines()[-2:]
    assert tail == [f"New Line.m2_ng{j} Units=km Length=0.3 bus1=c.1.2.3 bus2=d.1.2.3 switch=n enabled=y phases=3 "
                    f"Linecode=3P_OH_B" for j in (1, 2)]
    assert rows[0]["count"] == 3 and rows[0]["changed"] == [("line", "m2"), ("line", "m2_ng1"), ("line", "m2_ng2")]
    # a line with second circuits is taken with them: the sum of their currents gives n
    files = dict(FILES, **changed)
    net = ng.read_network(_text(files))
    groups = ng.head_groups(net, [_head(_amps(100.0, 100.0, 100.0))], {1: {"head": _amps(100.0, 100.0, 100.0)}},
                            "largest_phase")
    found = ng.reconductor_items(net, groups, _rows(net, {"m2": 210.0, "m2_ng1": 210.0, "m2_ng2": 210.0}),
                                 _catalog(), NG, LIMITS)
    assert [(i["line"], i["linecode"], i["circuits"]) for i in found] == [("m2", "3P_OH_B", 5)]   # ceil(630 / 150)
    again, rows = ng.apply_items(files, [dict(two, circuits=5)], catalog, SUBSTATION, EXPRESS)
    assert [ln.split()[1] for ln in again["Lines.dss"].splitlines()[-2:]] == ["Line.m2_ng3", "Line.m2_ng4"]
    assert (rows[0]["count_before"], rows[0]["count"]) == (3, 5)
    # a second circuit of a head line is a head too
    head2, _ = ng.apply_items(FILES, [{"step": "reconductor", "line": "head", "linecode": "3P_OH_B", "circuits": 2}],
                              catalog, SUBSTATION, EXPRESS)
    assert pl.head_lines(head2["Master.dss"]) == [(1, "head"), (2, "head_ng1")]
    net = ng.read_network(_text(dict(FILES, **head2)))
    rows = [_head(_amps(120.0, 110.0, 100.0)), _head(_amps(118.0, 110.0, 100.0), line="head_ng1", k=2)]
    at = {1: {"head": _amps(120.0, 110.0, 100.0), "head_ng1": _amps(118.0, 110.0, 100.0)}, 2: {}}
    (group,) = ng.head_groups(net, rows, at, "largest_phase")
    assert group["lines"] == ["head", "head_ng1"] and group["normamps"] == 400.0
    assert group["amps"] == _amps(238.0, 220.0, 200.0) and group["percent"] == 60.0


def test_carried_items_with_a_missing_element_stop():
    catalog = _catalog()
    for item in ({"step": "reconductor", "line": "nope", "linecode": "3P_OH_B", "circuits": 1},
                 {"step": "reconductor", "line": "m2", "linecode": "3P_OH_C", "circuits": 1},   # not in this catalog
                 {"step": "service_transformer", "transformer": "nope", "kva": 50.0, "units": 1},
                 {"step": "service_transformer", "transformer": "t1", "kva": 75.0, "units": 1},
                 {"step": "new_feeder", "open": "nope"}, {"step": "new_feeder", "open": "tie"},
                 {"step": "new_feeder", "cut_bus": "nope"}, {"step": "new_feeder", "cut_bus": "t1lv"},
                 {"step": "regulator", "line": "nope"}, {"step": "regulator", "line": "head"},
                 {"step": "regulator", "line": "s1"}, {"step": "rebalance_phases", "lateral": "nope", "to_phase": 1},
                 {"step": "new_substation"}):
        try:
            ng.apply_items(FILES, [dict(item, feeder="f", mix="all")], catalog, SUBSTATION, EXPRESS)
        except ng.NetworkGrowthError as e:
            assert "item" in str(e) or "catalog" in str(e), (item, e)
        else:
            raise AssertionError(f"expected a stop: {item}")
    assert _raises(ng.apply_items, FILES, [{"step": "regulator", "line": "m2"}], catalog,
                   {"transformers": [], "regcontrol": None}, EXPRESS)
    # an item sees what the items before it built: the regulator takes the ampacity of the rebuilt line
    changed, rows = ng.apply_items(
        FILES, [{"step": "reconductor", "line": "m2", "linecode": "3P_OH_B", "circuits": 1},
                {"step": "regulator", "line": "m2"}], catalog, SUBSTATION, EXPRESS)
    assert math.isclose(rows[1]["kva"], 200.0 * 12.47 / math.sqrt(3.0))


def _transformers(peaks, region=False, **settings):
    net = ng.read_network(_text())
    rows = pl.transformer_rows(net, {name: (kva, 4) for name, kva in peaks.items()}, DATES)
    return [(i["transformer"], i["kva"], i["units"]) for i in ng.transformer_items(
        net, rows, _catalog(region), dict(NG, **settings), LIMITS)]


def test_transformer_rules_and_statements():
    # t1: 25 kVA, single-phase, 7.2 kV to 0.12 and 0.12 kV. 75 percent of 50 kVA is 37.5 kVA
    assert _transformers({"t1": 30.0}) == [("t1", 50.0, 1)]                  # the next rating by sizing
    assert _transformers({"t1": 45.0}, region=True) == [("t1", 75.0, 1)]
    assert _transformers({"t1": 45.0}) == [("t1", 50.0, 1)]                  # the largest, within its limit
    assert _transformers({"t1": 70.0}) == [("t1", 50.0, 2)]                  # parallel units: ceil(70 / 37.5)
    assert _transformers({"t1": 24.0}) == []
    # no larger rating: parallel units of its own (150 kVA: ceil(400 / 112.5))
    assert _transformers({"t4": 400.0}) == [("t4", 150.0, 4)]
    assert _transformers({"t2": 60.0, "t1": 30.0}) == [("t1", 50.0, 1), ("t2", 50.0, 2)]
    catalog = _catalog()
    item = {"step": "service_transformer", "transformer": "t1", "kva": 50.0, "units": 2, "_peak": 70.0}
    changed, rows = ng.apply_items(FILES, [item], catalog, SUBSTATION, EXPRESS)
    assert sorted(changed) == ["Transformers.dss"]
    text = changed["Transformers.dss"]
    # the catalog statement of 50 kVA (t2's) under t1's name and on t1's buses, winding by winding
    new = _tr("t1", "l1", 1, 50.0)
    assert text.startswith(new) and text.endswith(new.replace("Transformer.t1 ", "Transformer.t1_ng1 "))
    assert (rows[0]["was"], rows[0]["now"], rows[0]["count_before"], rows[0]["count"], rows[0]["kva"]) == \
        (25.0, 50.0, 1, 2, 50.0)
    assert rows[0]["changed"] == [("transformer", "t1"), ("transformer", "t1_ng1")]
    # parallel units of the same rating keep the transformer's own statement
    same, _ = ng.apply_items(FILES, [dict(item, transformer="t4", kva=150.0, units=3)], catalog, SUBSTATION, EXPRESS)
    assert same["Transformers.dss"].count("kva=150.0 %r=0.5 XHL=4.0") == 3
    assert "New Transformer.t4_ng2 phases=3 windings=2" in same["Transformers.dss"]
    # a transformer with parallel units is taken with them
    net = ng.read_network(_text(dict(FILES, **changed)))
    rows = pl.transformer_rows(net, {"t1": (55.0, 4), "t1_ng1": (55.0, 4)}, DATES)
    assert [(i["transformer"], i["kva"], i["units"]) for i in ng.transformer_items(net, rows, catalog, NG, LIMITS)] \
        == [("t1", 50.0, 3)]                                                  # ceil(110 / 37.5)
    assert ng.retarget("New Transformer.x wdg=1 bus=a.1 kv=7.2 wdg=2 bus=b.1.0 kv=0.12", "y", ["p.2", "q.1.0"]) == \
        "New Transformer.y wdg=1 bus=p.2 kv=7.2 wdg=2 bus=q.1.0 kv=0.12"
    assert _raises(ng.retarget, "New Transformer.x wdg=1 bus=a.1 wdg=2 bus=b wdg=3 bus=c", "y", ["p", "q"])


# ---------------------------------------------------------------------------
# A line voltage regulator (N16)
# ---------------------------------------------------------------------------
def _groups(net):
    return ng.head_groups(net, [_head(_amps(100.0, 100.0, 100.0))], {1: {"head": _amps(100.0, 100.0, 100.0)}},
                          "largest_phase")


def test_regulator_rules_and_statements():
    net = ng.read_network(_text())
    # the customers under the band are on one lateral: the deepest line on the path of both is fz1
    items, notes = ng.regulator_choice(net, _groups(net), {"load_h1": 0.93, "load_h2": 0.94}, SUBSTATION)
    assert [ng.public(i) for i in items] == [{"step": "regulator", "line": "fz1"}] and not notes
    assert items[0]["_peak"] == 0.93
    # customers on the lateral and at the far end: the deepest shared line is m1
    assert ng.regulator_choice(net, _groups(net), {"load_h2": 0.94, "load_c1": 0.92}, SUBSTATION)[0][0]["line"] == "m1"
    assert ng.regulator_choice(net, _groups(net), {"load_c1": 0.92}, SUBSTATION)[0][0]["line"] == "m3"
    # customers on both sides of bus a: the shared line is the head, which starts at the source bus
    assert ng.regulator_choice(net, _groups(net), {"load_h1": 0.93, "load_h5": 0.94}, SUBSTATION) == ([], [])
    assert ng.regulator_choice(net, _groups(net), {}, SUBSTATION) == ([], [])
    # a substation folder without a RegControl: the step does not apply, with a note
    items, notes = ng.regulator_choice(net, _groups(net), {"load_h1": 0.93}, {"transformers": [], "regcontrol": None})
    assert items == [] and notes == ["no regulator: the substation folder holds no RegControl"]

    changed, rows = ng.apply_items(FILES, [{"step": "regulator", "line": "m2", "_peak": 0.92}], _catalog(),
                                   SUBSTATION, EXPRESS)
    assert sorted(changed) == ["Buscoords.dss", "Lines.dss", "Transformers.dss"]
    assert "New Line.m2 Units=km Length=0.3 bus1=c_ngreg1.1.2.3 bus2=d.1.2.3 switch=n" in changed["Lines.dss"]
    kv, kva = 12.47 / math.sqrt(3.0), 100.0 * 12.47 / math.sqrt(3.0)
    added = changed["Transformers.dss"][len(TRANSFORMERS):].splitlines()
    assert len(added) == 6
    for p in (1, 2, 3):
        assert added[2 * p - 2] == (
            f"New Transformer.ngreg1_{p} phases=1 windings=2 XHL=0.01 %LoadLoss=0.01 wdg=1 conn=wye bus=c.{p} "
            f"Kv={kv:.10g} kva={kva:.10g} wdg=2 conn=wye bus=c_ngreg1.{p} Kv={kv:.10g} kva={kva:.10g}")
        assert added[2 * p - 1] == (f"New RegControl.ngreg1_{p} transformer=ngreg1_{p} winding=2 vreg=123.6 "
                                    f"band=1.992 ptratio=60.0")
    assert changed["Buscoords.dss"] == BUSCOORDS + "c_ngreg1 0.003 0.0001\n"
    assert (rows[0]["element"], rows[0]["was"], rows[0]["now"], rows[0]["count"]) == ("m2", "c", "c_ngreg1", 3)
    assert math.isclose(rows[0]["kva"], kva) and rows[0]["peak"] == 0.92
    # the buses beyond the regulator stay at medium voltage, and the line carries one regulator only
    after = ng.read_network(_text(dict(FILES, **changed)))
    assert {"c_ngreg1", "d", "e", "f", "g"} <= after["mv"] and after["line_of"]["m3"]["b1"] in after["mv"]
    assert [ln["name"] for ln in ng.mv_path(after, "f")] == ["head", "m1", "sw1", "m2", "sw2", "m3"]
    assert pl.line_rows(after, {}, DATES)[5]["level"] == "mv"
    assert all(ng.is_regulator(f"ngreg1_{p}") for p in (1, 2, 3)) and not ng.is_regulator("t1")
    # the regulator on a single-phase line: one unit; a second regulator of the circuit is number 2
    more, rows = ng.apply_items(dict(FILES, **changed), [{"step": "regulator", "line": "fz1"}], _catalog(),
                                SUBSTATION, EXPRESS)
    assert "New Line.fz1 Units=km Length=0.001 bus1=b_ngreg2.1 bus2=l1.1 switch=y" in more["Lines.dss"]
    assert more["Transformers.dss"].count("New Transformer.ngreg2_") == 1 and rows[0]["count"] == 1
    assert "bus=b.1 Kv=" in more["Transformers.dss"] and "bus=b_ngreg2.1 Kv=" in more["Transformers.dss"]
    # one per line: m2 already carries a regulator
    again = ng.read_network(_text(dict(FILES, **changed)))
    path_customers = {"load_c1": 0.92}
    assert ng.regulator_choice(again, _groups(again), path_customers, SUBSTATION)[0][0]["line"] == "m3"
    only_m2 = dict(path_customers, load_h3=0.93)               # load_h3 hangs on d: the shared line is m2
    assert ng.regulator_choice(again, _groups(again), only_m2, SUBSTATION) == ([], [])
    assert _raises(ng.apply_items, dict(FILES, **changed), [{"step": "regulator", "line": "m2"}], _catalog(),
                   SUBSTATION, EXPRESS)
    # a line with second circuits is one branch: every circuit moves to the regulator bus, and the
    # regulator takes the ampacity of them all
    two, _ = ng.apply_items(FILES, [{"step": "reconductor", "line": "m2", "linecode": "3P_OH_B", "circuits": 2}],
                            _catalog(), SUBSTATION, EXPRESS)
    files2 = dict(FILES, **two)
    net2 = ng.read_network(_text(files2))
    assert [x["name"] for x in ng.circuits(net2, net2["line_of"]["m2_ng1"])] == ["m2", "m2_ng1"]
    assert ng.regulator_choice(net2, _groups(net2), {"load_c1": 0.92, "load_h3": 0.93}, SUBSTATION)[0][0]["line"] == "m2"
    reg2, rows2 = ng.apply_items(files2, [{"step": "regulator", "line": "m2"}], _catalog(), SUBSTATION, EXPRESS)
    assert reg2["Lines.dss"].count("bus1=c_ngreg1.1.2.3 bus2=d.1.2.3") == 2 and "bus1=c.1.2.3 bus2=d" not in reg2["Lines.dss"]
    assert math.isclose(rows2[0]["kva"], 2 * 200.0 * 12.47 / math.sqrt(3.0))
    assert rows2[0]["changed"][:2] == [("line", "m2"), ("line", "m2_ng1")]
    after2 = ng.read_network(_text(dict(files2, **reg2)))
    assert not [ln["name"] for ln in after2["extra_lines"] if {ln["b1"], ln["b2"]} != {"c_ngreg1", "d"}]
    assert ng.regulator_choice(after2, _groups(after2), {"load_c1": 0.92, "load_h3": 0.93}, SUBSTATION) == ([], [])
    # a new feeder that opens the branch opens every circuit of it, and the cut at a bus names the first
    cut, rows2 = ng.apply_items(files2, [{"step": "new_feeder", "cut_bus": "d"}], _catalog(), SUBSTATION, EXPRESS)
    assert cut["Lines.dss"].count("bus1=c.1.2.3 bus2=d.1.2.3 switch=n enabled=n") == 2 and rows2[0]["was"] == "m2 (bus d)"
    opened = ng.read_network(_text(dict(files2, **cut)))
    assert opened["parent"]["d"][1]["name"] == "ng_express_2" and not opened["extra_lines"]
    # the branch is one candidate of a new feeder, with the sum of its currents
    table = {1: {"head": _amps(230.0, 210.0, 205.0), "m2": _amps(40.0, 35.0, 30.0), "m2_ng1": _amps(40.0, 35.0, 30.0)}}
    groups2 = ng.head_groups(net2, [_head(_amps(230.0, 210.0, 205.0))], table, "largest_phase")
    found, _ = ng.new_feeder_choice(net2, groups2, _rows(net2, {"head": 230.0}), table, _catalog(), dict(NG, open_point="bus"),
                                    LIMITS, EXPRESS, ng.new_state())
    assert ng.public(found[0]) == {"step": "new_feeder", "cut_bus": "d"} and "amps=[80.0, 70.0, 60.0]" in found[0]["_detail"]
    # a lateral whose first line has a second circuit: both change phase, and both give its current
    lat2, _ = ng.apply_items(FILES, [{"step": "reconductor", "line": "lc", "linecode": "1P_OH_X", "circuits": 2}],
                             _catalog(), SUBSTATION, EXPRESS)
    files3 = dict(FILES, **lat2)
    net3 = ng.read_network(_text(files3))
    assert next(x for x in ng.single_phase_laterals(net3) if x["root"] == "h")["firsts"] == ["lc", "lc_ng1"]
    moved, _ = ng.apply_items(files3, [{"step": "rebalance_phases", "lateral": "h", "to_phase": 2}], _catalog(),
                              SUBSTATION, EXPRESS)
    assert moved["Lines.dss"].count("bus1=y.2 bus2=h.2") == 2 and "bus1=y.1 bus2=h.1" not in moved["Lines.dss"]
    at3 = {1: {"head": _amps(220.0, 150.0, 180.0), "lc": {1: 15.0}, "lc_ng1": {1: 15.0}, "fz1": {1: 45.0}}}
    items3 = ng.rebalance_moves(net3, ng.head_groups(net3, [_head(_amps(220.0, 150.0, 180.0))], at3, "largest_phase"), at3)
    assert [(i["lateral"], i["to_phase"], i["_peak"]) for i in items3] == [("h", 2, 30.0)]
    # the transformers of a regulator are never replaced by the transformer step
    rows = pl.transformer_rows(after, {"ngreg1_1": (5000.0, 2), "t1": (10.0, 2)}, DATES)
    assert ng.transformer_items(after, rows, _catalog(), NG, LIMITS) == []


def _short_line_files(lines_from_to=(), more_lines=""):
    """FILES with switch sw2 (1 m, d-e) on a 295 A code, more LineCodes, each (old, new)
    of lines_from_to replaced in Lines.dss, and more_lines appended."""
    codes = LINECODES + ("New Linecode.SW295 units=km nphases=3 Rmatrix=(0.01 ) Xmatrix=(0.01 ) normamps=295.0\n"
                         "New Linecode.UG595 units=km nphases=3 Rmatrix=(0.1 ) Xmatrix=(0.1 ) normamps=595.0\n"
                         "New Linecode.1P595 units=km nphases=1 Rmatrix=(0.1 ) Xmatrix=(0.1 ) normamps=595.0\n")
    lines = LINES.replace("bus1=d.1.2.3 bus2=e.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_B",
                          "bus1=d.1.2.3 bus2=e.1.2.3 switch=y enabled=y phases=3 Linecode=SW295")
    for old, new in lines_from_to:
        lines = lines.replace(old, new)
    return dict(FILES, **{"LineCodes.dss": codes, "Lines.dss": lines + more_lines})


def _regulator_amps(files, line, drop_mv=()):
    """The amps of the regulator built on line: its kVA / (base kV / sqrt(3)). drop_mv:
    buses taken out of the medium-voltage set before the regulator is built."""
    f = ng.Files(files)
    net = ng.read_network(f.text())
    net["mv"] -= set(drop_mv)
    row = ng._apply_regulator(f, net, {"step": "regulator", "line": line}, SUBSTATION)
    return row["kva"] / (12.47 / math.sqrt(3.0))


def test_regulator_rating_on_a_short_line():
    m3_595 = ("bus1=e.1.2.3 bus2=f.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_A",
              "bus1=e.1.2.3 bus2=f.1.2.3 switch=n enabled=y phases=3 Linecode=UG595")
    lb_595 = ("bus1=d.2 bus2=g.2 switch=n enabled=y phases=1 Linecode=1P_OH_X",
              "bus1=d.2 bus2=g.2 switch=n enabled=y phases=1 Linecode=1P595")
    # a regulator on the 1 m switch sw2 (295 A) beside the 100 m line m3 (595 A) takes 595 A
    files = _short_line_files([m3_595])
    assert math.isclose(_regulator_amps(files, "sw2"), 595.0)
    _, rows = ng.apply_items(files, [{"step": "regulator", "line": "sw2"}], _catalog(), SUBSTATION, EXPRESS)
    assert math.isclose(rows[0]["kva"], 595.0 * 12.47 / math.sqrt(3.0))
    # with nothing larger beside it, the switch keeps its own rating
    assert math.isclose(_regulator_amps(_short_line_files(), "sw2"), 295.0)
    # second circuits beside it: the branch counts with the sum of its circuits (2 x 200 A)
    two = ng.apply_items(_short_line_files(), [{"step": "reconductor", "line": "m3", "linecode": "3P_OH_B",
                                                "circuits": 2}], _catalog(), SUBSTATION, EXPRESS)[0]
    files2 = dict(_short_line_files(), **two)
    assert math.isclose(_regulator_amps(files2, "sw2"), 400.0)
    # a branch of lines of 1 m or less is skipped
    short = "New Line.sw4 Units=km Length=0.001 bus1=e.1.2.3 bus2=k.1.2.3 switch=y enabled=y phases=3 Linecode=UG595\n"
    assert math.isclose(_regulator_amps(_short_line_files(more_lines=short), "sw2"), 295.0)
    # a low-voltage branch is skipped
    branch = "New Line.lvk Units=km Length=0.05 bus1=e.1.2.3 bus2=k.1.2.3 switch=n enabled=y phases=3 Linecode=UG595\n"
    assert math.isclose(_regulator_amps(_short_line_files(more_lines=branch), "sw2"), 595.0)
    assert math.isclose(_regulator_amps(_short_line_files(more_lines=branch), "sw2", drop_mv=["k"]), 295.0)
    # a disabled branch is skipped
    off = branch.replace("enabled=y", "enabled=n")
    assert math.isclose(_regulator_amps(_short_line_files(more_lines=off), "sw2"), 295.0)
    # a regulator on a line longer than 1 m keeps the rating of its line: m2 (100 A) beside lb (595 A)
    assert math.isclose(_regulator_amps(_short_line_files([m3_595, lb_595]), "m2"), 100.0)
    assert math.isclose(_regulator_amps(_short_line_files([lb_595]), "sw2"), 595.0)


def _built_regcontrols(capsys, base_kv, ptratio):
    files = dict(FILES, **{"Master.dss": MASTER.replace("basekV=12.47", f"basekV={base_kv}")})
    substation = dict(SUBSTATION, regcontrol=dict(SUBSTATION["regcontrol"], ptratio=ptratio))
    capsys.readouterr()
    changed, _ = ng.apply_items(files, [{"step": "regulator", "line": "m2", "_peak": 0.92}], _catalog(), substation,
                                EXPRESS)
    added = changed["Transformers.dss"][len(TRANSFORMERS):].splitlines()
    printed = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[growth]")]
    return [a for a in added if a.startswith("New RegControl.")], printed


def test_built_regulator_copies_a_ptratio_that_fits(capsys):
    for base_kv, ptratio, written in [
        (12.47, 60.0, "60.0"),                                     # within 1 percent of 59.996: copied
        (25.0, 120.28130608117205, "120.28130608117205"),
        (4.0, 19.24, "19.24"),                                     # within 1 percent of 19.245: copied
    ]:
        regcontrols, printed = _built_regcontrols(capsys, base_kv, ptratio)
        assert regcontrols == [f"New RegControl.ngreg1_{p} transformer=ngreg1_{p} winding=2 vreg=123.6 band=1.992 "
                               f"ptratio={written}" for p in (1, 2, 3)]
        assert printed == []


def test_built_regulator_ptratio_from_its_own_voltage(capsys):
    regcontrols, printed = _built_regcontrols(capsys, 25.0, 60.0)
    assert regcontrols == [f"New RegControl.ngreg1_{p} transformer=ngreg1_{p} winding=2 vreg=123.6 band=1.992 "
                           f"ptratio=120.28130608117205" for p in (1, 2, 3)]
    assert printed == ["[growth] line regulator ngreg1_1, ngreg1_2, ngreg1_3: the substation RegControl's ptratio "
                       "60.0 does not fit the winding of 14.43375673 kV; ptratio 120.28130608117205 written"]


# ---------------------------------------------------------------------------
# The order of the steps (N7) and the substation units (N17)
# ---------------------------------------------------------------------------
def test_order_of_the_steps():
    net = ng.read_network(_text())
    head = _amps(230.0, 210.0, 205.0)
    at = {1: {"head": head, "sw1": _amps(90.0, 80.0, 85.0), "sw3": _amps(60.0, 50.0, 45.0)}}
    lines = _rows(net, {"head": 230.0, "m2": 140.0})
    trs = pl.transformer_rows(net, {"t1": (30.0, 4)}, DATES)
    low_v = {"load_c1": 0.92}

    def step(ng_settings, state=None, load_min=low_v, heads=None, line_rows=lines, tr_rows=trs):
        return ng.next_step(net, [heads or _head(head)], line_rows, tr_rows, at, load_min, _catalog(), SUBSTATION,
                            ng_settings, LIMITS, 0.95, EXPRESS, state or ng.new_state())

    assert step(NG)[0] == "new_feeder"                                   # the first step that applies
    assert step(dict(NG, steps=["reconductor", "service_transformer", "regulator"]))[0] == "reconductor"
    found = step(dict(NG, steps=["reconductor"]))
    assert sorted(i["line"] for i in found[1]) == ["head", "m2"]         # every line over its limit, the head too
    assert step(dict(NG, steps=["service_transformer", "regulator"]))[:1] == ("service_transformer",)
    assert step(dict(NG, steps=["regulator", "new_feeder"]))[0] == "regulator"
    assert step(dict(NG, steps=[])) == (None, [], [])                    # a step left out never runs
    ok = _head(_amps(100.0, 100.0, 100.0))
    assert step(NG, load_min={}, heads=ok, line_rows=_rows(net, {}), tr_rows=[]) == (None, [], [])
    # voltage above the band calls no step
    assert step(NG, load_min={"load_c1": 1.08}, heads=ok, line_rows=_rows(net, {}), tr_rows=[])[0] is None
    # under switch with no candidate the head is left out, and the lines go to the reconductor step
    none = {1: {"head": head, "sw1": _amps(1.0, 1.0, 1.0)}}
    state = ng.new_state()
    out = ng.next_step(net, [_head(head)], lines, trs, none, low_v, _catalog(), SUBSTATION, NG, LIMITS, 0.95,
                       EXPRESS, state)
    assert out[0] == "reconductor" and out[2] == ["no switch qualifies for head 1 (head)"]
    assert ("head", "3P_OH_B", 2) in [(i["line"], i["linecode"], i["circuits"]) for i in out[1]]
    assert state["no_feeder"] == {"head"}


# ---------------------------------------------------------------------------
# Voltage regulators: the feeder above with the head line replaced by a head regulator
# src-a and a single-phase regulator g0-g in the lateral at d
# ---------------------------------------------------------------------------
REG_HEAD = ("New Transformer.reg_head phases=3 windings=2 buses=(src.1.2.3,a.1.2.3) kvs=(12.47, 12.47) "
            "kvas=(10000.0, 10000.0) XHL=0.01\n")
REG_LAT = "New Transformer.reg_lb phases=1 windings=2 buses=(g0.2,g.2) kvs=(7.2, 7.2) kvas=(1000.0, 1000.0) XHL=0.01\n"
REG_FILES = dict(FILES, **{
    "Lines.dss": LINES.replace("New Line.head Units=km Length=0.1 bus1=src.1.2.3 bus2=a.1.2.3 switch=n enabled=y "
                               "phases=3 Linecode=3P_OH_B\n", "").replace("bus1=d.2 bus2=g.2", "bus1=d.2 bus2=g0.2"),
    "Transformers.dss": REG_HEAD + REG_LAT + TRANSFORMERS,
    "Master.dss": MASTER.replace("Line.head", "Transformer.reg_head")})


def _reg_head(amps, percent=None):
    return dict(_head(amps, percent, line="reg_head"), linecode="")


def test_regulators_in_the_network():
    net = ng.read_network(_text(REG_FILES))
    assert {"a", "b", "c", "d", "e", "f", "x", "y", "l1", "l2", "g0", "g", "h"} <= net["mv"]
    assert [ln["name"] for ln in ng.mv_path(net, "f")] == ["m1", "sw1", "m2", "sw2", "m3"]
    assert ng.path_length_m(net, "c") == 201.0
    # the catalog: a three-phase line beyond the head regulator is a medium-voltage line
    uses = ng.inventory({name.lower(): text for name, text in REG_FILES.items()})["uses"]
    assert uses["3|mv|OH"] == ["3p_oh_a", "3p_oh_b"] and "3|lv|OH" not in uses
    # a lateral that holds a regulator is a lateral, never moved by phase rebalancing
    assert [(x["root"], x["regulator"]) for x in growth.find_laterals(net)] == \
        [("g0", True), ("h", False), ("l1", False)]
    assert {x["root"]: x["node"] for x in ng.single_phase_laterals(net)} == {"h": 1, "l1": 1}
    # a regulator over its limit is no service transformer; a service transformer over its limit still is
    rows = pl.transformer_rows(net, {"reg_head": (12000.0, 4), "reg_lb": (1500.0, 4), "t1": (30.0, 4)}, DATES)
    assert [(i["transformer"], i["kva"], i["units"]) for i in ng.transformer_items(net, rows, _catalog(), NG, LIMITS)] \
        == [("t1", 50.0, 1)]
    # the line regulator network growth builds and a SMART-DS regulator are both crossed
    changed, _ = ng.apply_items(REG_FILES, [{"step": "regulator", "line": "m2"}], _catalog(), SUBSTATION, None)
    after = ng.read_network(_text(dict(REG_FILES, **changed)))
    assert growth.is_regulator(after["transformer_of"]["ngreg1_1"]) and growth.is_regulator(after["transformer_of"]["reg_head"])
    assert {"a", "c_ngreg1", "d", "e", "f", "g"} <= after["mv"]
    assert [ln["name"] for ln in ng.mv_path(after, "f")] == ["m1", "sw1", "m2", "sw2", "m3"]
    assert pl.line_rows(after, {}, DATES)[4]["line"] == "m3" and pl.line_rows(after, {}, DATES)[4]["level"] == "mv"


def test_head_on_a_regulator():
    net = ng.read_network(_text(REG_FILES))
    head = _amps(220.0, 150.0, 180.0)                       # 200 A rating: 110 percent
    at = {1: {"fz1": {1: 45.0}, "lc": {1: 30.0}, "lb": {2: 20.0}}}
    (group,) = ng.head_groups(net, [_reg_head(head)], at, "largest_phase")
    assert (group["k"], group["lines"], group["up"], group["down"], group["regulator"]) == \
        (1, ["reg_head"], "src", "a", True)
    assert (group["normamps"], group["percent"], group["amps"]) == (200.0, 110.0, head)
    # phase rebalancing works behind it: h (30 A) moves from phase 1 to phase 2
    items = ng.rebalance_moves(net, [group], at)
    assert [ng.public(i) for i in items] == [{"step": "rebalance_phases", "lateral": "h", "to_phase": 2}]
    # no new feeder, the head is no line to rebuild
    assert ng.new_feeder_choice(net, [group], _rows(net, {}), at, _catalog(), NG, LIMITS, None, ng.new_state()) == \
        ([], [])
    assert ng.reconductor_items(net, [group], _rows(net, {}), _catalog(region=True), NG, LIMITS) == []
    # the note on the head, once per circuit folder, with the steps of a run that builds nothing at a regulator
    state = ng.new_state()
    trs = pl.transformer_rows(net, {"reg_head": (12000.0, 4)}, DATES)
    args = (net, [_reg_head(head)], _rows(net, {"m2": 140.0}), trs, at, {}, _catalog(), SUBSTATION, NG_T, LIMITS,
            0.95, None, state)
    step, found, notes = ng.next_step(*args)
    assert step == "reconductor" and [i["line"] for i in found] == ["m2"]
    assert notes == ["head 1 is the regulator reg_head at 110 percent, over head_limit_percent; no new feeder is "
                     "built and nothing is rebuilt at the head",
                     "the regulator reg_head is at 120 percent of its kVA, over transformer_limit_percent; a "
                     "regulator is not a service transformer and is not replaced"]
    assert ng.next_step(*args)[2] == []
    # the line regulator step skips a line that starts at a bus fed by a regulator: the customers on both
    # sides of b share m1, which starts at a, behind the head regulator (with a line head, m1 is taken)
    under = {"load_h1": 0.93, "load_c1": 0.92}
    assert ng.regulator_choice(net, [group], under, SUBSTATION) == ([], [])
    line_net = ng.read_network(_text())
    assert ng.regulator_choice(line_net, _groups(line_net), under, SUBSTATION)[0][0]["line"] == "m1"
    assert ng.regulator_choice(net, [group], {"load_c1": 0.92}, SUBSTATION)[0][0]["line"] == "m3"
    # a new feeder on a circuit whose head 1 is a regulator stops
    try:
        ng.apply_items(REG_FILES, [{"step": "new_feeder", "open": "sw1", "feeder": "f1", "mix": "all"}], _catalog(),
                       SUBSTATION, None)
    except ng.NetworkGrowthError as e:
        assert "head 1 of feeder f1 is the regulator reg_head" in str(e)
    else:
        raise AssertionError("expected a stop")


# the feeder with the line head and the single-phase regulator g0-g in the lateral at d (load_h3 behind it),
# and the same lateral with a second regulator g-g2 after the first
LAT_FILES = dict(FILES, **{"Lines.dss": LINES.replace("bus1=d.2 bus2=g.2", "bus1=d.2 bus2=g0.2"),
                           "Transformers.dss": REG_LAT + TRANSFORMERS})
SERIES_FILES = dict(LAT_FILES, **{"Transformers.dss": REG_LAT + REG_LAT.replace("reg_lb", "reg_lb2").replace(
    "buses=(g0.2,g.2)", "buses=(g.2,g2.2)") + TRANSFORMERS.replace("bus=g.2 ", "bus=g2.2 ")})


def test_no_line_regulator_upstream_of_a_regulator():
    plain, lat, series = (ng.read_network(_text(files)) for files in (FILES, LAT_FILES, SERIES_FILES))
    assert [ln["name"] for ln in ng.customer_path(lat, "load_h3")] == ["head", "m1", "sw1", "m2", "lb"]
    # the deepest line shared by the customers under the band is lb, and the regulator g0-g sits between it
    # and load_h3: no item, one note naming the regulator nearest the line; without it the item is lb
    note = ("head 1: no line regulator on lb, since the regulator reg_lb sits between that line and 1 of the "
            "customers under the band")
    assert ng.regulator_choice(lat, _groups(lat), {"load_h3": 0.93}, SUBSTATION) == ([], [note])
    assert ng.regulator_choice(series, _groups(series), {"load_h3": 0.93}, SUBSTATION) == ([], [note])
    assert ng.regulator_choice(plain, _groups(plain), {"load_h3": 0.93}, SUBSTATION) == \
        ([{"step": "regulator", "line": "lb", "_peak": 0.93, "_detail": "head 1;customers=1"}], [])
    # one of the two customers under the band is behind the regulator: no item for the head
    under = {"load_h3": 0.93, "load_c1": 0.92}
    assert ng.regulator_choice(lat, _groups(lat), under, SUBSTATION) == \
        ([], ["head 1: no line regulator on m2, since the regulator reg_lb sits between that line and 1 of the "
              "customers under the band"])
    assert ng.regulator_choice(plain, _groups(plain), under, SUBSTATION) == \
        ([{"step": "regulator", "line": "m2", "_peak": 0.92, "_detail": "head 1;customers=2"}], [])
    # no regulator between the line and the customers: the item stands
    assert ng.regulator_choice(lat, _groups(lat), {"load_c1": 0.92}, SUBSTATION)[0][0]["line"] == "m3"


def test_substation_units():
    nc = {"transformers": [{"name": "t", "kva": 40000.0}]}
    tx = {"transformers": [{"name": "t", "kva": 16000.0}]}
    # ceil(85,000 / (40,000 x 0.75)) = 3 units in all; ceil(19,000 / (16,000 x 0.75)) = 2
    assert ng.substation_units(nc, 85000.0, 1, 75, True) == {"units_existing": 1, "unit_kva": 40000.0,
                                                              "units_in_all": 3, "units_added": 2}
    assert ng.substation_units(tx, 19000.0, 1, 75, True) == {"units_existing": 1, "unit_kva": 16000.0,
                                                              "units_in_all": 2, "units_added": 1}
    # within the limit: the existing units; under mode "off" the last two columns stay empty
    assert ng.substation_units(nc, 30000.0, 0, 75, True)["units_added"] == 0
    assert ng.substation_units(nc, 85000.0, 1, 75, False) == {"units_existing": 1, "unit_kva": 40000.0,
                                                               "units_in_all": None, "units_added": None}
    # a new unit copies the largest; never fewer than the existing units
    two = {"transformers": [{"name": "a", "kva": 10000.0}, {"name": "b", "kva": 20000.0}]}
    assert ng.substation_units(two, 31000.0, 1, 100, True) == {"units_existing": 2, "unit_kva": 20000.0,
                                                                "units_in_all": 2, "units_added": 0}
    assert ng.substation_units(two, 61000.0, 1, 100, True)["units_in_all"] == 4
    assert ng.substation_units({"transformers": []}, 5.0, None, 75, True)["units_existing"] == 0


# ---------------------------------------------------------------------------
# Regulators in the building rules: the settings, a larger rating, a new feeder behind a
# copy of the head regulator, the notes and the Phase 8 column
# ---------------------------------------------------------------------------
REG_CONTROL = "New RegControl.rc_head transformer=REG_HEAD winding=2 ptratio=59.99631547328862 band=2.4 vreg = 123.6\n"
REG_FILES_RC = dict(REG_FILES, **{"Regulators.dss": REG_CONTROL})
# another feeder folder of the region with three-phase 12.47 kV regulators of 16,000 and 31,500 kVA
REG_OTHER = {"linecodes.dss": LINECODES, "lines.dss": "", "loads.dss": "",
             "master.dss": "New Circuit.other bus1=o basekV=12.47\n",
             "transformers.dss": "New Transformer.big16 phases=3 windings=2 buses=(o.1.2.3,p.1.2.3) kvs=(12.47, 12.47) "
                                 "kvas=(16000.0, 16000.0) XHL=0.02\n"
                                 "New Transformer.big31 phases=3 windings=2 buses=(p.1.2.3,q.1.2.3) kvs=(12.47, 12.47) "
                                 "kvas=(31500.0, 31500.0) XHL=0.03\n"}


def _reg_catalog(ratings=("big16", "big31")):
    other = dict(REG_OTHER, **{"transformers.dss": "".join(
        ln + "\n" for ln in REG_OTHER["transformers.dss"].splitlines() if ln.split()[1][12:] in ratings)})
    return ng.build_catalog(ng.inventory({name.lower(): text for name, text in REG_FILES.items()}),
                            [ng.inventory(other)])


def test_regulator_settings_and_items():
    for changes in ({"new_feeder_regulator": "always"}, {"new_feeder_regulator": None},
                    {"new_feeder_regulator": False}, {"steps": ["regulator_rating", "regulator_rating"]},
                    {"steps": ["rating"]}):
        assert _stops(growth_settings, _with(**changes)), changes
    for value in ("copy", "none", "skip"):
        assert growth_settings(_with(new_feeder_regulator=value))["network_growth"]["new_feeder_regulator"] == value
    assert growth_settings(_with(steps=["regulator_rating"]))["network_growth"]["steps"] == ["regulator_rating"]
    item = {"feeder": "f", "mix": "all", "step": "regulator_rating", "transformer": "reg_head", "kva": 16000.0}
    assert network_item_error(item) is None and network_item_error(dict(item, round=2)) is None
    for bad in (dict(item, kva=0), dict(item, transformer=""), dict(item, units=1),
                {k: v for k, v in item.items() if k != "kva"}):
        assert network_item_error(bad) is not None, bad
    assert ng.ITEM_STEPS[-2:] == ("regulator_rating", "regulator")


def test_retarget_a_buses_array():
    # the wdg= and bus= form, as before
    assert ng.retarget("New Transformer.x wdg=1 bus=a.1 kv=7.2 wdg=2 bus=b.1.0 kv=0.12", "y", ["p.2", "q.1.0"]) == \
        "New Transformer.y wdg=1 bus=p.2 kv=7.2 wdg=2 bus=q.1.0 kv=0.12"
    # the buses= array of the release: each element takes the bus of its winding, the rest as written
    big = "New Transformer.big16 phases=3 windings=2 buses=(o.1.2.3,p.1.2.3) kvs=(12.47, 12.47) kvas=(16000.0, 16000.0)"
    assert ng.retarget(big, "reg_head", ["src.1.2.3", "a.1.2.3"]) == \
        "New Transformer.reg_head phases=3 windings=2 buses=(src.1.2.3,a.1.2.3) kvs=(12.47, 12.47) kvas=(16000.0, 16000.0)"
    assert ng.retarget("New Transformer.r buses=[o.2 p.2] kvs=[7.2 7.2]", "s", ["x.3", "y.3"]) == \
        "New Transformer.s buses=[x.3 y.3] kvs=[7.2 7.2]"
    assert ng.retarget("New Transformer.r Buses='o.2, p.2'", "s", ["x.3", "y.3"]) == "New Transformer.s Buses='x.3, y.3'"
    assert _raises(ng.retarget, big, "reg_head", ["src.1.2.3"])


def _rating(peaks, catalog=None, heads=None, limits=LIMITS, files=REG_FILES, state=None):
    net = ng.read_network(_text(files))
    rows = pl.transformer_rows(net, {name: (kva, 4) for name, kva in peaks.items()}, DATES)
    groups = ng.head_groups(net, heads or [], {1: {}}, "largest_phase")
    return ng.regulator_rating_items(net, groups, rows, catalog or _reg_catalog(), NG, limits, state or ng.new_state())


def test_regulator_rating_rules_and_statements():
    # reg_head: 10,000 kVA, three-phase, 12.47 kV. 75 percent of 16,000 kVA is 12,000 kVA
    items, notes = _rating({"reg_head": 11000.0})
    assert [ng.public(i) for i in items] == [{"step": "regulator_rating", "transformer": "reg_head", "kva": 16000.0}]
    assert items[0]["_peak"] == 11000.0 and notes == []
    assert _rating({"reg_head": 13000.0})[0][0]["kva"] == 31500.0           # the smallest that carries it by sizing
    only16 = _reg_catalog(("big16",))
    assert _rating({"reg_head": 13000.0}, only16)[0][0]["kva"] == 16000.0    # the largest, within its limit
    assert _rating({"reg_head": 9000.0}) == ([], [])                         # within its limit: nothing
    # no rating passes: nothing is built, and one note per circuit folder
    state = ng.new_state()
    items, notes = _rating({"reg_head": 17000.0}, only16, state=state)
    assert items == [] and notes == ["the regulator reg_head is at 170 percent, over transformer_limit_percent; the "
                                     "catalog holds no larger rating of its class 3|12.47,12.47 that carries it, and "
                                     "a regulator is not paralleled"]
    assert _rating({"reg_head": 17000.0}, only16, state=state) == ([], [])
    items, notes = _rating({"reg_lb": 1500.0})                               # no larger rating of its class
    assert items == [] and "the regulator reg_lb is at 150 percent" in notes[0] and "class 1|7.2,7.2" in notes[0]
    # a regulator network growth built is left out, and so is a service transformer
    built, _ = ng.apply_items(REG_FILES, [{"step": "regulator", "line": "m2"}], _catalog(), SUBSTATION, None)
    assert _rating({"ngreg1_1": 9000.0, "t1": 30.0}, files=dict(REG_FILES, **built)) == ([], [])
    # a head regulator over head_limit_percent only (its kVA within transformer_limit_percent)
    head = _reg_head(_amps(220.0, 150.0, 180.0))                             # 110 percent
    items, _ = _rating({"reg_head": 9000.0}, heads=[head])
    assert [(i["transformer"], i["kva"]) for i in items] == [("reg_head", 16000.0)]
    items, notes = _rating({"reg_head": 9000.0}, _reg_catalog(()), heads=[head])
    assert items == [] and notes[0].startswith("the regulator reg_head is at 110 percent, over head_limit_percent")
    # the statement: the catalog's, under the regulator's name and on its buses, in its place; the RegControl stays
    changed, rows = ng.apply_items(REG_FILES_RC, [{"step": "regulator_rating", "transformer": "reg_head",
                                                   "kva": 16000.0, "_peak": 11000.0}], _reg_catalog(), SUBSTATION, None)
    assert sorted(changed) == ["Transformers.dss"]
    assert changed["Transformers.dss"].splitlines()[0] == (
        "New Transformer.reg_head phases=3 windings=2 buses=(src.1.2.3,a.1.2.3) kvs=(12.47, 12.47) "
        "kvas=(16000.0, 16000.0) XHL=0.02")
    assert changed["Transformers.dss"].splitlines()[1:] == REG_FILES["Transformers.dss"].splitlines()[1:]
    assert {k: rows[0][k] for k in ("step", "element", "was", "now", "count_before", "count", "kva", "peak")} == \
        {"step": "regulator_rating", "element": "reg_head", "was": 10000.0, "now": 16000.0, "count_before": 1,
         "count": 1, "kva": 16000.0, "peak": 11000.0}
    assert rows[0]["changed"] == [("transformer", "reg_head")]
    # a planned item of this step is checked like the others
    for bad in ({"transformer": "t1", "kva": 50.0}, {"transformer": "reg_head", "kva": 20000.0},
                {"transformer": "nope", "kva": 16000.0}):
        assert _raises(ng.apply_items, REG_FILES, [dict(bad, step="regulator_rating")], _reg_catalog(), SUBSTATION,
                       None)
    assert _raises(ng.apply_items, dict(REG_FILES, **built),
                   [{"step": "regulator_rating", "transformer": "ngreg1_1", "kva": 16000.0}], _reg_catalog(),
                   SUBSTATION, None)
    # in the order of the steps: capacity before voltage, after the service transformers
    net = ng.read_network(_text(REG_FILES))
    trs = pl.transformer_rows(net, {"reg_head": (11000.0, 4), "t1": (30.0, 4)}, DATES)
    args = (net, [_reg_head(_amps(90.0, 90.0, 90.0))], _rows(net, {}), trs, {1: {}}, {}, _reg_catalog(), SUBSTATION)
    assert ng.next_step(*args, NG, LIMITS, 0.95, None, ng.new_state())[0] == "service_transformer"
    step, items, _ = ng.next_step(*args, dict(NG, steps=["regulator_rating", "service_transformer"]), LIMITS, 0.95,
                                  None, ng.new_state())
    assert step == "regulator_rating" and [i["transformer"] for i in items] == ["reg_head"]
    assert ng.next_step(*args, NG_T, LIMITS, 0.95, None, ng.new_state())[0] == "service_transformer"


def test_regulator_notes_by_the_settings():
    net = ng.read_network(_text(REG_FILES))
    groups = ng.head_groups(net, [_reg_head(_amps(220.0, 150.0, 180.0))], {1: {}}, "largest_phase")
    trs = pl.transformer_rows(net, {"reg_head": (12000.0, 4)}, DATES)
    head_note = ("head 1 is the regulator reg_head at 110 percent, over head_limit_percent; no new feeder is built "
                 "and nothing is rebuilt at the head")
    tr_note = ("the regulator reg_head is at 120 percent of its kVA, over transformer_limit_percent; a regulator is "
               "not a service transformer and is not replaced")

    def notes(settings):
        return ng.regulator_notes(net, groups, trs, LIMITS, ng.new_state(), settings)

    # the settings of today: both notes as before (no settings at all gives the same)
    assert notes(NG_T) == [head_note, tr_note] == notes(None)
    # the defaults: a step can act on both, so no note
    assert notes(NG) == []
    assert notes(dict(NG, steps=["new_feeder"])) == [tr_note]                # a new feeder is built at the head
    assert notes(dict(NG, steps=["new_feeder"], new_feeder_regulator="skip")) == [head_note, tr_note]
    assert notes(dict(NG_T, steps=["regulator_rating"])) == []               # the rating step acts on both
    # a regulator network growth built is never replaced: its note stays under the defaults
    built, _ = ng.apply_items(REG_FILES, [{"step": "regulator", "line": "m2"}], _catalog(), SUBSTATION, None)
    after = ng.read_network(_text(dict(REG_FILES, **built)))
    rows = pl.transformer_rows(after, {"ngreg1_1": (12000.0, 4)}, DATES)
    found = ng.regulator_notes(after, [], rows, LIMITS, ng.new_state(), NG)
    assert found[0].startswith("the regulator ngreg1_1 is at ") and found[0].endswith("is not replaced")


def test_note_of_a_head_regulator_no_step_acts_on():
    net = ng.read_network(_text(REG_FILES_RC))
    head = _reg_head(_amps(220.0, 150.0, 180.0))                           # 110 percent of 200 A
    at = {1: {"sw1": _amps(90.0, 80.0, 85.0), "sw3": _amps(60.0, 50.0, 45.0)}}
    express = {mode: ng.regulator_express(net, head, mode, _text(REG_FILES_RC)) for mode in ("copy", "none")}
    note = ("head 1 is the regulator reg_head at 110 percent, over head_limit_percent; the catalog holds a larger "
            "rating of its class 3|12.47,12.47 and regulator_rating is not in steps, so no new feeder is built and "
            "nothing is rebuilt at the head")
    head_note = ("head 1 is the regulator reg_head at 110 percent, over head_limit_percent; no new feeder is built "
                 "and nothing is rebuilt at the head")
    only = dict(NG, steps=["new_feeder"])
    trs = pl.transformer_rows(net, {"reg_head": (9000.0, 4)}, DATES)          # within its kVA

    def step(settings, catalog, state=None, peaks=None):
        found = ng.next_step(net, [head], _rows(net, peaks or {}), trs, at, {}, catalog, SUBSTATION, settings, LIMITS,
                             0.95, express.get(settings["new_feeder_regulator"]), state or ng.new_state())
        return found[0], [ng.public(i) for i in found[1]], found[2]

    # the defaults: the rating step replaces the regulator, no note
    assert step(NG, _reg_catalog()) == ("regulator_rating", [{"step": "regulator_rating", "transformer": "reg_head",
                                                               "kva": 16000.0}], [])
    # new_feeder alone under copy, no larger rating of its class: a new feeder, no note
    assert step(only, _catalog()) == ("new_feeder", [{"step": "new_feeder", "open": "sw1"}], [])
    # new_feeder alone under copy or none, a larger rating of its class: nothing is built, and the note says why
    assert step(only, _reg_catalog()) == (None, [], [note])
    assert step(dict(only, new_feeder_regulator="none"), _reg_catalog()) == (None, [], [note])
    # skip: the head note of regulator_notes, as before
    assert step(dict(only, new_feeder_regulator="skip"), _reg_catalog()) == (None, [], [head_note])
    # once per circuit folder: the second call on one state gives no note
    state = ng.new_state()
    assert step(only, _reg_catalog(), state) == (None, [], [note])
    assert step(only, _reg_catalog(), state) == (None, [], [])
    (group,) = ng.head_groups(net, [head], at, "largest_phase")
    assert ng.new_feeder_choice(net, [group], _rows(net, {}), at, _reg_catalog(), only, LIMITS, express["copy"],
                                state) == ([], [])
    # regulator_rating in the steps, or a stuck line behind the head (m1, the largest code): no note
    assert step(dict(only, steps=["new_feeder", "regulator_rating"]), _reg_catalog())[2] == []
    assert step(only, _reg_catalog(), peaks={"m1": 250.0}) == ("new_feeder", [{"step": "new_feeder", "open": "sw1"}],
                                                               [])
    # the settings T: the notes of before
    assert step(NG_T, _reg_catalog()) == (None, [], [head_note])
    assert step(NG_T, _catalog()) == (None, [], [head_note])


def test_new_feeder_on_a_regulator_head():
    net = ng.read_network(_text(REG_FILES_RC))
    head = _reg_head(_amps(220.0, 150.0, 180.0))                           # 110 percent of 200 A
    at = {1: {"sw1": _amps(90.0, 80.0, 85.0), "sw3": _amps(60.0, 50.0, 45.0)}}
    (group,) = ng.head_groups(net, [head], at, "largest_phase")
    text = _text(REG_FILES_RC)
    # the express LineCode: the largest normamps among the three-phase lines that leave the regulator (m1 and
    # sw3, both 200 A: the first name, m1); its normamps that of the head under copy, of the code under none
    copy = ng.regulator_express(net, head, "copy", text)
    assert copy == {"linecode": "3P_OH_B", "normamps": 200.0, "regulator": "copy", "head": "reg_head",
                    "regcontrol": "rc_head"}
    larger = dict(REG_FILES_RC, **{"LineCodes.dss": LINECODES + "New Linecode.3P_OH_C units=km nphases=3 "
                                                                "Rmatrix=(0.1 ) Xmatrix=(0.5 ) normamps=400.0\n",
                                   "Lines.dss": REG_FILES["Lines.dss"].replace(
                                       "bus1=a.1.2.3 bus2=x.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_B",
                                       "bus1=a.1.2.3 bus2=x.1.2.3 switch=y enabled=y phases=3 Linecode=3P_OH_C")})
    net_c = ng.read_network(_text(larger))
    assert ng.regulator_express(net_c, head, "none", _text(larger))["linecode"] == "3P_OH_C"
    assert ng.regulator_express(net_c, head, "none", _text(larger))["normamps"] == 400.0
    assert ng.regulator_express(net_c, head, "copy", _text(larger))["normamps"] == 200.0
    none = ng.regulator_express(net, head, "none", _text(REG_FILES))
    assert none == {"linecode": "3P_OH_B", "normamps": 200.0, "regulator": "none", "head": "reg_head",
                    "regcontrol": None}
    assert ng.regulator_express(ng.read_network(_text()), _head(_amps(1.0, 1.0, 1.0)), "copy", _text()) is None

    def choose(express, settings, catalog=None):
        return ng.new_feeder_choice(net, [group], _rows(net, {}), at, catalog or _catalog(), settings, LIMITS, express,
                                    ng.new_state())

    # copy and none: the regulator head over its limit with no larger rating of its class qualifies
    items, notes = choose(copy, NG)
    assert [ng.public(i) for i in items] == [{"step": "new_feeder", "open": "sw1"}] and notes == []
    assert ng.public(choose(none, dict(NG, new_feeder_regulator="none"))[0][0]) == {"step": "new_feeder", "open": "sw1"}
    assert choose(copy, dict(NG, new_feeder_regulator="skip")) == ([], [])     # skip: as before
    assert choose(None, NG) == ([], [])                                        # no express: as before
    assert choose(copy, NG, _reg_catalog()) == ([], [])                        # a larger rating of its class exists
    # a head regulator without a RegControl gets a note under copy
    assert choose(dict(copy, regcontrol=None), NG)[1] == [
        "head 1: the head regulator reg_head has no RegControl; the regulator copied for the new feeder has none"]

    # copy: the express line starts behind a copy of the head regulator and its RegControl
    changed, rows = ng.apply_items(REG_FILES_RC, [{"step": "new_feeder", "open": "sw1", "_peak": 220.0}], _catalog(),
                                   SUBSTATION, copy)
    assert sorted(changed) == ["Buscoords.dss", "Lines.dss", "Master.dss", "Regulators.dss", "Transformers.dss"]
    assert changed["Transformers.dss"] == REG_FILES["Transformers.dss"] + (
        "New Transformer.ng_express_2_reg phases=3 windings=2 buses=(src.1.2.3,ng_express_2_bus.1.2.3) "
        "kvs=(12.47, 12.47) kvas=(10000.0, 10000.0) XHL=0.01\n")
    assert changed["Regulators.dss"] == REG_CONTROL + ("New RegControl.ng_express_2_reg transformer=ng_express_2_reg "
                                                       "winding=2 ptratio=59.99631547328862 band=2.4 vreg = 123.6\n")
    assert changed["Lines.dss"].endswith("New Line.ng_express_2 Units=m Length=201.0 bus1=ng_express_2_bus.1.2.3 "
                                         "bus2=c.1.2.3 switch=n enabled=y phases=3 Linecode=3P_OH_B\n")
    assert changed["Buscoords.dss"] == BUSCOORDS + "ng_express_2_bus 0.0 0.0\n"
    master = changed["Master.dss"].splitlines()
    assert ["New Monitor.h2m1 element=Transformer.ng_express_2_reg mode=0",
            "New Monitor.h2m2 element=Transformer.ng_express_2_reg mode=1"] == \
        [ln for ln in master if ln.startswith("New Monitor.h2")]
    assert pl.head_lines(changed["Master.dss"]) == [(1, "reg_head"), (2, "ng_express_2_reg")]
    assert pl.head_classes(changed["Master.dss"]) == {1: "transformer", 2: "transformer"}
    assert (rows[0]["element"], rows[0]["was"], rows[0]["now"], rows[0]["length_m"]) == \
        ("ng_express_2", "sw1", "3P_OH_B", 201.0)
    # the circuit after the step: c and beyond hang on the express line behind the copied regulator, a head
    # group of its own with the rating of the head regulator
    after = ng.read_network(_text(dict(REG_FILES_RC, **changed)))
    assert after["parent"]["c"][1]["name"] == "ng_express_2" and not after["extra_lines"]
    assert after["parent"]["ng_express_2_bus"][1]["name"] == "ng_express_2_reg"
    copied = after["transformer_of"]["ng_express_2_reg"]
    assert growth.is_regulator(copied) and copied["windings"][0][3] == 10000.0
    assert {"ng_express_2_bus", "c", "d", "f"} <= after["mv"]
    rows2 = [head, dict(_reg_head(_amps(90.0, 80.0, 85.0)), head=2, line="ng_express_2_reg")]
    groups = ng.head_groups(after, rows2, {1: {}, 2: {}}, "largest_phase")
    assert [(g["k"], g["lines"], g["up"], g["down"], g.get("regulator")) for g in groups] == \
        [(1, ["reg_head"], "src", "a", True), (2, ["ng_express_2_reg"], "src", "ng_express_2_bus", True)]
    # without a RegControl the regulator is copied alone
    alone, _ = ng.apply_items(REG_FILES, [{"step": "new_feeder", "open": "sw1"}], _catalog(), SUBSTATION,
                              dict(copy, regcontrol=None))
    assert "New Transformer.ng_express_2_reg " in alone["Transformers.dss"] and "Regulators.dss" not in alone
    # none: the express line starts at the source bus, with its Monitors on the line
    changed, _ = ng.apply_items(REG_FILES_RC, [{"step": "new_feeder", "cut_bus": "c"}], _catalog(), SUBSTATION, none)
    assert sorted(changed) == ["Lines.dss", "Master.dss"]
    assert changed["Lines.dss"].endswith("New Line.ng_express_2 Units=m Length=201.0 bus1=src.1.2.3 bus2=c.1.2.3 "
                                         "switch=n enabled=y phases=3 Linecode=3P_OH_B\n")
    assert pl.head_lines(changed["Master.dss"]) == [(1, "reg_head"), (2, "ng_express_2")]
    assert pl.head_classes(changed["Master.dss"]) == {1: "transformer", 2: "line"}
    # skip: a planned item stops, as before
    assert _raises(ng.apply_items, REG_FILES_RC, [{"step": "new_feeder", "open": "sw1"}], _catalog(), SUBSTATION,
                   dict(copy, regulator="skip"))


def test_block_copy_of_a_regulator_lateral_is_not_moved():
    # the lateral at d holds the regulator g0-g; its block copy at c holds a copy of it
    net = ng.read_network(_text(LAT_FILES))
    lat = next(x for x in growth.find_laterals(net) if x["root"] == "g0")
    new = growth.copy_lateral(net, lat, "b1", "c")
    files = dict(LAT_FILES, **{"Lines.dss": LAT_FILES["Lines.dss"] + "".join(t + "\n" for t in new["lines"]),
                               "Transformers.dss": LAT_FILES["Transformers.dss"]
                               + "".join(t + "\n" for t in new["transformers"])})
    grown = ng.read_network(_text(files))
    assert {(x["root"], x["regulator"]) for x in growth.find_laterals(grown)} >= {("g0", True), ("g0_gb1", True)}
    assert not {"g0", "g0_gb1"} & {x["root"] for x in ng.single_phase_laterals(grown)}


def test_summary_counts_the_replaced_regulators():
    # Phase 8 writes network_growth_summary.csv in its main block: its last column counts the rows of
    # network_growth.csv whose step is regulator_rating
    with open(os.path.join(REPO_ROOT, "8_results_analysis", "aggregate_m1_m2_with_circuits.py"), encoding="utf-8") as f:
        source = f.read()
    row = source[source.index("growth_summary_rows.append({"):]
    row = row[:row.index("})") + 2]
    assert row.endswith('"regulators_replaced": len(by_step["regulator_rating"])})')
    assert "regulator_rating" in ng.ITEM_STEPS
