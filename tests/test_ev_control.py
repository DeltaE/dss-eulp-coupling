# -*- coding: utf-8 -*-
"""
test_ev_control.py
------------------
ev_control.py (Phase 7 deploy, the ev_control rules) on synthetic data: valley filling
against the 2024 reference block (copied below), energy and interval counts kept,
uncontrolled cars on the start curve, the service transformer map of a small
hand-written circuit, the off-peak start timer on a small URDB-like record, real power
from mode=1 Monitor channels, and the ev_control and ev_valley_base settings.

Run directly (no pytest needed): python tests/test_ev_control.py
Or under pytest: pytest tests/test_ev_control.py
"""
import os
import sys

import numpy as np
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from ev_control import (cheap_intervals, monitor_p_kw, offpeak_row, offpeak_start, place_car,  # noqa: E402
                        service_transformers, valley_fill, valley_fill_curves)
from pipeline_utils import ev_control, ev_valley_base  # noqa: E402

KW = 7.36


def reference_2024(array_ev_profiles_uncontrolled, P_total):
    """Luis's 2024 block (power_flow_sim_daily_EV.py), copied word for word."""
    new_profiles = np.zeros_like(array_ev_profiles_uncontrolled)  # final result
    combined_load = P_total.copy()                    # will be updated after each EV

    num_evs, num_intervals = array_ev_profiles_uncontrolled.shape

    for ev_i in range(num_evs):
        ev_load = array_ev_profiles_uncontrolled[ev_i, :]
        total_energy = ev_load.sum()
        nonzero_count = np.count_nonzero(ev_load)
        if nonzero_count == 0:
            continue
        sorted_indices = np.argsort(combined_load)  # ascending order
        chosen_intervals = sorted_indices[:nonzero_count]
        energy_per_interval = total_energy / nonzero_count
        new_profile = np.zeros(num_intervals)
        new_profile[chosen_intervals] = energy_per_interval
        new_profiles[ev_i, :] = new_profile
        combined_load += new_profile
    return new_profiles


def _sessions(rng, n_cars=10, n=96):
    """Session rows: one or two blocks of charging at 6.6 to 7.36 kW per car, with
    distinct values so no two intervals of a car tie."""
    rows = np.zeros((n_cars, n))
    for j in range(n_cars):
        for _ in range(rng.integers(1, 3)):
            start, length = rng.integers(0, n), rng.integers(2, 16)
            idx = (start + np.arange(length)) % n
            rows[j, idx] = rng.uniform(0.9 * KW, KW, size=length)
    return rows


def test_valley_fill_equals_2024_block():
    rng = np.random.default_rng(2024)
    rows = _sessions(rng)
    base = rng.uniform(500.0, 1500.0, size=96)
    ref = reference_2024(rows, base)
    got, after = valley_fill(rows, base)
    assert np.array_equal(got, ref)
    assert np.allclose(after, base + ref.sum(axis=0))


def test_energy_and_intervals_kept():
    rng = np.random.default_rng(7)
    rows = _sessions(rng)
    rows[3, :] = 0.0
    got, _ = valley_fill(rows, rng.uniform(500.0, 1500.0, size=96))
    for j in range(rows.shape[0]):
        assert np.isclose(got[j].sum(), rows[j].sum())
        assert np.count_nonzero(got[j]) == np.count_nonzero(rows[j])
        assert got[j].max() <= rows[j].max() + 1e-12
    assert not got[3].any()


def test_ties_go_to_the_earlier_interval():
    row = np.zeros(96); row[50:53] = 7.0
    got = place_car(row, np.ones(96))
    assert list(np.flatnonzero(got)) == [0, 1, 2]


def test_uncontrolled_cars_on_the_curve():
    rng = np.random.default_rng(11)
    unc, ctl = _sessions(rng, 6), _sessions(rng, 6)
    base = rng.uniform(500.0, 1500.0, size=96)
    combined = base.copy()
    for row in unc:
        combined += row
    got, _ = valley_fill(ctl, base + unc.sum(axis=0))
    assert np.allclose(got, valley_fill(ctl, combined)[0])
    assert np.array_equal(got, reference_2024(ctl, base + unc.sum(axis=0)))
    # every car on the feeder curve: valley_fill_curves gives valley_fill
    same, _ = valley_fill_curves(ctl, {"feeder": base + unc.sum(axis=0)}, ["feeder"] * 6, "feeder")
    assert np.array_equal(same, got)


def test_cars_on_their_own_curves_also_load_the_feeder():
    ctl = np.zeros((2, 4)); ctl[0, 0] = 1.0; ctl[1, 3] = 1.0
    curves = {"feeder": np.array([5.0, 1.0, 9.0, 9.0]), "t1": np.array([3.0, 2.0, 1.0, 4.0])}
    got, after = valley_fill_curves(ctl, curves, ["t1", "feeder"], "feeder")
    assert list(np.flatnonzero(got[0])) == [2]   # lowest of t1
    assert list(np.flatnonzero(got[1])) == [1]   # lowest of the feeder
    assert np.allclose(after["t1"], [3.0, 2.0, 2.0, 4.0])
    assert np.allclose(after["feeder"], [5.0, 2.0, 10.0, 9.0])


CIRCUIT = """
New Line.p1 bus1=src.1.2.3 bus2=p2.1.2.3 phases=3
New Line.p2 bus1=p2.1.2.3 bus2=p3.1.2.3 phases=3
! regulator: equal winding kV, no secondary
New Transformer.reg1 phases=1 windings=2 buses=[p3.1 p4.1] kvs=[7.2 7.2]
New Line.p3 bus1=p4.1 bus2=p5.1 phases=1
New Transformer.t1 phases=1 windings=3 wdg=1 bus=p2.1 Kv=7.2 wdg=2 bus=s1.1.0 Kv=0.12 wdg=3 bus=s1.0.2 Kv=0.12
New Line.s1a bus1=s1.1.2 bus2=h1.1.2 phases=2
New Line.s1b bus1=h1.1.2 bus2=h2.1.2 phases=2
New Transformer.t2 phases=3 windings=2
~ wdg=1 conn=wye kv=12.47 bus=p5 wdg=2 conn=wye kv=0.48 bus=S2
New Line.s2a bus1=s2 bus2=h3 phases=3
New Transformer.t3 phases=1 windings=2 buses=(p3.1, s4.1) kvs=(7.2, 0.24)
New Transformer.t4 phases=1 windings=2 buses=(p3.2, s5.2) kvs=(7.2, 0.24)
New Line.tie bus1=s4.1 bus2=s5.1 phases=1
"""


def test_service_transformer_map():
    load_buses = {"load_h1_1": "h1.1", "load_h2_2": "H2.2", "load_h3": "h3.1.2.3",
                  "load_s2": "s2", "load_p": "p3.1.2.3", "load_s4": "s4.1"}
    mapping, status = service_transformers([CIRCUIT], load_buses)
    assert mapping == {"load_h1_1": "t1", "load_h2_2": "t1", "load_h3": "t2", "load_s2": "t2",
                       "load_p": None, "load_s4": None}
    assert status == {"load_h1_1": "one", "load_h2_2": "one", "load_h3": "one", "load_s2": "one",
                      "load_p": "none", "load_s4": "several"}


def test_switched_out_lines_left_out_of_the_map():
    # open1 would join the secondary of t1 (h1) to the secondary of t2 (h3)
    load_buses = {"load_h1_1": "h1.1", "load_h2_2": "H2.2", "load_h3": "h3.1.2.3",
                  "load_s2": "s2", "load_p": "p3.1.2.3", "load_s4": "s4.1"}
    extra = ("New Line.open1 bus1=h1.1 bus2=h3.1 phases=1 enabled=n\n"
             "New Line.open2 bus1=h2.1 bus2=s2.1 phases=1 Enabled=False\n"
             "New Line.open3 bus1=s1.1 bus2=s2.1 phases=1\n~ enabled=No\n")
    skipped = []
    mapping, status = service_transformers([CIRCUIT + extra], load_buses, skipped)
    assert skipped == ["open1", "open2", "open3"]
    assert mapping == {"load_h1_1": "t1", "load_h2_2": "t1", "load_h3": "t2", "load_s2": "t2",
                       "load_p": None, "load_s4": None}
    # the same lines in service join t1 and t2: their loads have several transformers
    closed, status = service_transformers([CIRCUIT + "New Line.open1 bus1=h1.1 bus2=h3.1 phases=1 enabled=y\n"],
                                          load_buses)
    assert closed == {"load_h1_1": None, "load_h2_2": None, "load_h3": None, "load_s2": None,
                      "load_p": None, "load_s4": None}
    assert status["load_h1_1"] == "several"


def test_place_car_with_a_window():
    row = np.zeros(96); row[50:54] = 6.0                     # 4 intervals, 24 kW-intervals
    curve = np.arange(96, 0, -1, dtype=float)                 # lowest at the end of the day
    got = place_car(row, curve, window=[94, 95, 0, 1, 2, 3])
    assert list(np.flatnonzero(got)) == [2, 3, 94, 95]
    # fewer candidates than intervals: both get row sum / 4, the rest is left over
    got = place_car(row, curve, window=[10, 11])
    assert list(np.flatnonzero(got)) == [10, 11]
    assert np.allclose(got[[10, 11]], 6.0) and np.isclose(row.sum() - got.sum(), 12.0)
    # window=None gives the existing results
    rng = np.random.default_rng(3)
    rows = _sessions(rng)
    base = rng.uniform(500.0, 1500.0, size=96)
    assert np.array_equal(valley_fill(rows, base, None)[0], valley_fill(rows, base)[0])
    assert np.array_equal(valley_fill(rows, base, [None] * rows.shape[0])[0], valley_fill(rows, base)[0])
    for j in range(rows.shape[0]):
        assert np.array_equal(place_car(rows[j], base, None), place_car(rows[j], base))
    curves = {"feeder": base, "t1": base[::-1].copy()}
    keys = ["t1", "feeder"] * (rows.shape[0] // 2)
    assert np.array_equal(valley_fill_curves(rows, curves, keys, "feeder", None)[0],
                          valley_fill_curves(rows, curves, keys, "feeder")[0])
    # windows keep every car inside its own window
    windows = [[(10 * j + k) % 96 for k in range(12)] for j in range(rows.shape[0])]
    got, _ = valley_fill(rows, base, windows)
    for j in range(rows.shape[0]):
        outside = np.setdiff1d(np.arange(96), windows[j])
        assert not got[j, outside].any()


def test_offpeak_row_with_a_window():
    _, cheap = cheap_intervals(_rate(), 7)                    # cheap: 0 to 23 and 88 to 95
    row = np.zeros(96); row[70:73] = 7.0                      # 21 kW-intervals
    # window 80 to 91: the first cheap interval met is 88, charging stops at the window end
    window = list(range(80, 92))
    got, start = offpeak_row(row, cheap, 7.0, window)
    assert start == 88 and list(np.flatnonzero(got)) == [88, 89, 90]
    assert np.allclose(got[88:91], 7.0)
    got, start = offpeak_row(row, cheap, 4.0, window)         # 5 x 4 + 1 needs 6 intervals, 4 left
    assert start == 88 and list(np.flatnonzero(got)) == [88, 89, 90, 91]
    assert np.isclose(row.sum() - got.sum(), 5.0)
    # no cheap interval in the window: starts at plug-in
    got, start = offpeak_row(row, cheap, 7.0, list(range(30, 40)))
    assert start == 30 and list(np.flatnonzero(got)) == [30, 31, 32]
    # window=None gives the existing results; per-car power
    rows = np.zeros((2, 96)); rows[0, 70:73] = 7.0; rows[1, 10:12] = 3.0
    a, sa = offpeak_start(rows, cheap, [7.0, 3.0])
    b0, s0 = offpeak_row(rows[0], cheap, 7.0)
    b1, s1 = offpeak_row(rows[1], cheap, 3.0)
    assert np.array_equal(a, np.vstack([b0, b1])) and sa == [s0, s1]
    assert np.array_equal(offpeak_start(rows, cheap, 7.0, None)[0], offpeak_start(rows, cheap, 7.0)[0])


def _rate():
    """Two periods: period 1 (rate 0.05 + adj 0.01) from 22:00 to 06:00, period 0
    (rate 0.20) otherwise, every month; the weekend schedule is all period 0."""
    row = [1] * 6 + [0] * 16 + [1] * 2
    return {"energyweekdayschedule": [row] * 12, "energyweekendschedule": [[0] * 24] * 12,
            "energyratestructure": [[{"rate": 0.20}], [{"rate": 0.05, "adj": 0.01}]]}


def test_cheap_intervals():
    period, cheap = cheap_intervals(_rate(), 7)
    assert period == 1
    assert cheap == list(range(0, 24)) + list(range(88, 96))
    tie = _rate()
    tie["energyratestructure"] = [[{"rate": 0.06}], [{"rate": 0.05, "adj": 0.01}]]
    assert cheap_intervals(tie, 7)[0] == 0   # equal prices: the lower period number


def test_offpeak_start():
    _, cheap = cheap_intervals(_rate(), 7)
    rows = np.zeros((3, 96))
    rows[0, 70:74] = [7.0, 7.0, 7.0, 3.0 * KW + 2.0 - 21.0]   # starts at 88, wraps past midnight
    rows[1, 2:33] = 30.0 * KW / 31.0; rows[1, 40] = 1.5       # starts at 2, runs past 06:00
    _, starts = offpeak_start(rows[2:3], cheap, KW)            # all-zero row
    assert starts == [None]
    got, starts = offpeak_start(rows, cheap, KW)
    assert starts[:2] == [88, 2]
    # car 0: 3.0 x 7.36 + 2.0 kW-intervals from 88 -> 88, 89, 90 full, 91 partial
    assert np.allclose(got[0, 88:91], KW) and np.isclose(got[0, 91], 2.0)
    assert np.count_nonzero(got[0]) == 4
    # car 1: 30 x 7.36 + 1.5 from 2 -> 2 to 31 full, 32 partial, past the cheap end (24)
    assert np.allclose(got[1, 2:32], KW) and np.isclose(got[1, 32], 1.5)
    assert np.count_nonzero(got[1]) == 31
    for j in range(3):
        assert np.isclose(got[j].sum(), rows[j].sum())
        assert got[j].max() <= KW + 1e-12
    assert not got[2].any()


def test_offpeak_charging_wraps_past_the_last_interval():
    _, cheap = cheap_intervals(_rate(), 1)
    row = np.zeros((1, 96)); row[0, 90] = 10.0 * KW
    got, starts = offpeak_start(row, cheap, KW)
    assert starts == [90]
    assert list(np.flatnonzero(got[0])) == [0, 1, 2, 3, 90, 91, 92, 93, 94, 95]


def test_monitor_p_polar_and_rectangular():
    polar = {1: [10.0, 20.0], 2: [60.0, 0.0], 3: [5.0, 5.0], 4: [90.0, 180.0]}
    p = monitor_p_kw([" S1 (kVA)", " Ang1", " S2 (kVA)", " Ang2"], lambda i: polar[i])
    assert np.allclose(p, [10.0 * 0.5 + 0.0, 20.0 * 1.0 - 5.0])
    rect = {1: [1.0, 2.0], 2: [9.0, 9.0], 3: [3.0, 4.0], 4: [9.0, 9.0]}
    p = monitor_p_kw(["P1 (kW)", "Q1 (kvar)", "P2 (kW)", "Q2 (kvar)"], lambda i: rect[i])
    assert np.allclose(p, [4.0, 6.0])


def _stops(fn, cfg):
    try:
        fn(cfg)
    except SystemExit as e:
        return e.code == 1
    return False


def test_settings():
    for value in ("uncontrolled", "valley_fill_feeder", "valley_fill_transformer", "offpeak_start",
                  "water_fill_feeder"):
        assert ev_control({"ev_control": value}) == value
    for value in ("buildings_only", "after_pv"):
        assert ev_valley_base({"ev_valley_base": value}) == value
    assert _stops(ev_control, {"ev_control": "equal_energy_realloc"})
    assert _stops(ev_control, {})
    assert _stops(ev_valley_base, {"ev_valley_base": "pv_only"})
    assert _stops(ev_valley_base, {})
    with open(os.path.join(REPO_ROOT, "pipeline_config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert (ev_control(cfg), ev_valley_base(cfg)) == ("valley_fill_feeder", "buildings_only")


def test_uncontrolled_keeps_session_rows():
    """The deploy keeps the session rows for controlled cars unless ev_control names a
    rule: arr_c starts as the session rows and only the guarded block replaces it."""
    path = os.path.join(REPO_ROOT, "7_circuit_instantiation", "power_flow_sim_daily_EV_STO_DG_deploy.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "arr_c = arr_c_sessions " in src
    assert 'if ACTIVATE_EV and N_c > 0 and EV_CONTROL != "uncontrolled":' in src
    assert "equal_energy_realloc" not in src


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
