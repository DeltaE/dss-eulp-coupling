# -*- coding: utf-8 -*-
"""
test_ev_cars.py
---------------
ev_cars.py (Phase 7 deploy, the EV cars) and the two extract scripts on small
hand-made data: the seeds, the level and charging draws, charge_shape and the plug-in
window, the share of cars charging, the NHTS day classes and windows, the NHTS speed
check (class iv), the NHTS work pieces, the EV WATTS
extract filters (residential and office venues, weekday and weekend day types), the
weekend NHTS files, the repaired 2024 generator, the work
cars (charge_window, work_window, work_cars, read_bus_coords, work_share), and the
ev_cars, ev_home_window, ev_day and ev_work_share_case settings.

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
from ev_cars import (charge_shape, charge_window, charging_share, evwatts_cars, load_inputs,  # noqa: E402
                     nhts_cars, pick, plug_window, read_bus_coords, rng, seed, session_rows_cars,
                     window_intervals, work_cars, work_window)
from build_nhts_extract import COLUMNS as NHTS_COLUMNS, DAY_TYPES as NHTS_DAY_TYPES, vehicle_days  # noqa: E402
from build_evwatts_extract import DAY_TYPES as EVWATTS_DAY_TYPES, apply_filters, inside_repository  # noqa: E402
from pipeline_utils import ev_cars, ev_day, ev_home_window, ev_work_share_case  # noqa: E402

INPUTS = {"level2_kw": 7.2, "level1_kw": 1.0, "kwh_per_mile": 33.7 / 99.9}
INPUTS_PATH = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars", "ev_inputs.yaml")
OLD_COLUMNS = ["HOUSEID", "VEHID", "TDAYDATE", "TRAVDAY", "WTHHFIN", "day_class", "arrival_min",
               "departure_min", "window_min", "driver_miles", "n_driver_trips", "n_miles_missing"]


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
    veh = pd.DataFrame({"HOUSEID": ["1", "1", "2", "3", "4"], "VEHID": ["01", "02", "01", "01", "01"],
                        "TDAYDATE": ["201608"] * 5, "TRAVDAY": ["03"] * 5, "WTHHFIN": [1.0, 2.0, 3.0, 4.0, 5.0]})
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
        # house 4: home at 23:00, leaves home at 02:00 after midnight and does not return
        _trip("4", "01", "2200", "2300", "03", "01", 1.0),
        _trip("4", "01", "0200", "0230", "01", "03", 1.0),
    ])
    days = vehicle_days(veh, trips, 85)
    assert list(days.columns)[:12] == OLD_COLUMNS
    days = days.set_index(["HOUSEID", "VEHID"])
    a = days.loc[("1", 1)]
    assert a["day_class"] == "i"
    assert (a["arrival_min"], a["departure_min"], a["window_min"]) == (120, 420, 300)
    assert (a["n_driver_trips"], a["n_miles_missing"]) == (3, 1)
    assert np.isclose(a["driver_miles"], 7.0)
    b = days.loc[("1", 2)]
    assert b["day_class"] == "ii" and b["n_driver_trips"] == 0 and pd.isna(b["window_min"])
    assert days.loc[("2", 1), "day_class"] == "iii"
    assert days.loc[("3", 1), "window_min"] == 270    # d' - a' when d' >= a'
    c = days.loc[("4", 1)]
    assert (c["arrival_min"], c["departure_min"], c["window_min"]) == (1380, 120, 180)
    # the work pieces of the same days: house 1 vehicle 1 parks at work 07:30 to 12:00
    assert (a["n_work_pieces"], a["work_min"], a["work_pieces"]) == (1, 270, "450:270")
    assert (b["n_work_pieces"], b["work_pieces"]) == (0, "") and pd.isna(b["work_min"])
    assert days.loc[("2", 1), "work_pieces"] == "510:1170"     # parked to 04:00 (class iii)
    assert days.loc[("3", 1), "work_pieces"] == "630:1050"
    assert days.loc[("4", 1), "work_pieces"] == "150:90"       # 02:30 at work, parked to 04:00


def test_nhts_work_pieces():
    veh = pd.DataFrame({"HOUSEID": ["1", "2", "3", "4"], "VEHID": ["01"] * 4, "TDAYDATE": ["201608"] * 4,
                        "TRAVDAY": ["03"] * 4, "WTHHFIN": [1.0] * 4})
    trips = pd.DataFrame([
        # house 1: one stay at work, 08:00 to 17:00
        _trip("1", "01", "0730", "0800", "01", "03", 5.0),
        _trip("1", "01", "1700", "1730", "03", "01", 5.0),
        # house 2: a lunch trip splits the stay into two pieces
        _trip("2", "01", "0730", "0800", "01", "03", 5.0),
        _trip("2", "01", "1200", "1215", "03", "13", 1.0),
        _trip("2", "01", "1245", "1300", "13", "03", 1.0),
        _trip("2", "01", "1750", "1820", "03", "01", 5.0),
        # house 3: arrives at work 22:00 and has no later trip: parked to 04:00
        _trip("3", "01", "2130", "2200", "01", "03", 5.0),
        # house 4: the next trip does not start from work; the piece still ends at its start
        _trip("4", "01", "0730", "0800", "01", "03", 5.0),
        _trip("4", "01", "1200", "1230", "01", "04", 2.0),
    ])
    days = vehicle_days(veh, trips, 85).set_index("HOUSEID")
    assert (days.loc["1", "n_work_pieces"], days.loc["1", "work_min"], days.loc["1", "work_pieces"]) == (1, 540, "480:540")
    assert (days.loc["2", "n_work_pieces"], days.loc["2", "work_min"], days.loc["2", "work_pieces"]) == (2, 530, "480:240|780:290")
    assert (days.loc["3", "n_work_pieces"], days.loc["3", "work_min"], days.loc["3", "work_pieces"]) == (1, 360, "1320:360")
    assert (days.loc["4", "n_work_pieces"], days.loc["4", "work_min"], days.loc["4", "work_pieces"]) == (1, 240, "480:240")
    assert list(days.reset_index().columns)[:12] == OLD_COLUMNS


def test_nhts_speed_check():
    # Each house leaves home and returns home (class i unless a trip is too fast).
    # speed = miles / ((end - start, plus 1440 when negative, + 1) / 60), limit 85 mph.
    legs = {
        "1": ("0800", "0830", 30.0),     # 30 / (31/60) = 58.1 mph: passes
        "2": ("0800", "0830", 60.0),     # 60 / (31/60) = 116.1 mph: class iv
        "3": ("0800", "0900", 400.0),    # 400 / (61/60) = 393.4 mph: class iv
        "4": ("2350", "0010", 10.0),     # across midnight, 20 min: 28.6 mph, passes
        "5": ("2350", "0010", 40.0),     # across midnight, 20 min: 114.3 mph, class iv
        "6": ("-9", "0900", 400.0),      # missing start time: not tested
        "7": ("0800", "0830", -9.0),     # missing miles: not tested
    }
    veh = pd.DataFrame({"HOUSEID": list(legs), "VEHID": ["01"] * 7, "TDAYDATE": ["201608"] * 7,
                        "TRAVDAY": ["03"] * 7, "WTHHFIN": [1.0] * 7})
    trips = []
    for hid, (start, end, miles) in legs.items():
        trips.append(_trip(hid, "01", start, end, "01", "03", miles))
        trips.append(_trip(hid, "01", "1700", "1730", "03", "01", 5.0))
    days = vehicle_days(veh, pd.DataFrame(trips), 85)
    assert list(days.columns)[:12] == OLD_COLUMNS
    days = days.set_index("HOUSEID")
    assert days.loc["1", "day_class"] == "i" and days.loc["4", "day_class"] == "i"
    for hid in ("2", "3", "5"):
        d = days.loc[hid]
        assert d["day_class"] == "iv", hid
        assert pd.isna(d["arrival_min"]) and pd.isna(d["departure_min"]) and pd.isna(d["window_min"]), hid
    # missing start time: not tested; its departure from home has no time, so class iii
    assert days.loc["6", "day_class"] == "iii"
    assert days.loc["7", "day_class"] == "i"      # missing miles: not tested
    assert np.isclose(days.loc["3", "driver_miles"], 405.0)


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
        dict(good, energy_kwh=60.0),                              # 11 mean power 20 kW above 19.2
        good,
    ]
    s = pd.DataFrame(rows)
    s.insert(0, "session_id", range(1, len(rows) + 1))
    out, dropped, before_flag = apply_filters(s, evse, ["South Atlantic", "West South Central"], 19.2)
    assert dropped == [1] * 11
    assert list(out["session_id"]) == [12]
    r = out.iloc[0]
    assert (r["start_date"], r["weekday"], r["month"], r["start_min"], r["plug_min"]) == ("2024-01-03", 2, 1, 1080.0, 780.0)
    assert before_flag == {"South Atlantic": 6}
    # the office venue keeps only Business Office rows; the default keeps today's rows
    evse.loc[3, "venue"] = "Business Office"
    office, dropped_o, _ = apply_filters(s, evse, ["South Atlantic", "West South Central"], 19.2,
                                         ["Business Office"])
    assert list(office["session_id"]) == [3] and list(office["venue"]) == ["Business Office"]
    assert dropped_o[2] == 9
    again, dropped_r, _ = apply_filters(s, evse, ["South Atlantic", "West South Central"], 19.2)
    assert list(again["session_id"]) == [12] and dropped_r == [1] * 11


def test_evwatts_extract_day_type():
    """--day-type weekend keeps Saturday and Sunday at rule 5 and every other rule; weekday,
    the default, keeps Monday to Friday; the columns are the same."""
    evse = pd.DataFrame({"evse_id": [1], "charge_level": ["L2"], "venue": ["Single Family Residential"],
                         "region": ["South Atlantic"]}).set_index("evse_id")
    good = {"evse_id": 1, "start_datetime": "2024-01-06 18:00:00", "end_datetime": "2024-01-06 20:00:00",
            "charge_duration": 1.0, "energy_kwh": 5.0, "flag_id": 0}
    rows = [
        good,                                                                                   # Saturday
        dict(good, start_datetime="2024-01-07 09:30:00", end_datetime="2024-01-07 11:00:00"),   # Sunday
        dict(good, start_datetime="2024-01-03 18:00:00", end_datetime="2024-01-03 20:00:00"),   # Wednesday
        dict(good, flag_id=64),                                                                 # Saturday, flagged
        dict(good, start_datetime="2024-01-07 09:30:00", end_datetime="2024-01-07 11:00:00", energy_kwh=0.0),
    ]
    s = pd.DataFrame(rows)
    s.insert(0, "session_id", range(1, len(rows) + 1))
    divisions = ["South Atlantic", "West South Central"]
    weekend, dropped, _ = apply_filters(s, evse, divisions, 19.2, day_type="weekend")
    assert list(weekend["session_id"]) == [1, 2] and list(weekend["weekday"]) == [5, 6]
    assert list(weekend["start_min"]) == [1080.0, 570.0]
    assert dropped == [0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0]    # the Wednesday, the flag, the empty session
    weekday, dropped_w, _ = apply_filters(s, evse, divisions, 19.2)
    assert list(weekday["session_id"]) == [3] and dropped_w[4] == 4
    assert list(weekday.columns) == list(weekend.columns)
    by_name, _, _ = apply_filters(s, evse, divisions, 19.2, day_type="weekday")
    assert by_name.equals(weekday)
    assert EVWATTS_DAY_TYPES["weekday"][1] == (0, 1, 2, 3, 4) and EVWATTS_DAY_TYPES["weekend"][1] == (5, 6)


def test_nhts_extract_day_type():
    """--day-type weekend keeps TRAVDAY 07 and 01 and writes the _weekend files; the rules
    and columns of a vehicle-day are those of a weekday."""
    assert NHTS_DAY_TYPES["weekday"][:2] == ({2, 3, 4, 5, 6}, "")
    assert NHTS_DAY_TYPES["weekend"][:2] == ({7, 1}, "_weekend")
    veh = pd.DataFrame({"HOUSEID": ["1", "2"], "VEHID": ["01", "01"], "TDAYDATE": ["201608"] * 2,
                        "TRAVDAY": ["07", "01"], "WTHHFIN": [1.0, 2.0]})
    trips = pd.DataFrame([_trip("1", "01", "0900", "0930", "01", "04", 3.0),
                          _trip("1", "01", "1100", "1130", "04", "01", 3.0)])
    days = vehicle_days(veh, trips, 85)
    assert list(days.columns) == NHTS_COLUMNS
    assert list(days["TRAVDAY"]) == ["07", "01"] and list(days["day_class"]) == ["i", "ii"]
    assert days.loc[0, "window_min"] == 1290            # home 11:30, leaves 09:00: 21.5 h


def test_weekend_nhts_files():
    """The tracked weekend files hold Saturday and Sunday vehicle-days only, with the
    columns of the weekday files, and nhts2017_extract.yaml records their counts."""
    import yaml
    folder = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars")
    with open(os.path.join(folder, "nhts2017_extract.yaml"), encoding="utf-8") as f:
        record = yaml.safe_load(f)["weekend"]
    for state in ("NC", "TX"):
        name = f"{state}_nhts2017_vehicle_days_weekend.csv"
        assert name in record["files"]
        days = pd.read_csv(os.path.join(folder, name), dtype={"TRAVDAY": str, "day_class": str})
        weekday = pd.read_csv(os.path.join(folder, f"{state}_nhts2017_vehicle_days.csv"), nrows=5)
        assert list(days.columns) == list(weekday.columns) == NHTS_COLUMNS
        assert set(days["TRAVDAY"]) == {"07", "01"}
        for day, code in (("Saturday", "07"), ("Sunday", "01")):
            for cls in ("i", "ii", "iii", "iv"):
                assert record["rows_per_state_day_and_class"][state][day][cls] == \
                    int(((days["TRAVDAY"] == code) & (days["day_class"] == cls)).sum())


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


def test_charge_window():
    # on a contiguous window charge_window equals charge_shape
    for a, n_w, e in ((40, 5, 5.0), (94, 10, 5.0), (0, 96, 60.0), (10, 2, 7.0)):
        assert np.array_equal(charge_window(window_intervals(a, n_w), 7.2, e), charge_shape(a, 7.2, e, n_w))
    # a two-piece window (08:00 to 12:00 and 13:00 to 17:00) is filled in list order: 20 kWh at
    # 7.2 kW = 80 kW-intervals = 11 full intervals and 0.8 kW left, all inside the first piece
    a, window, minute = work_window("480:240|780:240")
    assert (a, minute) == (32, 480.0)
    row = charge_window(window, 7.2, 20.0)
    assert list(np.flatnonzero(row)) == list(range(32, 44))
    assert np.isclose(row[43], 0.8) and np.isclose(row.sum() / 4.0, 20.0)
    # 50 kWh = 200 kW-intervals = 27 full intervals and 5.6 kW left: the first piece (16
    # intervals) fills, then the second piece from interval 52, the leftover in interval 63
    row = charge_window(window, 7.2, 50.0)
    assert list(np.flatnonzero(row)) == list(range(32, 48)) + list(range(52, 64))
    assert np.isclose(row[63], 5.6) and np.isclose(row.sum() / 4.0, 50.0)
    # 60 kWh does not fit in the 32 intervals: every interval gets 7.2 kW, 2.4 kWh is left over
    row = charge_window(window, 7.2, 60.0)
    assert np.count_nonzero(row) == 32 and np.isclose(row.sum() / 4.0, 57.6)


def test_work_window():
    a, window, minute = work_window("480:240|780:290")
    assert (a, minute) == (32, 480.0)
    assert window == list(range(32, 48)) + list(range(52, 72))
    assert len(window) == 36
    # a piece that wraps past midnight and a repeated interval are not duplicated
    a, window, minute = work_window("1410:60|0:30")
    assert (a, minute) == (94, 1410.0)
    assert window == [94, 95, 0, 1]


def _office_pool():
    return pd.DataFrame({"session_id": [101, 102, 103], "start_min": [480.0, 510.0, 540.0],
                         "plug_min": [240.0, 180.0, 300.0], "charge_h": [2.0, 1.5, 2.5],
                         "energy_kwh": [12.0, 9.0, 15.0]})


def _same_car(a, b):
    return all(np.array_equal(a[k], b[k]) if isinstance(a[k], np.ndarray) else a[k] == b[k] for k in a) and a.keys() == b.keys()


def test_work_cars():
    pool = pd.DataFrame({"session_id": [9], "start_min": [1080.0], "plug_min": [600.0], "charge_h": [2.0],
                         "energy_kwh": [10.0]})
    hosts = [f"h{k}" for k in range(30)]
    cars = evwatts_cars("uncontrolled", hosts, pool, 1.0, 1.0, INPUTS, 555)
    offices = ["off_a", "off_b", "off_c"]
    # share 0: the same list, nothing drawn
    assert work_cars("uncontrolled", cars, 0.0, offices, INPUTS, 555, "evwatts_sessions", _office_pool()) is cars
    # no charging car: the same list
    idle = evwatts_cars("uncontrolled", hosts[:5], pool, 0.0, 1.0, INPUTS, 555)
    assert work_cars("uncontrolled", idle, 0.5, offices, INPUTS, 555, "evwatts_sessions", _office_pool()) is idle
    # session_rows: the work share is not applied
    assert work_cars("uncontrolled", cars, 0.5, offices, INPUTS, 555, "session_rows") is cars
    # share 0.10 on 30 charging cars: floor(0.10 x 30 + 0.5) = 3 work cars
    out = work_cars("uncontrolled", cars, 0.10, offices, INPUTS, 555, "evwatts_sessions", _office_pool())
    work = [k for k, c in enumerate(out) if c["place"] == "work"]
    assert len(out) == 30 and len(work) == 3
    for k, c in enumerate(out):
        if k in work:
            assert c["place_load"] in offices and c["car"] == cars[k]["car"] and c["host"] == cars[k]["host"]
            assert c["group"] == "uncontrolled" and c["level"] == "L2" and c["charges_today"]
            assert c["source_id"] in ("101", "102", "103") and c["charging_share"] == cars[k]["charging_share"]
            assert np.isclose(c["delivered_kwh"], c["energy_kwh"])
            assert cars[k]["place"] == "home" and cars[k]["place_load"] == cars[k]["host"]
        else:
            assert _same_car(c, cars[k])
    again = work_cars("uncontrolled", cars, 0.10, offices, INPUTS, 555, "evwatts_sessions", _office_pool())
    assert all(_same_car(a, b) for a, b in zip(out, again))
    other = work_cars("uncontrolled", cars, 0.10, offices, INPUTS, 556, "evwatts_sessions", _office_pool())
    assert [c["place"] for c in other] != [c["place"] for c in out] or \
        [c["place_load"] for c in other] != [c["place_load"] for c in out] or \
        [c["source_id"] for c in other] != [c["source_id"] for c in out]
    # the controlled group draws with its own names
    cars_c = evwatts_cars("controlled", hosts, pool, 1.0, 1.0, INPUTS, 555)
    out_c = work_cars("controlled", cars_c, 0.10, offices, INPUTS, 555, "evwatts_sessions", _office_pool())
    assert sum(c["place"] == "work" for c in out_c) == 3
    # nhts_days: a work car's row sums to its energy when the window holds it
    days = pd.DataFrame({"HOUSEID": ["7"], "VEHID": [1], "TDAYDATE": ["201608"], "TRAVDAY": ["03"], "WTHHFIN": [1.0],
                         "day_class": ["i"], "arrival_min": [1080], "departure_min": [420], "window_min": [780],
                         "driver_miles": [30.0], "n_driver_trips": [2], "n_miles_missing": [0]})
    work_days = pd.DataFrame({"HOUSEID": ["8", "9"], "VEHID": [1, 2], "WTHHFIN": [1.0, 1.0], "day_class": ["i", "i"],
                              "driver_miles": [30.0, 40.0], "n_work_pieces": [1, 2],
                              "work_pieces": ["480:540", "480:240|780:290"]})
    cars_n = nhts_cars("uncontrolled", hosts, days, 1.0, INPUTS, 555)
    out_n = work_cars("uncontrolled", cars_n, 0.10, offices, INPUTS, 555, "nhts_days", work_day_pool=work_days)
    work_n = [c for c in out_n if c["place"] == "work"]
    assert len(work_n) == 3
    for c in work_n:
        assert c["source_id"] in ("8-1", "9-2") and c["day_class"] == "i" and c["power_kw"] == 7.2
        assert c["plug_in_interval"] == 33 and c["plug_minute"] == 480.0
        assert np.isclose(c["energy_kwh"], (30.0 if c["source_id"] == "8-1" else 40.0) * INPUTS["kwh_per_mile"])
        assert np.isclose(c["row"].sum() / 4.0, c["energy_kwh"]) and np.isclose(c["leftover_kwh"], 0.0)
        assert c["window_intervals"] == 36
        assert set(np.flatnonzero(c["row"])) <= set(c["window"])


def test_read_bus_coords(tmp_path):
    p = tmp_path / "Buscoords.dss"
    p.write_text("udm715 -79.8022855531746 36.08618863548974\nB2,-79.1,36.2\n\nnot a line\nb3 x y\n",
                 encoding="utf-8")
    assert read_bus_coords(str(p)) == {"udm715": (-79.8022855531746, 36.08618863548974), "b2": (-79.1, 36.2)}


def test_work_share_inputs():
    for value_set in ("typical", "stress"):
        assert load_inputs(INPUTS_PATH, value_set)["work_share"] == {"low": 0.0, "moderate": 0.10, "high": 0.20}


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
    for value in ("typical", "stress"):
        assert ev_day({"ev_day": value}) == value
    assert _stops(ev_day, {"ev_day": "peak"})
    assert _stops(ev_day, {})
    for value in ("low", "moderate", "high"):
        assert ev_work_share_case({"ev_work_share_case": value}) == value
    assert _stops(ev_work_share_case, {"ev_work_share_case": "medium"})
    assert _stops(ev_work_share_case, {})



def test_empty_office_pool_stops():
    """An empty office pool stops work_cars with [FAIL], not with a numpy error."""
    pool = pd.DataFrame({"session_id": [1], "energy_kwh": [8.0], "charge_h": [2.0], "start_min": [1080.0],
                         "plug_min": [600.0]})
    cars = evwatts_cars("uncontrolled", ["a", "b", "c", "d"], pool, 1.0, 1.0, INPUTS, 7)
    try:
        work_cars("uncontrolled", cars, 0.5, ["office_a"], INPUTS, 7, "evwatts_sessions",
                  office_pool=pool.iloc[0:0], where="South Atlantic")
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected a stop")


def test_empty_one_day_pools_stop():
    """An empty pool stops the one-day draws with [FAIL] and exit 1, not with a numpy
    error: the EV WATTS sessions of evwatts_cars, the NHTS vehicle-days of nhts_cars and
    the NHTS windows of session_rows_cars."""
    sessions = pd.DataFrame({"session_id": [1], "energy_kwh": [8.0], "charge_h": [2.0], "start_min": [1080.0],
                             "plug_min": [600.0]})
    days = pd.DataFrame({"HOUSEID": ["1"], "VEHID": [1], "WTHHFIN": [1.0], "day_class": ["i"],
                         "arrival_min": [1080.0], "window_min": [600.0], "driver_miles": [30.0]})
    calls = [
        lambda: evwatts_cars("uncontrolled", ["a", "b"], sessions.iloc[0:0], 1.0, 1.0, INPUTS, 7,
                             where="South Atlantic"),
        lambda: evwatts_cars("uncontrolled", [], sessions.iloc[0:0], 1.0, 1.0, INPUTS, 7),
        lambda: nhts_cars("controlled", ["a", "b"], days.iloc[0:0], 1.0, INPUTS, 7, where="NC"),
        lambda: session_rows_cars("controlled", ["a", "b"], np.ones(96), 1.0, 1.0, INPUTS, 7,
                                  window_pool=days.iloc[0:0], where="NC"),
    ]
    for call in calls:
        try:
            call()
        except SystemExit as e:
            assert e.code == 1
        else:
            raise AssertionError("expected a stop")
    # a pool with a row still draws
    assert len(evwatts_cars("uncontrolled", ["a", "b"], sessions, 1.0, 1.0, INPUTS, 7)) == 2


def test_extract_dir_inside_repository():
    """The extract folder is refused when it is the repository or inside it. A folder
    beside the repository whose name starts with the repository's name is accepted."""
    repo = os.path.join(os.path.abspath(os.sep), "work", "dss-eulp-coupling")
    assert inside_repository(repo, repo)
    assert inside_repository(os.path.join(repo, "data", "extract"), repo)
    assert inside_repository(os.path.join(repo.upper(), "Extract"), repo)
    assert not inside_repository(repo + "_extract", repo)
    assert not inside_repository(os.path.join(repo + "_scratch", "extract"), repo)
    assert not inside_repository(os.path.dirname(repo), repo)


def test_weekend_charging_share():
    pool = pd.DataFrame({"evse_id": [1, 1, 2], "start_date": ["2024-01-06", "2024-01-14", "2024-01-07"]})
    assert np.isclose(charging_share(pool, day_type="weekend"), 3.0 / 5.0)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
