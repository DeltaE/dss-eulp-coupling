# -*- coding: utf-8 -*-
"""
Tests of the planning limits of a grown circuit
(7_circuit_instantiation/deployer_modules/planning_limits.py) on synthetic tables and
the small synthetic feeder of test_growth.py. No OpenDSS.
"""

import math
import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
import growth  # noqa: E402
import planning_limits as pl  # noqa: E402
from pipeline_utils import growth_settings, load_growth, planning_band  # noqa: E402
from test_growth import MASTER, TEXTS  # noqa: E402

LIMITS = {"line_limit_percent": 100, "head_limit_percent": 100, "transformer_limit_percent": 100,
          "substation_limit_percent": 100}
DATES = ["2018-06-16", "2018-06-17"]


class _Monitors:
    """The part of the engine's Monitors interface that read_loading uses."""

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


def test_loading_monitors():
    net = growth.read_feeder(TEXTS)
    text, line_mon, tr_mon = pl.loading_monitor_lines(net)
    assert len(line_mon) == 11 and len(tr_mon) == 4            # the open tie has no monitor
    assert "tie" not in line_mon.values() and set(tr_mon.values()) == {"t1", "t2", "t3", "t4"}
    assert text[0] == "New Monitor.ml_1 element=Line.head terminal=1 mode=0\n"
    assert text[11] == "New Monitor.mx_1 element=Transformer.t1 terminal=1 mode=1 ppolar=no\n"
    assert len(set(line_mon) | set(tr_mon)) == 15


def test_peaks_from_monitor_channels():
    header = [" V1", " VAngle1", " V2", " VAngle2", " I1", " IAngle1", " I2", " IAngle2"]
    values = {" V1": [7200.0] * 3, " VAngle1": [0.0] * 3, " V2": [7200.0] * 3, " VAngle2": [-120.0] * 3,
              " I1": [10.0, 30.0, 20.0], " IAngle1": [0.0] * 3, " I2": [12.0, 25.0, 45.0], " IAngle2": [0.0] * 3}
    assert pl.peak_current(header, lambda i: values[header[i - 1]]) == (45.0, 3)
    header = ["P1 (kW)", "Q1 (kvar)", "P2 (kW)", "Q2 (kvar)"]
    values = {"P1 (kW)": [3.0, 30.0], "Q1 (kvar)": [4.0, 0.0], "P2 (kW)": [0.0, 10.0], "Q2 (kvar)": [0.0, 30.0]}
    kva, step = pl.peak_kva(header, lambda i: values[header[i - 1]])
    assert math.isclose(kva, 50.0) and step == 2               # (30 + 10, 0 + 30) -> 50 kVA
    for bad in (["V1", "VAngle1"], ["S1 (kVA)", "Ang1"]):
        try:
            (pl.peak_current if bad[0] == "V1" else pl.peak_kva)(bad, lambda i: [0.0])
        except ValueError:
            continue
        raise AssertionError("expected a stop")
    circuit = _Circuit({"ml_1": {"V1": [1.0, 1.0], "I1": [5.0, 9.0]},
                        "mx_1": {"P1 (kW)": [6.0, 3.0], "Q1 (kvar)": [8.0, 4.0]}})
    assert pl.read_loading(circuit, {"ml_1": "head"}, {"mx_1": "t1"}) == ({"head": (9.0, 2)}, {"t1": (10.0, 1)})


def test_loading_percentages_and_the_short_flag():
    net = growth.read_feeder(TEXTS)
    peaks = {"head": (300.0, 5), "main2": (410.0, 100), "fuse1": (250.0, 97), "lat1": (60.0, 1)}
    rows = {r["line"]: r for r in pl.line_rows(net, peaks, DATES, ["LAT1"])}
    assert len(rows) == 12                                      # every line of the circuit, the open tie too
    assert math.isclose(rows["head"]["loading_percent"], 75.0) and rows["head"]["normamps"] == 400.0
    assert math.isclose(rows["main2"]["loading_percent"], 102.5)
    assert rows["main2"]["peak_step"] == 100 and rows["main2"]["peak_date"] == "2018-06-17"
    assert rows["head"]["peak_date"] == "2018-06-16"
    assert rows["fuse1"]["short"] == 1 and math.isclose(rows["fuse1"]["loading_percent"], 250.0)
    assert rows["lat1"]["short"] == 0 and rows["lat1"]["new"] == 1 and rows["head"]["new"] == 0
    assert rows["tie"]["enabled"] == 0 and rows["tie"]["short"] == 1 and rows["tie"]["loading_percent"] is None
    assert rows["s1"]["loading_percent"] is None                # no monitor value: not checked
    assert rows["head"]["level"] == "mv" and rows["lat1"]["level"] == "mv" and rows["s1"]["level"] == "lv"
    assert pl.SHORT_LINE_M == 1.0

    trs = {r["transformer"]: r for r in pl.transformer_rows(net, {"t1": (30.0, 7), "t3": (75.0, 190)}, DATES, ["t3"])}
    assert len(trs) == 4 and math.isclose(trs["t1"]["loading_percent"], 120.0) and trs["t1"]["kva"] == 25.0
    assert math.isclose(trs["t3"]["loading_percent"], 50.0) and trs["t3"]["new"] == 1
    assert trs["t3"]["peak_date"] == "2018-06-17" and trs["t2"]["loading_percent"] is None

    head_kva = np.array([1000.0, 9000.0, 4000.0])
    rating, head_line = pl.head_rating(net, MASTER)
    assert head_line == "head" and math.isclose(rating, 400.0 * 12.47 * math.sqrt(3.0))
    out = {r["limit"]: r for r in pl.limit_rows(list(rows.values()), list(trs.values()), head_kva, rating,
                                                head_line, LIMITS, DATES)}
    # the short line (250 percent) is left out of the line limit; the worst is main2
    assert out["line"]["elements_checked"] == 3 and out["line"]["elements_over"] == 1
    assert out["line"]["worst_element"] == "main2" and math.isclose(out["line"]["worst_value"], 102.5)
    assert out["line"]["worst_step"] == 100 and out["line"]["worst_date"] == "2018-06-17"
    assert out["transformer"]["elements_checked"] == 2 and out["transformer"]["elements_over"] == 1
    assert out["transformer"]["worst_element"] == "t1"
    assert out["head"]["elements_checked"] == 1 and out["head"]["elements_over"] == 1
    assert math.isclose(out["head"]["worst_value"], 100.0 * 9000.0 / rating) and out["head"]["worst_step"] == 2
    # each limit is a setting: at 75 percent the head line of 75 percent is not over, main2 still is
    tight = {r["limit"]: r for r in pl.limit_rows(list(rows.values()), list(trs.values()), head_kva, rating,
                                                  head_line, dict(LIMITS, line_limit_percent=75,
                                                                  transformer_limit_percent=40,
                                                                  head_limit_percent=200), DATES)}
    assert tight["line"]["elements_over"] == 1 and tight["transformer"]["elements_over"] == 2
    assert tight["head"]["elements_over"] == 0
    loose = pl.limit_rows(list(rows.values()), list(trs.values()), head_kva, None, None, LIMITS, DATES)[1]
    assert loose["elements_checked"] == 0 and loose["worst_value"] is None    # no rating: nothing to check


def test_head_series_as_phase_8():
    frame = pd.DataFrame({"hour": [0, 0], " t(sec)": [900, 1800], " S1 (kVA)": [100.0, 50.0], " Ang1": [0.0, 90.0],
                          " S2 (kVA)": [100.0, 50.0], " Ang2": [0.0, 90.0], " S3 (kVA)": [100.0, 0.0],
                          " Ang3": [60.0, 0.0]})
    kva, p, q = pl.head_series(frame)
    assert np.allclose(p, [250.0, 0.0]) and np.allclose(q, [100.0 * math.sin(math.radians(60.0)), 100.0])
    assert np.allclose(kva, np.hypot(p, q))
    try:
        pl.head_series(pd.DataFrame({"hour": [0]}))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a stop")


def test_voltage_rows_and_band_values():
    frame = pd.DataFrame({
        "load": ["load_a_1", "load_a_2", "load_b", "load_b", "load_c_1", "EVu_load_a_1"],
        "step": [1, 1, 97, 98, 5, 1],
        "v_pu": [0.96, 0.93, 1.02, 1.07, 1.00, 0.80],
        "ev_leg": [False, False, False, False, False, True]})
    rows = {r["limit"]: r for r in pl.voltage_rows(frame, 0.95, 1.05, DATES)}
    assert rows["voltage_band"]["elements_checked"] == 3 and rows["voltage_band"]["elements_over"] == 2
    assert rows["voltage_band"]["worst_element"] == "load_a_2" and rows["voltage_band"]["worst_value"] == 0.93
    assert rows["voltage_low"]["elements_over"] == 1 and rows["voltage_low"]["worst_date"] == "2018-06-16"
    assert rows["voltage_high"]["elements_over"] == 1 and rows["voltage_high"]["worst_element"] == "load_b"
    assert rows["voltage_high"]["worst_step"] == 98 and rows["voltage_high"]["worst_date"] == "2018-06-17"
    # the EV leg at 0.80 pu is left out; a wider band has no customer outside
    assert pl.voltage_rows(frame, 0.9167, 1.0583, DATES)[1]["elements_over"] == 0
    assert pl.voltage_rows(frame, 0.9167, 1.0583, DATES)[2]["elements_over"] == 1
    # the band values of growth.yaml: ANSI C84.1 on a 120 V base
    g = growth_settings(load_growth(settings_dir=""))
    bands = g["planning_limits"]["voltage_bands"]
    assert bands["range_a"] == [0.95, 1.05] and [round(v * 120) for v in bands["range_a"]] == [114, 126]
    assert bands["range_b"] == [0.9167, 1.0583] and [round(v * 120) for v in bands["range_b"]] == [110, 127]
    assert planning_band(g, {"voltage_band": {"low_pu": 0.95, "high_pu": 1.05}}) == (0.95, 1.05)


def test_block_rows():
    net = growth.read_feeder(TEXTS)
    lines = pl.line_rows(net, {"head": (300.0, 1), "main2": (440.0, 3), "main3": (100.0, 2)}, DATES)
    units = [{"unit": "b1", "loads": [{"name": "load_h1_gb1_1"}, {"name": "load_h1_gb1_2"}]}]
    frame = pd.DataFrame({"load": ["load_h1_gb1_1", "load_h1_gb1_2", "load_h1_1"], "step": [1, 2, 1],
                          "v_pu": [0.97, 0.94, 0.90], "ev_leg": [False] * 3})
    blocks = [{"Feeder": "f", "block": "1", "unit": "b1", "built": "1", "attach_bus": "c"},
              {"Feeder": "f", "block": "2", "unit": "", "built": "0", "attach_bus": ""}]
    built, missing = pl.block_rows(blocks, units, net, frame, lines, 0.95, 1.05, 100)
    assert built["v_pu_min"] == 0.94 and built["v_pu_min_load"] == "load_h1_gb1_2" and built["v_pu_max"] == 0.97
    assert built["voltage_outside"] == 1
    assert math.isclose(built["path_worst_percent"], 110.0) and built["path_worst_line"] == "main2"
    assert built["path_over"] == 1 and built["block"] == "1"
    assert missing["v_pu_min"] is None and missing["path_over"] is None


def test_substation_rating_and_rows():
    text = ("New Transformer.sub_1 phases=3 windings=2 wdg=1 conn=delta Kv=69.0 kva=40000.0 %R=0.3 bus=n9 "
            "wdg=2 conn=wye Kv=12.47 kva=40000.0 %R=0.3 bus=n4 XHL=6.7\n\n"
            "New Transformer.sub_2 phases=3 windings=2 wdg=1 conn=delta Kv=69.0 kva=20000.0 bus=n8 "
            "wdg=2 conn=wye Kv=12.47 kva=20000.0 bus=n5 XHL=6.7\n")
    assert pl.substation_rating(text) == 60000.0
    assert pl.substation_rating("") is None and pl.substation_rating("New RegControl.r transformer=x\n") is None
    power = {"baseline": [("c1", [3000.0, 6000.0], [0.0, 0.0]), ("c2", [1000.0, 0.0], [3000.0, 8000.0])],
             "stress": [("c1", [30000.0], [0.0]), ("c2", [0.0], [40000.0])]}
    rows = {r["scenario"]: r for r in pl.substation_rows(power, 40000.0, 100)}
    # step by step: (4000, 3000) -> 5000 kVA; (6000, 8000) -> 10000 kVA
    assert rows["baseline"]["peak_kva"] == 10000.0 and rows["baseline"]["peak_step"] == 2
    assert rows["baseline"]["percent"] == 25.0 and rows["baseline"]["over"] == 0 and rows["baseline"]["circuits"] == 2
    assert rows["stress"]["percent"] == 125.0 and rows["stress"]["over"] == 1
    empty = pl.substation_rows(power, None, 100)[0]
    assert empty["rating_kva"] is None and empty["percent"] is None and empty["over"] is None
    assert empty["peak_kva"] == 10000.0
