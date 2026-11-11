# -*- coding: utf-8 -*-
"""
test_load_voltage.py
--------------------
load_voltage.py (Phase 7 deploy, voltage at every load) on synthetic arrays at 96 and
672 steps (one and seven days): a split-phase load (legs _1 and _2 on nodes 1 and 2),
a three-phase wye load and a one-phase load on a bus with no base voltage. EV legs
(EVu_, EVc_) are marked in ev_leg and left out of the step table and the circuit
summary. Also reads load monitors of a small circuit solved through dss_engine.

Run directly (no pytest needed): python tests/test_load_voltage.py
Or under pytest: pytest tests/test_load_voltage.py
"""
import math
import os
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from load_voltage import (circuit_summary, load_table, load_voltage_frame,  # noqa: E402
                          monitor_lines, monitor_name, read_load_monitors, step_table,
                          voltage_columns)

LOW, HIGH = 0.95, 1.05


def _records(n):
    """Split-phase legs at 0.12 kV base, a three-phase wye load at 0.277 kV base, and a
    one-phase load on a bus with no base (0.12 kV from the load). At step 1 leg _1 is
    below the band; at step 2 the three-phase load's phase 2 is above it."""
    leg1 = np.full((n, 2), 120.0); leg1[:, 1] = 0.0
    leg1[0, 0] = 110.0
    leg2 = np.full((n, 2), 121.0); leg2[:, 1] = 0.0
    three = np.full((n, 4), 277.0); three[:, 3] = 0.5
    three[1, 1] = 300.0
    nobase = np.full((n, 2), 118.8); nobase[:, 1] = 0.0
    return [
        {"load": "load_a_1", "bus": "busa", "node_order": [1, 0], "v": leg1,
         "kv_base": 0.12, "kv": 0.12, "phases": 1, "delta": False},
        {"load": "load_a_2", "bus": "busa", "node_order": [2, 0], "v": leg2,
         "kv_base": 0.12, "kv": 0.12, "phases": 1, "delta": False},
        {"load": "load_b", "bus": "busb", "node_order": [1, 2, 3, 0], "v": three,
         "kv_base": 0.277, "kv": 0.48, "phases": 3, "delta": False},
        {"load": "load_c_1", "bus": "busc", "node_order": [1, 0], "v": nobase,
         "kv_base": 0.0, "kv": 0.12, "phases": 1, "delta": False},
    ]


def _check(n):
    frame, no_base = load_voltage_frame(_records(n))
    assert list(frame.columns) == ["load", "bus", "step", "conductor", "v_volts", "v_pu", "ev_leg"]
    assert not frame["ev_leg"].any()
    # node 0 left out: 1 + 1 + 3 + 1 conductors per step
    assert len(frame) == 6 * n
    assert sorted(frame["step"].unique()) == list(range(1, n + 1))
    assert no_base == ["load_c_1"]
    b = frame[frame["load"] == "load_b"]
    assert sorted(b["conductor"].unique()) == [1, 2, 3]
    assert math.isclose(b[(b["step"] == 2) & (b["conductor"] == 2)]["v_pu"].iloc[0], 300.0 / 277.0)
    c = frame[frame["load"] == "load_c_1"]
    assert np.allclose(c["v_pu"], 118.8 / 120.0)
    a1 = frame[frame["load"] == "load_a_1"]
    assert math.isclose(a1[a1["step"] == 1]["v_pu"].iloc[0], 110.0 / 120.0)

    steps = step_table(frame, LOW, HIGH)
    assert len(steps) == n and list(steps["step"]) == list(range(1, n + 1))
    s1, s2 = steps.iloc[0], steps.iloc[1]
    assert s1["v_pu_min_load"] == "load_a_1" and (s1["n_below"], s1["n_above"]) == (1, 0)
    assert s2["v_pu_max_load"] == "load_b" and (s2["n_below"], s2["n_above"]) == (0, 1)
    assert (steps.iloc[2:]["n_below"] == 0).all() and (steps.iloc[2:]["n_above"] == 0).all()

    loads = load_table(frame, LOW, HIGH).set_index("load")
    assert list(loads.index) == ["load_a_1", "load_a_2", "load_b", "load_c_1"]
    assert loads.loc["load_a_1", "v_pu_min_step"] == 1 and loads.loc["load_a_1", "n_steps_outside"] == 1
    assert loads.loc["load_b", "v_pu_max_step"] == 2 and loads.loc["load_b", "n_steps_outside"] == 1
    assert loads.loc["load_a_2", "n_steps_outside"] == 0

    summ = circuit_summary(loads.reset_index(), LOW, HIGH)
    assert (summ["n_loads_below"], summ["n_loads_above"], summ["n_load_steps_outside"]) == (1, 1, 2)
    assert math.isclose(summ["v_pu_min"], 110.0 / 120.0) and math.isclose(summ["v_pu_max"], 300.0 / 277.0)


def test_one_day_96_steps():
    _check(96)


def test_seven_days_672_steps():
    _check(672)


def test_three_phase_bus_without_base_uses_line_to_line_kv():
    rec = _records(96)[2]
    rec["kv_base"] = 0.0
    frame, no_base = load_voltage_frame([rec])
    assert no_base == ["load_b"]
    assert np.allclose(frame[frame["step"] == 1]["v_pu"], 277.0 / (480.0 / math.sqrt(3.0)))


def test_ev_legs_marked_and_left_out_of_the_counts():
    recs = _records(96)
    # Two EV legs on the bus of load_a_1, below the band at every step, and an EV leg
    # whose name sorts first and ties with load_a_1 at step 1.
    ev_low = dict(recs[0], load="EVu_load_a_1", v=np.full((96, 2), 100.0))
    ev_low["v"][:, 1] = 0.0
    ev_c = dict(recs[0], load="evc_load_a_2", v=np.full((96, 2), 100.0))
    ev_c["v"][:, 1] = 0.0
    ev_tie = dict(recs[0], load="EVc_a_tie", v=np.full((96, 2), 120.0))
    ev_tie["v"][:, 1] = 0.0
    ev_tie["v"][0, 0] = 110.0
    frame, _ = load_voltage_frame(recs + [ev_low, ev_c, ev_tie])
    assert list(frame.columns)[-1] == "ev_leg"
    marked = frame.groupby("load")["ev_leg"].first().to_dict()
    assert marked == {"EVc_a_tie": True, "EVu_load_a_1": True, "evc_load_a_2": True, "load_a_1": False,
                      "load_a_2": False, "load_b": False, "load_c_1": False}
    customer, _ = load_voltage_frame(recs)
    steps = step_table(frame, LOW, HIGH)
    assert steps.equals(step_table(customer, LOW, HIGH))
    assert steps.iloc[0]["v_pu_min_load"] == "load_a_1"
    loads = load_table(frame, LOW, HIGH)
    assert list(loads.columns)[-1] == "ev_leg"
    assert int(loads["ev_leg"].sum()) == 3 and int((~loads["ev_leg"]).sum()) == 4
    assert circuit_summary(loads, LOW, HIGH) == circuit_summary(load_table(customer, LOW, HIGH), LOW, HIGH)
    # the same after a round trip through load_voltage_loads.csv
    import io
    import pandas as pd
    buf = io.StringIO()
    loads.to_csv(buf, index=False)
    buf.seek(0)
    assert circuit_summary(pd.read_csv(buf), LOW, HIGH)["n_loads_below"] == 1


def test_monitor_lines_and_header():
    assert monitor_name("Load_X_1") == "vl_load_x_1"
    assert monitor_lines(["Load_X_1"]) == ["New Monitor.vl_load_x_1 element=Load.Load_X_1 terminal=1 mode=0\n"]
    header = [" V1", " VAngle1", " V2", " VAngle2", " I1", " IAngle1", " I2", " IAngle2"]
    assert voltage_columns(header) == {1: 1, 2: 3}


def test_read_monitors_through_engine():
    from dss_engine import create_dss_engine
    dss = create_dss_engine()
    dss.AllowForms = False
    dss.Start(0)
    text, circuit = dss.Text, dss.ActiveCircuit
    text.Command = "clear"
    text.Command = "new circuit.lvtest basekv=12.47 pu=1.0 phases=3"
    text.Command = "new transformer.t1 phases=3 windings=2 buses=(sourcebus, lv) conns=(delta, wye) kvs=(12.47, 0.48) kvas=(500, 500) xhl=2"
    text.Command = "new load.l3 bus1=lv.1.2.3 phases=3 kv=0.48 kw=50 kvar=10 model=1"
    text.Command = "new load.l1_1 bus1=lv.1 phases=1 kv=0.277 kw=5 kvar=1 model=1"
    text.Command = "set voltagebases=[12.47, 0.48]"
    text.Command = "calcvoltagebases"
    for line in monitor_lines(["l3", "l1_1"]):
        text.Command = line.strip()
    text.Command = "set mode=daily stepsize=15m number=96"
    circuit.Solution.Solve()
    assert circuit.Solution.Converged is True
    assert sorted(str(n).lower() for n in circuit.Loads.AllNames) == ["l1_1", "l3"]
    recs = read_load_monitors(circuit, ["l3", "l1_1"])
    assert [r["v"].shape for r in recs] == [(96, 4), (96, 2)]
    assert [list(r["node_order"]) for r in recs] == [[1, 2, 3, 0], [1, 0]]
    assert all(math.isclose(r["kv_base"], 0.48 / math.sqrt(3.0), rel_tol=1e-6) for r in recs)
    frame, no_base = load_voltage_frame(recs)
    assert no_base == [] and len(frame) == 96 * 4
    assert frame["v_pu"].between(0.9, 1.1).all()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
