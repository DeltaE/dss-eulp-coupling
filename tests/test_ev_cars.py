# -*- coding: utf-8 -*-
"""
test_ev_cars.py
---------------
ev_cars.py (Phase 7 deploy, the EV cars) and the two extract scripts on small
hand-made data: the seeds, the level and charging draws, charge_shape and the plug-in
window, the share of cars charging, the NHTS day classes and windows, the EV WATTS
extract filters, the repaired 2024 generator, and the ev_cars and ev_home_window
settings.

Run directly (no pytest needed): python tests/test_ev_cars.py
Or under pytest: pytest tests/test_ev_cars.py
"""
import hashlib
import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from ev_cars import (charge_shape, charging_share, evwatts_cars, pick, plug_window, rng,  # noqa: E402
                     seed, session_rows_cars, window_intervals)
from build_nhts_extract import vehicle_days  # noqa: E402
from build_evwatts_extract import apply_filters  # noqa: E402
from pipeline_utils import ev_cars, ev_home_window  # noqa: E402

INPUTS = {"level2_kw": 7.2, "level1_kw": 1.0, "kwh_per_mile": 33.7 / 99.9}


def test_seed_is_the_sha256_formula():
    expected = 555 + int.from_bytes(hashlib.sha256(b"level_controlled").digest()[:8], "big") % 10_000_000
    assert seed("level_controlled", 555) == expected
    assert seed("level_controlled", 555) != seed("level_uncontrolled", 555)


def test_level_and_charging_draws():
    for n, share, count in ((10, 0.8, 8), (10, 0.45, 5), (7, 0.9, 6), (0, 0.8, 0), (5, 0.0, 0)):
        got = pick(n, share, rng("level_uncontrolled", 1))
        assert got.sum() == count
        assert np.array_equal(got, pick(n, share, rng("level_uncontrolled", 1)))
    assert not np.array_equal(pick(40, 0.5, rng("charging_controlled", 1)),
                              pick(40, 0.5, rng("charging_controlled", 2)))


def test_charge_shape_and_window():
    # plug-in at 10:07 for 60 minutes: intervals 40 (10:00) to 44 (11:00 to 11:15)
    assert plug_window(607, 60) == (40, 5)
    assert plug_window(600, 60) == (40, 4)           # an end on a boundary opens no interval
    assert plug_window(1430, 3000) == (95, 96)       # at most the whole day
    assert plug_window(600, 0) == (40, 1)
    # remainder interval: 5 kWh at 7.2 kW = 20 kW-intervals -> 7.2, 7.2, 5.6
    row = charge_shape(40, 7.2, 5.0, 5)
    assert list(np.flatnonzero(row)) == [40, 41, 42]
    assert np.allclose(row[40:43], [7.2, 7.2, 5.6])
    # wrap past interval 95
    row = charge_shape(94, 7.2, 5.0, 10)
    assert list(np.flatnonzero(row)) == [0, 94, 95]
    assert np.isclose(row[0], 5.6)
    assert window_intervals(94, 4) == [94, 95, 0, 1]
    # a window of 4 intervals cuts a Level 1 car that needs 3 kWh: 1 kWh delivered, 2 left over
    pool = pd.DataFrame({"session_id": [9], "start_min": [150.0], "plug_min": [60.0], "charge_h": [0.5],
                         "energy_kwh": [3.0]})
    car = evwatts_cars("uncontrolled", ["h1"], pool, 1.0, 0.0, INPUTS, 555)[0]
    assert car["level"] == "L1" and car["power_kw"] == 1.0
    assert list(np.flatnonzero(car["row"])) == [10, 11, 12, 13]
    assert np.isclose(car["delivered_kwh"], 1.0) and np.isclose(car["leftover_kwh"], 2.0)
    assert (car["plug_in_interval"], car["window_intervals"], car["first_interval"]) == (11, 4, 11)
    # the same session at Level 2 charges at its mean power 3.0 / 0.5 = 6 kW
    car = evwatts_cars("uncontrolled", ["h1"], pool, 1.0, 1.0, INPUTS, 555)[0]
    assert np.isclose(car["power_kw"], 6.0) and np.isclose(car["leftover_kwh"], 0.0)
    assert np.allclose(car["row"][10:12], 6.0) and np.count_nonzero(car["row"]) == 2


def test_charging_share():
    pool = pd.DataFrame({
        "evse_id": [1, 1, 2, 3, 3, 3],
        # charger 1: Mon 1 and Wed 3 January 2024 (used 2 of 3 weekdays);
        # charger 2: Fri 5 January (1 of 1); charger 3: Fri 5 and Mon 8, twice (2 of 2)
        "start_date": ["2024-01-01", "2024-01-03", "2024-01-05", "2024-01-05", "2024-01-08", "2024-01-08"],
    })
    assert np.isclose(charging_share(pool), 5.0 / 6.0)


def _trip(hid, vid, start, end, wfrom, wto, miles=1.0, drv="01"):
    return {"HOUSEID": hid, "VEHID": vid, "STRTTIME": start, "ENDTIME": end, "WHYFROM": wfrom,
            "WHYTO": wto, "DRVR_FLG": drv, "TRPMILES": miles}


def test_nhts_day_classes_and_windows():
    veh = pd.DataFrame({"HOUSEID": ["1", "1", "2", "3"], "VEHID": ["01", "02", "01", "01"],
                        "TDAYDATE": ["201608"] * 4, "TRAVDAY": ["03"] * 4, "WTHHFIN": [1.0, 2.0, 3.0, 4.0]})
    trips = pd.DataFrame([
        # house 1 vehicle 1: leaves home 07:00, a stop, home at 02:00 (after midnight)
        _trip("1", "01", "0700", "0730", "01", "03", 5.0),
        _trip("1", "01", "1200", "1230", "03", "04", 2.0),
        _trip("1", "01", "1200", "1230", "03", "04", 2.0),          # duplicate driver trip
        _trip("1", "01", "0130", "0200", "04", "01", -9.0),         # missing miles
        _trip("1", "01", "0800", "0900", "01", "03", 9.0, drv="02"),  # passenger trip, left out
        # house 2: drives, never ends at home
        _trip("2", "01", "0800", "0830", "01", "03", 4.0),
        # house 3: drives from and to home, departure after the last arrival home
        _trip("3", "01", "0500", "0530", "03", "01", 1.0),
        _trip("3", "01", "1000", "1030", "01", "03", 1.0),
    ])
    days = vehicle_days(veh, trips).set_index(["HOUSEID", "VEHID"])
    a = days.loc[("1", 1)]
    assert a["day_class"] == "i"
    assert (a["arrival_min"], a["departure_min"], a["window_min"]) == (120, 420, 300)
    assert (a["n_driver_trips"], a["n_miles_missing"]) == (3, 1)
    assert np.isclose(a["driver_miles"], 7.0)
    b = days.loc[("1", 2)]
    assert b["day_class"] == "ii" and b["n_driver_trips"] == 0 and pd.isna(b["window_min"])
    assert days.loc[("2", 1), "day_class"] == "iii"
    assert days.loc[("3", 1), "window_min"] == 1440   # min(1440, d' + 1440 - a')


def test_evwatts_extract_filters():
    evse = pd.DataFrame({
        "evse_id": [1, 2, 3, 4],
        "charge_level": ["L2", "DCFC", "L2", "L2"],
        "venue": ["Single Family Residential", "Single Family Residential", "Workplace", "Multi-Unit Dwelling"],
        "region": ["South Atlantic", "South Atlantic", "South Atlantic", "Pacific"],
    }).set_index("evse_id")
    good = {"evse_id": 1, "start_datetime": "2024-01-03 18:00:00", "end_datetime": "2024-01-04 07:00:00",
            "charge_duration": 3.0, "energy_kwh": 20.0, "flag_id": 0}
    rows = [
        dict(good, evse_id=99),                                   # 1 no evse
        dict(good, evse_id=2),                                    # 2 DCFC
        dict(good, evse_id=3),                                    # 3 workplace
        dict(good, evse_id=4),                                    # 4 Pacific
        dict(good, start_datetime="2024-01-06 18:00:00", end_datetime="2024-01-06 20:00:00"),  # 5 Saturday
        dict(good, end_datetime="2024-01-04 19:00:01"),          # 6 above 24 h
        dict(good, flag_id=64),                                   # 7 flagged
        dict(good, end_datetime="2024-01-03 18:00:00"),          # 8 zero duration
        dict(good, energy_kwh=0.0),                               # 9 no energy
        dict(good, end_datetime="2024-01-03 19:00:00", charge_duration=1.1),  # 10 charging past plug-out
        good,
    ]
    s = pd.DataFrame(rows)
    s.insert(0, "session_id", range(1, len(rows) + 1))
    out, dropped, before_flag = apply_filters(s, evse, ["South Atlantic", "West South Central"])
    assert dropped == [1] * 10
    assert list(out["session_id"]) == [11]
    r = out.iloc[0]
    assert (r["start_date"], r["weekday"], r["month"], r["start_min"], r["plug_min"]) == ("2024-01-03", 2, 1, 1080.0, 780.0)
    assert before_flag == {"South Atlantic": 5}


def test_repaired_generator():
    c = np.zeros(96)
    c[32:96] = 1.0                    # E = 64 / 4 = 16 kWh = 64 kW-intervals: 8 x 7.2 + 6.4
    hosts = [f"h{k}" for k in range(5)]
    cars = session_rows_cars("uncontrolled", hosts, c, 1.0, 1.0, INPUTS, 555)
    rows = np.array([car["row"] for car in cars])
    for car in cars:
        start = car["first_interval"] - 1
        assert np.allclose(car["row"], charge_shape(start, 7.2, 16.0, 96))
        assert np.count_nonzero(car["row"]) == 9
        assert np.isclose(sorted(car["row"][car["row"] > 0])[0], 6.4)
    assert np.isclose(rows.sum() / 4.0, 5 * 16.0)
    again = np.array([car["row"] for car in session_rows_cars("uncontrolled", hosts, c, 1.0, 1.0, INPUTS, 555)])
    other = np.array([car["row"] for car in session_rows_cars("uncontrolled", hosts, c, 1.0, 1.0, INPUTS, 556)])
    assert np.array_equal(rows, again)
    assert not np.array_equal(rows, other)


def _stops(fn, cfg):
    try:
        fn(cfg)
    except SystemExit as e:
        return e.code == 1
    return False


def test_settings():
    for value in ("evwatts_sessions", "nhts_days", "session_rows"):
        assert ev_cars({"ev_cars": value}) == value
    assert ev_home_window({"ev_home_window": True}) is True
    assert ev_home_window({"ev_home_window": False}) is False
    assert _stops(ev_cars, {"ev_cars": "generator"})
    assert _stops(ev_cars, {})
    assert _stops(ev_home_window, {"ev_home_window": "yes"})
    assert _stops(ev_home_window, {"ev_home_window": 1})
    assert _stops(ev_home_window, {})


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
