# -*- coding: utf-8 -*-
"""
test_ev_behaviour.py
--------------------
The EV control behaviour of the Phase 7 deploy on small hand-made data: the mixes file
reader, the stress day draw pools, the plug-in order of the valley rules, the forecast
error, the start spread of offpeak_start, water filling, and the defaults of the
extended functions.

Run directly (no pytest needed): python tests/test_ev_behaviour.py
Or under pytest: pytest tests/test_ev_behaviour.py
"""
import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from ev_cars import (EVWATTS_EXTRACT_FILE, charging_share, draw_months, load_inputs,  # noqa: E402
                     read_evwatts_pool, read_nhts_pool, rng)
from ev_control import (forecast_curve, forecast_cv, offpeak_row, offpeak_start, plugin_order,  # noqa: E402
                        start_offsets, valley_fill, valley_fill_curves, water_fill)
from pipeline_utils import load_mixes  # noqa: E402

INPUTS_PATH = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars", "ev_inputs.yaml")
MIXES = {"baseline": {"shares": {"baseline": 1.0, "dm": 0.0, "un": 0.0}, "ev_perc": 0.1},
         "stress": {"shares": {"baseline": 0.2, "dm": 0.2, "un": 0.6}, "ev_perc": 0.3}}


def _stops(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code == 1
    return False


def test_load_mixes():
    yaml_text = ("baseline:\n  shares: {baseline: 1.0, dm: 0.0, un: 0.0}\n  ev_perc: 0.10\n"
                 "stress:\n  shares: {baseline: 0.20, dm: 0.20, un: 0.60}\n  ev_perc: 0.30\n")
    with tempfile.TemporaryDirectory() as d:
        for name, text in (("m.yaml", yaml_text), ("m.yml", yaml_text), ("m.json", json.dumps(MIXES)),
                           ("m.txt", yaml_text)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        for name in ("m.yaml", "m.yml", "m.json"):
            got = load_mixes(os.path.join(d, name))
            assert got == MIXES and list(got) == ["baseline", "stress"], name
        assert _stops(load_mixes, os.path.join(d, "m.txt"))
    # the tracked mixes file
    mixes = load_mixes(os.path.join(REPO_ROOT, "0_experimental_design", "mixes_fixed.yaml"))
    assert list(mixes) == ["baseline", "mixed", "stress"]
    assert mixes["mixed"]["shares"] == {"baseline": 0.5, "dm": 0.3, "un": 0.2}


def test_stress_pool_filters():
    ev = pd.DataFrame({
        "session_id": [1, 2, 3, 4, 5], "evse_id": [10, 10, 11, 11, 12],
        "division": ["South Atlantic"] * 4 + ["Pacific"], "venue": ["x"] * 5,
        "start_date": ["2020-06-01", "2020-07-01", "2020-01-06", "2020-08-03", "2020-06-02"],
        "month": [6, 7, 1, 8, 6], "start_min": [0.0] * 5, "plug_min": [60.0] * 5,
        "charge_h": [1.0] * 5, "energy_kwh": [5.0] * 5})
    nh = pd.DataFrame({
        "HOUSEID": ["2", "1", "1", "3"], "VEHID": [1, 2, 1, 1],
        "TDAYDATE": ["201607", "201606", "201612", "201608"], "TRAVDAY": ["02"] * 4,
        "WTHHFIN": [1.0] * 4, "day_class": ["i", "ii", "i", "iii"]})
    with tempfile.TemporaryDirectory() as d:
        ev.to_csv(os.path.join(d, EVWATTS_EXTRACT_FILE), index=False)
        nh.to_csv(os.path.join(d, "nh.csv"), index=False)
        assert list(read_evwatts_pool(d, "South Atlantic")["session_id"]) == [1, 2, 3, 4]
        assert list(read_evwatts_pool(d, "South Atlantic", [6, 7, 8])["session_id"]) == [1, 2, 4]
        pool = read_nhts_pool(os.path.join(d, "nh.csv"))
        assert list(zip(pool["HOUSEID"], pool["VEHID"])) == [("1", 1), ("1", 2), ("2", 1)]
        pool = read_nhts_pool(os.path.join(d, "nh.csv"), [6, 7, 8])
        assert list(zip(pool["HOUSEID"], pool["VEHID"])) == [("1", 2), ("2", 1)]
        pool = read_nhts_pool(os.path.join(d, "nh.csv"), [6, 7, 8], ("i",))
        assert list(zip(pool["HOUSEID"], pool["VEHID"])) == [("2", 1)]
    # share on the season months: charger 10 used 2 of the summer weekdays from Mon 1 June
    # to Wed 1 July 2020 (22 in June, 1 in July = 23); charger 11 used 1 of 1 (Mon 3 August)
    pool = pd.DataFrame({"evse_id": [10, 10, 11], "start_date": ["2020-06-01", "2020-07-01", "2020-08-03"]})
    assert np.isclose(charging_share(pool, [6, 7, 8]), 3.0 / 24.0)
    # with every month the share is the default one
    assert np.isclose(charging_share(pool, list(range(1, 13))), charging_share(pool))
    # a winter season skips the months between first and last session that are not in it:
    # Fri 28 February to Tue 1 December 2020 holds 2 winter weekdays
    pool = pd.DataFrame({"evse_id": [1, 1], "start_date": ["2020-02-28", "2020-12-01"]})
    assert np.isclose(charging_share(pool, [12, 1, 2]), 1.0)
    assert charging_share(pool) < 0.02
    inputs = load_inputs(INPUTS_PATH, "stress")
    assert draw_months(inputs, "summer") == [6, 7, 8] and draw_months(inputs, "winter") == [12, 1, 2]
    assert draw_months(load_inputs(INPUTS_PATH), "summer") is None


def test_plugin_order():
    # 04:00 is 240: 03:59 (239) is the last minute of the placement day, 04:00 the first
    minutes = [600.0, None, 239.0, 240.0, 600.0, 0.0, None, 1439.0]
    assert plugin_order(minutes) == [3, 0, 4, 7, 5, 2, 1, 6]
    assert plugin_order([None, None]) == [0, 1]
    assert plugin_order([]) == []


def test_forecast_error():
    models = load_inputs(INPUTS_PATH)["forecast_models"]
    for w, hour, day in ((500.0, 3.4, 7.0), (20.0, 14.0, 14.8)):
        assert abs(forecast_cv(w, "hour_ahead", models["hour_ahead"]) - hour) < 0.1
        assert abs(forecast_cv(w, "day_ahead", models["day_ahead"]) - day) < 0.1
    curve = np.full(96, 100.0)
    curve[:4] = [90.0, 95.0, 105.0, 110.0]
    z = rng("forecast_feeder", 555).standard_normal(24)
    f, err, w, cv = forecast_curve(curve, "hour_ahead", models["hour_ahead"], z)
    assert np.isclose(w, curve.mean()) and np.isclose(cv, forecast_cv(w, "hour_ahead", models["hour_ahead"]))
    assert np.allclose(err, np.repeat(z, 4) * cv / 100.0 * w) and np.allclose(f, curve + err)
    assert all(len(set(err[4 * h:4 * h + 4])) == 1 for h in range(24))
    z2 = rng("forecast_feeder", 555).standard_normal(24)
    assert np.array_equal(forecast_curve(curve, "hour_ahead", models["hour_ahead"], z2)[0], f)
    assert not np.array_equal(rng("forecast_t1", 555).standard_normal(24), z)
    for flat in (np.zeros(96), np.full(96, -5.0)):
        f0, e0, _, cv0 = forecast_curve(flat, "day_ahead", models["day_ahead"], z)
        assert cv0 is None and np.array_equal(f0, flat) and not e0.any()


def test_start_spread():
    cheap = list(range(88, 96)) + list(range(0, 24))            # 22:00 to 06:00
    row = np.zeros(96)
    row[70:74] = 7.0                                             # 28 kW-intervals
    window = list(range(70, 96)) + [0, 1]                        # 17:30 to 00:30, first cheap 88
    z = np.array([-1.5, 3.0, 0.4, 0.0])
    rows = np.array([row, row, row, np.zeros(96)])
    d = start_offsets(rows, cheap, [window] * 4, z, 60.0)
    assert d == [-6, 12, 2, None]                                # round(z x 60 / 15)
    got, start = offpeak_row(row, cheap, 7.0, window, d[0])      # 88 - 6 = 82
    assert start == 82 and np.array_equal(np.flatnonzero(got), [82, 83, 84, 85])
    got, start = offpeak_row(row, cheap, 7.0, window, d[1])      # 88 + 12 is past the window: clamped to 1
    assert start == 1 and np.array_equal(np.flatnonzero(got), [1]) and got.sum() == 7.0
    got, start = offpeak_row(row, cheap, 7.0, window, -30)       # clamped to the window's first interval
    assert start == 70
    # no cheap interval in the window: no offset, the plug-in start
    window2 = list(range(40, 60))
    assert start_offsets(np.array([row]), cheap, [window2], [2.0], 60.0) == [None]
    got, start = offpeak_row(row, cheap, 7.0, window2, None)
    assert start == 40
    # without a window the start wraps modulo 96
    got, start = offpeak_row(row, cheap, 7.0, None, 12)          # first cheap at or after 70 is 88
    assert start == 4
    a, s = offpeak_start(rows, cheap, 7.0, [window] * 4, d)
    assert s == [82, 1, 90, None]
    # nothing outside the window
    for j in range(4):
        assert set(np.flatnonzero(a[j])) <= set(window)


def test_water_fill():
    gen = np.random.default_rng(3)
    curve = gen.uniform(50.0, 150.0, size=96)
    rows = np.zeros((5, 96))
    rows[0, 70:74] = 7.0                         # 28 kW-intervals
    rows[1, 10:12] = 6.0
    rows[2, 80:90] = 3.3
    rows[4, 0:96] = 1.0                          # 96 kW-intervals, more than 2 kW x 20 intervals
    powers = [7.0, 6.0, 3.3, 7.0, 2.0]
    windows = [list(range(68, 96)), list(range(8, 20)), None, None, list(range(30, 50))]
    order = [2, 0, 4, 1, 3]
    out, after = water_fill(rows, curve, powers, windows, order)
    assert np.allclose(after, curve + out.sum(axis=0))
    f = curve.copy()
    for j in order:
        if not rows[j].any():
            continue
        cand = set(range(96)) if windows[j] is None else set(windows[j])
        assert set(np.flatnonzero(out[j])) <= cand
        assert (out[j] <= powers[j] + 1e-12).all() and (out[j] >= 0).all()
        energy = rows[j].sum()
        if powers[j] * len(cand) <= energy:
            assert np.allclose(out[j, sorted(cand)], powers[j])
            assert np.isclose(out[j].sum() + (energy - powers[j] * len(cand)), energy)
        else:
            assert np.isclose(out[j].sum(), energy)
            mid = (out[j] > 1e-9) & (out[j] < powers[j] - 1e-9)
            level = (f + out[j])[mid]
            assert mid.any() and np.ptp(level) < 1e-6
            # intervals the car leaves empty sit at or above the level
            empty = [i for i in cand if out[j, i] <= 1e-9]
            assert all(f[i] >= level.max() - 1e-6 for i in empty)
        f += out[j]
    assert not out[3].any()
    # one car, a flat curve and a large power: the energy spreads evenly over the window
    row = np.zeros((1, 96))
    row[0, 0:4] = 6.0
    out, _ = water_fill(row, np.full(96, 10.0), [50.0], [list(range(20, 32))])
    assert np.allclose(out[0, 20:32], 24.0 / 12) and np.isclose(out.sum(), 24.0)


def test_defaults_keep_host_order_and_no_shift():
    gen = np.random.default_rng(5)
    rows = np.zeros((6, 96))
    for j in range(6):
        a = int(gen.integers(0, 90))
        rows[j, a:a + int(gen.integers(1, 6))] = 7.0
    base = gen.uniform(500.0, 1500.0, size=96)
    windows = [list(range(40, 96))] * 6
    host = list(range(6))
    assert np.array_equal(valley_fill(rows, base, windows)[0], valley_fill(rows, base, windows, host)[0])
    assert np.array_equal(valley_fill(rows, base, windows, None)[0], valley_fill(rows, base, windows)[0])
    curves = {"feeder": base, "t1": base / 10}
    keys = ["t1", "feeder"] * 3
    assert np.array_equal(valley_fill_curves(rows, curves, keys, "feeder", windows)[0],
                          valley_fill_curves(rows, curves, keys, "feeder", windows, host)[0])
    assert np.array_equal(water_fill(rows, base, [7.0] * 6)[0], water_fill(rows, base, [7.0] * 6, None, host)[0])
    cheap = list(range(0, 24))
    for w in (None, [windows[0]] * 6):
        a, sa = offpeak_start(rows, cheap, 7.0, w)
        b, sb = offpeak_start(rows, cheap, 7.0, w, [None] * 6)
        c, sc = offpeak_start(rows, cheap, 7.0, w, [0] * 6)
        assert np.array_equal(a, b) and np.array_equal(a, c) and sa == sb == sc
    typical = load_inputs(INPUTS_PATH)
    assert typical == load_inputs(INPUTS_PATH, "typical")
    assert (typical["charging_share"], typical["months"], typical["forecast_error"],
            typical["start_spread_min"]) == ("measured", "all", "hour_ahead", 60.0)
    stress = load_inputs(INPUTS_PATH, "stress")
    assert (stress["charging_share"], stress["months"], stress["forecast_error"],
            stress["start_spread_min"]) == ("all", "season", "day_ahead", 15.0)
    assert stress["check_curve_file"] == "Weekday - Level 2 - Diversified (75th percentile) of 100 EVs.csv"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
