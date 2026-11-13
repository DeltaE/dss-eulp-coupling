# -*- coding: utf-8 -*-
"""
test_multi_day.py
-----------------
The multi-day window (horizon_days in pipeline_config.yaml) on small hand-made data:
the settings readers; the window dates and their shift inside the season; the season
months in their four places; window_days.csv with the federal holidays; the Phase 5b
cut of a window; the peak of day X; loadshape names with text; the EV cars over a
window (charging days, weekend sessions, work cars, the top-up of energy that did not
fit, the timeline past midnight and the energy owed at the end); the forecast per day
and the weekend tariff row; and the storage schedule over several days. Needs no
SMART-DS/EULP data.

Run directly (no pytest needed): python tests/test_multi_day.py
Or under pytest: pytest tests/test_multi_day.py
"""
import ast
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation"))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from pipeline_utils import (EV_VALLEY_DAYS, FEDERAL_HOLIDAYS, GIVEN_SEASON_MONTHS, SETTINGS_ENV,  # noqa: E402
                            STEPS_PER_DAY, WINDOW_DAYS_COLUMNS, WINDOW_YEAR, day_type, ev_valley_day,
                            horizon_days, load_config, season_months, season_stretches, window_dates,
                            window_day_rows)
from der_sizing import CHOICES, day_peak, loadshape_building  # noqa: E402
from ev_cars import (charging_share, draw_name, event_row, evwatts_cars, evwatts_session, load_inputs,  # noqa: E402
                     nhts_cars, nhts_session, nhts_work_session, plan_car, rng, window_group, work_cars)
from ev_control import cheap_intervals, forecast_curve, forecast_days  # noqa: E402
from storage_control import (_energy, _plan, best_start, best_window_start, schedule,  # noqa: E402
                             schedule_days)
from test_caller_settings import _ensure_local_yaml  # noqa: E402

DEPLOY = os.path.join(REPO_ROOT, "7_circuit_instantiation", "power_flow_sim_daily_EV_STO_DG_deploy.py")
PHASE5B = os.path.join(REPO_ROOT, "5b_profile_generation", "find_max_day_curve_impl.py")
INPUTS_PATH = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars", "ev_inputs.yaml")
INPUTS = {"level2_kw": 7.2, "level1_kw": 1.0, "kwh_per_mile": 33.7 / 99.9}
DT = 0.25
STEPS = np.arange(96)
# Night valley around 04:00, evening peak around 18:00 (kW), as test_storage_control.py
CURVE = 1000.0 - 400.0 * np.cos((STEPS - 16) / 96.0 * 2.0 * np.pi)

# Day X of the default runs: (state, feeder, season, mix): (month, day)
DAYS_X = {
    ("NC", "udt4015", "summer", "baseline"): (6, 19), ("NC", "udt4015", "summer", "mixed"): (6, 19),
    ("NC", "udt4015", "summer", "stress"): (6, 19), ("NC", "udt4015", "winter", "baseline"): (2, 16),
    ("NC", "udt4015", "winter", "mixed"): (1, 2), ("NC", "udt4015", "winter", "stress"): (1, 5),
    ("NC", "udt4819", "summer", "baseline"): (8, 16), ("NC", "udt4819", "summer", "mixed"): (8, 16),
    ("NC", "udt4819", "summer", "stress"): (8, 30), ("NC", "udt4819", "winter", "baseline"): (2, 16),
    ("NC", "udt4819", "winter", "mixed"): (1, 8), ("NC", "udt4819", "winter", "stress"): (1, 8),
    ("TX", "p2udt5222", "summer", "baseline"): (7, 17), ("TX", "p2udt5222", "summer", "mixed"): (7, 17),
    ("TX", "p2udt5222", "summer", "stress"): (8, 2), ("TX", "p2udt5222", "winter", "baseline"): (1, 18),
    ("TX", "p2udt5222", "winter", "mixed"): (1, 19), ("TX", "p2udt5222", "winter", "stress"): (1, 19),
    ("TX", "p2udt5984", "summer", "baseline"): (7, 20), ("TX", "p2udt5984", "summer", "mixed"): (7, 20),
    ("TX", "p2udt5984", "summer", "stress"): (7, 20), ("TX", "p2udt5984", "winter", "baseline"): (1, 19),
    ("TX", "p2udt5984", "winter", "mixed"): (1, 19), ("TX", "p2udt5984", "winter", "stress"): (1, 19),
}


def _stops(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except SystemExit as e:
        return e.code == 1
    return False


def _function(path, name, namespace):
    """One function of a script that runs on import, taken from its source text."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
            return namespace[name]
    raise AssertionError(f"{name} not found in {path}")


def _date(month, day):
    return datetime.date(WINDOW_YEAR, month, day)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_horizon_days_reader():
    for value in (1, 7, 14, 3):
        assert horizon_days({"horizon_days": value}) == value
    assert horizon_days({"horizon_days": 7.0}) == 7
    for bad in (0, -1, 2.5, "7", True, None):
        assert _stops(horizon_days, {"horizon_days": bad}), bad
    assert _stops(horizon_days, {})
    assert horizon_days(load_config(os.path.join(REPO_ROOT, "pipeline_config.yaml"))) == 7
    assert STEPS_PER_DAY == 96


def test_ev_valley_day_and_schedule_start_settings():
    for value in ("own_day", "peak_day"):
        assert ev_valley_day({"ev_valley_day": value}) == value
    assert EV_VALLEY_DAYS == ("own_day", "peak_day")
    assert _stops(ev_valley_day, {"ev_valley_day": "window"})
    assert _stops(ev_valley_day, {})
    cfg = load_config(os.path.join(REPO_ROOT, "pipeline_config.yaml"))
    assert ev_valley_day(cfg) == "own_day"
    assert CHOICES["schedule_start"] == ("best", "best_window", "fixed")
    assert cfg["der_sizing"]["schedule_start"] == "best"


def _dry_run(folder):
    env = {k: v for k, v in os.environ.items() if k != SETTINGS_ENV}
    case_path = os.path.join(REPO_ROOT, "configs", "cases", "NC_GSO_urban__NC.yaml")
    return subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "run_case.py"), "--case", case_path,
         "--all", "--season", "summer", "--dry-run", "--settings", folder],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


def test_run_case_stops_on_a_bad_horizon():
    local_path, metadata_dir = _ensure_local_yaml()
    folder = tempfile.mkdtemp()
    try:
        for text, code in (("horizon_days: 1\n", 0), ("horizon_days: 14\n", 0), ("horizon_days: 0\n", 1),
                           ("horizon_days: 2.5\n", 1)):
            with open(os.path.join(folder, "pipeline_config.yaml"), "w", encoding="utf-8") as f:
                f.write(text)
            proc = _dry_run(folder)
            assert proc.returncode == code, proc.stdout + proc.stderr
            assert ("[FAIL] horizon_days in pipeline_config.yaml" in proc.stdout) == (code == 1), proc.stdout
            if code == 1:
                assert "PHASE" not in proc.stdout       # no phase runs
    finally:
        shutil.rmtree(folder)
        if metadata_dir:
            os.remove(local_path)
            os.rmdir(metadata_dir)


# ---------------------------------------------------------------------------
# The window dates (D2), the season months (F1) and the holidays (F6)
# ---------------------------------------------------------------------------
def test_season_months_agree_in_every_place():
    """The season months sit in Phase 3, in Phase 5b, in ev_inputs.yaml (typical and
    stress) and in pipeline_utils.GIVEN_SEASON_MONTHS; the window reads Phase 5b."""
    phase5b = season_months()
    assert season_months(PHASE5B) == phase5b
    phase3 = season_months(os.path.join(REPO_ROOT, "3_tolerance_matching", "match_smartds_parquets_impl.py"))
    with open(INPUTS_PATH, encoding="utf-8") as f:
        ev = yaml.safe_load(f)["season_months"]
    for season in ("winter", "summer"):
        months = set(phase5b[season])
        assert set(phase3[season]) == months
        assert set(ev["typical"][season]) == months and set(ev["stress"][season]) == months
        assert set(GIVEN_SEASON_MONTHS[season]) == months
    assert set(phase5b) == {"winter", "summer"} == set(GIVEN_SEASON_MONTHS)


def test_season_stretches_never_cross_december():
    assert season_stretches([1, 2, 12]) == [(_date(1, 1), _date(2, 28)), (_date(12, 1), _date(12, 31))]
    assert season_stretches([6, 7, 8]) == [(_date(6, 1), _date(8, 31))]


def test_window_dates_of_the_default_runs():
    # one day: day X alone, whatever the season
    assert window_dates(6, 19, "summer", 1) == ([_date(6, 19)], 0)
    # 7 days: X-3 to X+3; 14 days: X-6 to X+7
    dates, x = window_dates(6, 19, "summer", 7)
    assert (dates[0], dates[-1], x, len(dates)) == (_date(6, 16), _date(6, 22), 3, 7)
    dates, x = window_dates(6, 19, "summer", 14)
    assert (dates[0], dates[-1], x, len(dates)) == (_date(6, 13), _date(6, 26), 6, 14)
    # the shifts of the default runs: 2 January at 7 days, 30 August at 7 and 14 days
    dates, x = window_dates(1, 2, "winter", 7)
    assert (dates[0], dates[-1], x) == (_date(1, 1), _date(1, 7), 1)
    dates, x = window_dates(8, 30, "summer", 7)
    assert (dates[0], dates[-1], x) == (_date(8, 25), _date(8, 31), 5)
    dates, x = window_dates(8, 30, "summer", 14)
    assert (dates[0], dates[-1], x) == (_date(8, 18), _date(8, 31), 12)
    for (state, feeder, season, mix), (month, day) in DAYS_X.items():
        for days in (7, 14):
            dates, x = window_dates(month, day, season, days)
            assert len(dates) == days and dates[x] == _date(month, day)
            assert all((b - a).days == 1 for a, b in zip(dates, dates[1:]))
            stretch = next(s for s in season_stretches(season_months()[season]) if s[0] <= dates[x] <= s[1])
            assert stretch[0] <= dates[0] and dates[-1] <= stretch[1]
            # day X at position ceil(days / 2) unless the season's edge shifts the window
            if dates[0] != stretch[0] and dates[-1] != stretch[1]:
                assert x == (days + 1) // 2 - 1


def test_window_dates_december_and_the_end_of_august():
    # December is its own stretch: the window never crosses 31 December
    dates, x = window_dates(12, 30, "winter", 7)
    assert (dates[0], dates[-1], x) == (_date(12, 25), _date(12, 31), 5)
    dates, x = window_dates(12, 2, "winter", 14)
    assert (dates[0], dates[-1], x) == (_date(12, 1), _date(12, 14), 1)
    dates, x = window_dates(12, 15, "winter", 7)
    assert (dates[0], dates[-1], x) == (_date(12, 12), _date(12, 18), 3)
    # the end of February and of August
    dates, x = window_dates(2, 27, "winter", 7)
    assert (dates[0], dates[-1], x) == (_date(2, 22), _date(2, 28), 5)
    dates, x = window_dates(8, 31, "summer", 7)
    assert (dates[0], dates[-1], x) == (_date(8, 25), _date(8, 31), 6)
    dates, x = window_dates(6, 1, "summer", 14)
    assert (dates[0], dates[-1], x) == (_date(6, 1), _date(6, 14), 0)
    # stops: a window longer than its stretch, a day outside the season, an unknown season
    assert _stops(window_dates, 12, 15, "winter", 32)
    assert window_dates(12, 15, "winter", 31)[0][0] == _date(12, 1)
    assert _stops(window_dates, 3, 15, "winter", 7)
    assert _stops(window_dates, 6, 19, "spring", 7)


def test_window_day_rows_and_holidays():
    assert set(FEDERAL_HOLIDAYS) == {(1, 1), (1, 15), (2, 19), (5, 28), (7, 4), (9, 3), (10, 8), (11, 12),
                                     (11, 22), (12, 25)}
    dates, x = window_dates(2, 16, "winter", 7)           # 13 to 19 February 2018
    rows = window_day_rows(dates, x)
    assert list(rows[0]) == WINDOW_DAYS_COLUMNS
    assert [r["weekday"] for r in rows] == ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                                            "Monday"]
    assert [r["day_type"] for r in rows] == ["weekday"] * 4 + ["weekend"] * 2 + ["weekday"]
    assert [r["day_index"] for r in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert [r["day_x"] for r in rows] == [0, 0, 0, 1, 0, 0, 0]
    assert [r["holiday"] for r in rows] == [""] * 6 + ["Washington's Birthday"]   # a holiday stays a weekday
    assert rows[3]["date"] == "2018-02-16"
    assert day_type(_date(6, 16)) == "weekend" and day_type(_date(6, 19)) == "weekday"
    # windows of the default runs that hold a federal holiday: 4 of 24 at 7 days, 12 of 24 at 14 days
    for days, expected in ((7, 4), (14, 12)):
        with_holiday = [key for key, (month, day) in DAYS_X.items()
                        if any(r["holiday"] for r in window_day_rows(*window_dates(month, day, key[2], days)))]
        assert len(with_holiday) == expected, with_holiday
    at_7 = {key for key, (month, day) in DAYS_X.items()
            if any(r["holiday"] for r in window_day_rows(*window_dates(month, day, key[2], 7)))}
    assert at_7 == {("NC", "udt4015", "winter", "baseline"), ("NC", "udt4819", "winter", "baseline"),
                    ("NC", "udt4015", "winter", "mixed"), ("TX", "p2udt5222", "winter", "baseline")}


def test_phase5b_cuts_the_window_in_date_order():
    """window_rows of Phase 5b: each day cut by month and day, joined in date order; the
    year's last row, stamped 1 January 00:00 of the next year, belongs to 1 January."""
    window_rows = _function(PHASE5B, "window_rows", {"pd": pd, "sys": sys, "WINDOW_YEAR": WINDOW_YEAR})
    stamps = list(pd.date_range("2018-01-01 00:15", "2018-01-04 00:00", freq="15min")) + \
        [pd.Timestamp("2019-01-01 00:00")]
    df = pd.DataFrame({"timestamp": stamps, "v": np.arange(len(stamps), dtype=float)})
    cut = window_rows(df, [_date(1, 1), _date(1, 2), _date(1, 3)], "test")
    assert len(cut) == 3 * 96
    assert list(cut["timestamp"].iloc[:95]) == stamps[:95]
    assert cut["timestamp"].iloc[95] == pd.Timestamp("2019-01-01 00:00")     # 1 January ends with the year's last row
    assert cut["timestamp"].iloc[96] == pd.Timestamp("2018-01-02 00:00")
    assert list(cut["timestamp"].iloc[96:]) == stamps[95:95 + 192]
    one = window_rows(df, [_date(1, 2)], "test")
    assert one.equals(df[(df["timestamp"].dt.month == 1) & (df["timestamp"].dt.day == 2)])
    other_year = df.assign(timestamp=df["timestamp"] - pd.DateOffset(years=6))
    assert _stops(window_rows, other_year, [_date(1, 2)], "test")


# ---------------------------------------------------------------------------
# Sizes (D14) and loadshape names (F4)
# ---------------------------------------------------------------------------
def test_day_peak_reads_day_x():
    values = np.concatenate([np.full(96, 2.0), np.linspace(1.0, 5.0, 96), np.full(96, 9.0)])
    assert day_peak(values) == 9.0
    assert day_peak(values, 1) == 5.0 and day_peak(values, 0) == 2.0 and day_peak(values, 2) == 9.0
    assert day_peak(values[:96], 0) == day_peak(values[:96]) == 2.0


def test_peak_kw_for_load_reads_day_x(tmp_path=None):
    """The deploy's peak_kw_for_load on a three-day profile: the peak of day X's 96
    values with horizon_days above 1, the whole profile's peak at horizon_days 1."""
    folder = tempfile.mkdtemp() if tmp_path is None else str(tmp_path)
    try:
        values = np.concatenate([np.full(96, 2.0), np.linspace(1.0, 5.0, 96), np.full(96, 9.0)])
        np.savetxt(os.path.join(folder, "res_kw_7_pu.csv"), values, fmt="%.4f")
        namespace = {"os": os, "re": __import__("re"), "pd": pd, "sys": sys, "day_peak": day_peak,
                     "base_to_daily": {"load_a": {"res_kw_7_pu"}}, "PROFILES_PATH": folder,
                     "PATH_LOADS_DSS_ORIG": os.path.join(folder, "none.dss"), "IRRADIANCE_NPTS": 96,
                     "HORIZON_DAYS": 3, "X_INDEX": 1}
        peak = _function(DEPLOY, "peak_kw_for_load", namespace)
        assert peak("load_a_1") == 5.0
        namespace["X_INDEX"] = 0
        assert peak("load_a") == 2.0
        namespace["HORIZON_DAYS"] = 1
        assert peak("load_a") == 9.0
    finally:
        if tmp_path is None:
            shutil.rmtree(folder)


def test_loadshape_building_keeps_text_names():
    assert loadshape_building("res_kw_9312-North_pu") == ("res", "9312-North")
    assert loadshape_building("res_kw_9312_pu") == ("res", "9312")
    assert loadshape_building("com_kw_12815_pu") == ("com", "12815")
    assert loadshape_building("com_kw_0042_pu") == ("com", "0042")           # text, not a number
    assert loadshape_building("flat_shape") is None and loadshape_building("res_kvar_9312_pu") is None
    # the deploy matches Yearly_Number read as text, so an integer column never becomes 9312.0
    frame = pd.read_csv(__import__("io").StringIO("Feeder,Yearly_Type,Yearly_Number\nf,res,9312\nf,res,9312-North\n"),
                        dtype={"Yearly_Number": str})
    for name, row in (("res_kw_9312_pu", 0), ("res_kw_9312-North_pu", 1)):
        kind, number = loadshape_building(name)
        hit = frame[(frame["Yearly_Type"] == kind) & (frame["Yearly_Number"] == number)]
        assert list(hit.index) == [row]
    with open(DEPLOY, encoding="utf-8") as f:
        src = f.read()
    assert 'dtype={"Yearly_Number": str}' in src and "loadshape_building(shapes[0])" in src


# ---------------------------------------------------------------------------
# EV cars over a window (D8 to D12, F2, F3)
# ---------------------------------------------------------------------------
def _nhts_30022175():
    """The vehicle-day of section 4b, from the tracked extract: household 30022175
    vehicle 1, home at 18:40 for 740 minutes (intervals 18:30 to 07:00)."""
    days = pd.read_csv(os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars",
                                    "NC_nhts2017_vehicle_days.csv"),
                       dtype={"HOUSEID": str, "TDAYDATE": str, "TRAVDAY": str, "day_class": str})
    return days[(days["HOUSEID"] == "30022175") & (days["VEHID"] == 1)].iloc[0]


def test_top_up_worked_example():
    """A Level 1 car at 1.0 kW, plugged 18:30 to 07:00 (50 intervals), 15.23 kWh a day at
    0.337 kWh per mile: 12.50 kWh fit and 2.73 kWh are left over each charging night.
    Charging days 1, 4, 5 and 6 of 7: top-up 2.73 kWh on day 2 and 8.20 kWh on day 7,
    60.9 kWh in the car's windows and nothing owed there; 50.0 kWh if leftovers are
    dropped. The repository's 33.7 / 99.9 kWh per mile gives 15.25 kWh a day."""
    d = _nhts_30022175()
    s = nhts_session(d, "home_a", 1.0, 0.337)
    assert s["offsets"] == list(range(74, 124)) and s["charges"] and s["plug_minute"] == 1120.0
    assert abs(s["energy"] - 15.23) < 0.005
    assert abs(nhts_session(d, "home_a", 1.0, INPUTS["kwh_per_mile"])["energy"] - 15.25) < 0.005
    charges = [False, True, False, False, True, True, True, False]
    events, days = plan_car([s] * 8, charges, 7)
    assert [e["p"] for e in events] == [1, 2, 4, 5, 6, 7]
    assert [e["kind"] for e in events] == ["session", "top_up", "session", "session", "session", "top_up"]
    assert all(abs(days[p]["fit_kwh"] - 12.5) < 1e-9 for p in (1, 4, 5, 6))
    assert abs(days[2]["fit_kwh"] - 2.73) < 0.006 and abs(days[2]["topup_kwh"] - 2.73) < 0.006
    assert abs(days[7]["fit_kwh"] - 8.20) < 0.006
    assert days[3]["kind"] == "" and days[3]["fit_kwh"] == 0.0        # nothing owed on day 3
    assert abs(sum(day["fit_kwh"] for day in days) - 60.9) < 0.05
    assert abs(days[7]["backlog_kwh"]) < 1e-9                          # nothing owed inside the windows
    assert abs(days[1]["backlog_kwh"] - 2.73) < 0.006 and abs(days[6]["backlog_kwh"] - 8.20) < 0.006
    # the car charges only inside its window and never above its power
    for e in events:
        row = event_row(e, 7 * 96)
        assert row.max() <= 1.0 + 1e-12
        assert set(np.flatnonzero(row)) <= set(e["window"])
    # leftovers dropped: 50.0 kWh
    _, dropped = plan_car([s] * 8, charges, 7, top_up=False)
    assert abs(sum(day["fit_kwh"] for day in dropped) - 50.0) < 1e-9
    assert [day["kind"] for day in dropped] == ["", "session", "", "", "session", "session", "session", ""]


def test_owed_energy_at_the_window_end():
    """On the run's steps the day 7 top-up of the worked example starts at 18:30 and
    stops at the window's last midnight: 5.50 kWh are delivered and the 2.70 kWh that
    would follow are owed. needed = delivered + owed, and owed = backlog + tails."""
    s = nhts_session(_nhts_30022175(), "home_a", 1.0, 0.337)
    charges = [False, True, False, False, True, True, True, False]
    events, days = plan_car([s] * 8, charges, 7)
    assert abs(days[7]["delivered_kwh"] - 5.5) < 1e-9 and abs(days[7]["tail_kwh"] - 2.70) < 0.006
    needed = sum(day["needed_kwh"] for day in days)
    delivered = sum(day["delivered_kwh"] for day in days)
    assert abs(needed - 4 * s["energy"]) < 1e-9
    assert abs(needed - delivered - days[-1]["owed_kwh"]) < 1e-9
    assert abs(days[-1]["owed_kwh"] - (days[-1]["backlog_kwh"] + sum(day["tail_kwh"] for day in days))) < 1e-9
    assert abs(days[-1]["owed_kwh"] - 2.70) < 0.006
    assert abs(sum(event_row(e, 7 * 96).sum() for e in events) / 4.0 - delivered) < 1e-9
    # a session on the last day: its part after the last midnight is owed too
    events, days = plan_car([s] * 8, [False] * 7 + [True], 7)
    assert abs(days[7]["delivered_kwh"] - 5.5) < 1e-9
    assert abs(days[7]["owed_kwh"] - (s["energy"] - 5.5)) < 1e-9
    assert abs(days[7]["tail_kwh"] - 7.0) < 1e-9 and abs(days[7]["backlog_kwh"] - (s["energy"] - 12.5)) < 1e-9


def test_every_day_charging_has_no_top_up():
    """charging_share all: a car that charges every day has no free evening."""
    s = nhts_session(_nhts_30022175(), "home_a", 1.0, 0.337)
    events, days = plan_car([s] * 8, [True] * 8, 7)
    assert all(e["kind"] == "session" for e in events) and len(events) == 8
    assert sum(day["topup_kwh"] for day in days) == 0.0
    assert abs(days[7]["backlog_kwh"] - 7 * (s["energy"] - 12.5)) < 1e-9


def test_a_car_without_leftover_is_unchanged_by_top_up():
    s = evwatts_session({"session_id": 5, "energy_kwh": 10.0, "charge_h": 2.0, "start_min": 1080.0,
                         "plug_min": 600.0}, "home_b")
    assert s["power"] == 5.0 and s["offsets"] == list(range(72, 112))
    charges = [False, True, False, True, True, False, False, True]
    with_top_up = plan_car([s] * 8, charges, 7)
    without = plan_car([s] * 8, charges, 7, top_up=False)
    assert [e["kind"] for e in with_top_up[0]] == ["session"] * 4
    for a, b in zip(with_top_up[1], without[1]):
        assert a == b
    assert all(day["backlog_kwh"] == 0.0 and day["owed_kwh"] < 1e-9 for day in with_top_up[1])
    for e in with_top_up[0]:
        assert np.count_nonzero(event_row(e, 7 * 96)) == 8 and abs(e["delivered_kwh"] - 10.0) < 1e-9


def test_day_1_receives_the_part_after_midnight_of_day_0():
    s = nhts_session(_nhts_30022175(), "home_a", 1.0, 0.337)
    events, days = plan_car([s] * 8, [True] + [False] * 7, 7)
    first = events[0]
    assert first["p"] == 0 and first["kind"] == "session"
    row = event_row(first, 7 * 96)
    # 18:30 to 07:00 from the day before: 22 intervals before midnight, 28 after
    assert np.all(row[:28] == 1.0) and not row[28:].any()
    assert abs(days[0]["delivered_kwh"] - 7.0) < 1e-9 and abs(days[0]["needed_kwh"] - 7.0) < 1e-9
    assert first["window"] == list(range(28))
    # day 0 leaves no backlog and has no top-up
    assert [e["p"] for e in events] == [0] and days[-1]["owed_kwh"] < 1e-9
    # at horizon_days 1 the same session wraps onto the same day (the one-day run)
    one_day = nhts_cars("uncontrolled", ["home_a"], pd.DataFrame([dict(_nhts_30022175())]), 0.0,
                        dict(INPUTS, kwh_per_mile=0.337), 1)[0]
    assert np.all(one_day["row"][:28] == 1.0) and np.all(one_day["row"][74:] == 1.0)


def test_a_window_ends_where_the_car_plugs_in_again():
    """A weekday session plugged 18:30 to 07:00 followed by a weekend session that starts
    at 05:00: the weekday window ends at 05:00, and the energy cut off joins the backlog."""
    weekday = nhts_session(_nhts_30022175(), "home_a", 1.0, 0.337)
    weekend = evwatts_session({"session_id": 9, "energy_kwh": 2.0, "charge_h": 1.0, "start_min": 300.0,
                               "plug_min": 120.0}, "home_a")
    events, days = plan_car([weekday, weekday, weekend, weekend], [False, True, True, False], 3)
    assert events[0]["window"] == list(range(74, 96 + 20)) and events[1]["window"] == list(range(116, 124))
    assert abs(days[1]["fit_kwh"] - 10.5) < 1e-9 and abs(days[1]["backlog_kwh"] - (weekday["energy"] - 10.5)) < 1e-9
    rows = sum(event_row(e, 3 * 96) for e in events)
    assert rows.max() <= 2.0 + 1e-12                       # two events of one car never share a step
    assert events[2]["kind"] == "top_up" and events[2]["p"] == 3


def test_nhts_times_after_midnight_land_on_the_next_day():
    """F3: a stay at work parked to 04:00 lands on the next day, as a home window does."""
    d = dict(_nhts_30022175(), work_pieces="1320:360", arrival_min=60, window_min=300)
    work = nhts_work_session(d, "office_a", 7.2, 0.337)
    assert work["offsets"] == list(range(88, 112)) and work["place"] == "work"      # 22:00 to 04:00
    home = nhts_session(d, "home_a", 7.2, 0.337)
    assert home["offsets"][0] == 96 + 4 and home["plug_minute"] == 1500.0           # 01:00 on the next day
    two = nhts_work_session(dict(d, work_pieces="480:240|150:90"), "office_a", 7.2, 0.337)
    assert two["offsets"] == list(range(32, 48)) + list(range(96 + 10, 96 + 16))


def _pools():
    weekday = pd.DataFrame({"session_id": [1, 2, 3, 4], "energy_kwh": [8.0, 12.0, 20.0, 30.0],
                            "charge_h": [2.0, 3.0, 4.0, 5.0], "start_min": [1080.0, 1140.0, 1200.0, 1260.0],
                            "plug_min": [600.0, 660.0, 720.0, 780.0]})
    weekend = pd.DataFrame({"session_id": [101, 102, 103], "energy_kwh": [5.0, 6.0, 7.0],
                            "charge_h": [1.0, 1.5, 2.0], "start_min": [600.0, 720.0, 840.0],
                            "plug_min": [300.0, 300.0, 300.0]})
    office = pd.DataFrame({"session_id": [201, 202], "energy_kwh": [9.0, 11.0], "charge_h": [2.0, 2.0],
                           "start_min": [480.0, 510.0], "plug_min": [240.0, 300.0]})
    return weekday, weekend, office


def test_window_group_weekend_sessions_and_work_cars():
    """Each car keeps one weekday and one weekend session; day X keeps the one-day run's
    draw; a work car charges at its office on weekdays and at home on weekend days."""
    weekday, weekend, office = _pools()
    hosts = [f"home_{k}" for k in range(40)]
    seed, share, work_share = 555, 0.5, 0.25
    cars = evwatts_cars("uncontrolled", hosts, weekday, share, 0.8, INPUTS, seed)
    cars = work_cars("uncontrolled", cars, work_share, ["office_a", "office_b"], INPUTS, seed,
                     "evwatts_sessions", office_pool=office)
    # p = 0 the day before, p = 1 to 7 the window; day X at position 3 (p = 4); days 6 and 7 a weekend
    day_types = ["weekday"] * 6 + ["weekend"] * 2
    out = window_group("uncontrolled", cars, "evwatts_sessions", day_types, 3, INPUTS, seed, 0.8,
                       share={"weekday": share, "weekend": 0.3}, pool={"weekday": weekday, "weekend": weekend},
                       work={"share": work_share, "offices": ["office_a", "office_b"], "office_pool": office},
                       where="South Atlantic")
    assert len(out) == 40
    for k, (c, w) in enumerate(zip(cars, out)):
        # day X is the car's record of the one-day run
        assert w["charges"][4] == c["charges_today"]
        if c["charges_today"]:
            assert w["sessions"]["weekday"]["source_id"] == c["source_id"]
            assert w["sessions"]["weekday"]["energy"] == c["energy_kwh"]
            assert w["sessions"]["weekday"]["place_load"] == c["place_load"]
            assert w["work"] == (c["place"] == "work")
        # weekend days draw weekend sessions, at home
        assert w["sessions"]["weekend"]["source_id"] in ("101", "102", "103")
        assert w["sessions"]["weekend"]["place"] == "home" and w["sessions"]["weekend"]["place_load"] == hosts[k]
        assert w["sessions"]["weekday"]["place"] == ("work" if w["work"] else "home")
        assert w["sessions"]["weekday"]["source_id"] in (("201", "202") if w["work"] else ("1", "2", "3", "4"))
    # the other days: one seeded draw per day, named by its distance from day X
    assert draw_name("charging_uncontrolled", 0) == "charging_uncontrolled"
    assert draw_name("charging_uncontrolled", -4) == "charging_uncontrolled_d-4"
    assert draw_name("charging_uncontrolled", 3) == "charging_uncontrolled_d+3"
    for p in range(8):
        if p == 4:
            continue
        expected = rng(draw_name("charging_uncontrolled", p - 4), seed).random(40) < (0.3 if p >= 6 else share)
        assert [w["charges"][p] for w in out] == list(expected)
    # work cars: those of day X, and the work share of the cars that do not charge on day X
    x_work = [k for k, c in enumerate(cars) if c["place"] == "work"]
    others = [k for k, c in enumerate(cars) if not c["charges_today"]]
    more = [k for k in others if out[k]["work"]]
    assert len(x_work) == 5 and len(others) == 20 and len(more) == 5
    assert sorted(x_work + more) == [k for k, w in enumerate(out) if w["work"]]
    # no work charging on a weekend day: every event of a weekend day is at home
    for k, w in enumerate(out):
        events, days = plan_car([w["sessions"][day_types[p]] for p in range(8)], w["charges"], 7)
        for e in events:
            if day_types[e["p"]] == "weekend":
                assert e["place"] == "home" and e["place_load"] == hosts[k]
            elif w["work"]:
                assert e["place"] == "work" and e["place_load"] in ("office_a", "office_b")
        assert abs(sum(d["needed_kwh"] for d in days) - sum(d["delivered_kwh"] for d in days)
                   - days[-1]["owed_kwh"]) < 1e-9
    # a second call gives the same cars; a wider window keeps the draws of the days it shares
    again = window_group("uncontrolled", cars, "evwatts_sessions", day_types, 3, INPUTS, seed, 0.8,
                         share={"weekday": share, "weekend": 0.3}, pool={"weekday": weekday, "weekend": weekend},
                         work={"share": work_share, "offices": ["office_a", "office_b"], "office_pool": office})
    assert [w["charges"] for w in again] == [w["charges"] for w in out]
    wide = window_group("uncontrolled", cars, "evwatts_sessions", ["weekday"] * 9 + ["weekend"] * 2 + ["weekday"] * 4,
                        6, INPUTS, seed, 0.8, share={"weekday": share, "weekend": 0.3},
                        pool={"weekday": weekday, "weekend": weekend},
                        work={"share": work_share, "offices": ["office_a", "office_b"], "office_pool": office})
    assert [w["charges"][3:11] for w in wide] == [w["charges"] for w in out]
    # every car every day (stress): no draw, weekend sessions on weekend days
    stress_cars = evwatts_cars("uncontrolled", hosts, weekday, 1.0, 0.8, INPUTS, seed)
    stress = window_group("uncontrolled", stress_cars, "evwatts_sessions", day_types, 3, INPUTS, seed, 0.8,
                          share={"weekday": 1.0, "weekend": 1.0}, pool={"weekday": weekday, "weekend": weekend})
    assert all(all(w["charges"]) for w in stress)
    events, days = plan_car([stress[0]["sessions"][day_types[p]] for p in range(8)], stress[0]["charges"], 7)
    assert [e["kind"] for e in events] == ["session"] * 8 and events[6]["source_id"] in ("101", "102", "103")


def test_window_group_nhts_days_repeat_by_day_type():
    row = dict(_nhts_30022175())
    weekday = pd.DataFrame([row, dict(row, HOUSEID="2", day_class="ii", driver_miles=0.0)])
    weekend = pd.DataFrame([dict(row, HOUSEID="7", TRAVDAY="07", arrival_min=900, window_min=600)])
    hosts = [f"home_{k}" for k in range(6)]
    cars = nhts_cars("controlled", hosts, weekday, 1.0, INPUTS, 9)
    day_types = ["weekend", "weekday", "weekday", "weekday", "weekday", "weekday", "weekend", "weekend"]
    out = window_group("controlled", cars, "nhts_days", day_types, 2, INPUTS, 9, 1.0,
                       pool={"weekday": weekday, "weekend": weekend}, where="NC")
    for c, w in zip(cars, out):
        assert w["sessions"]["weekday"]["source_id"] == c["source_id"]
        assert w["sessions"]["weekend"]["source_id"] == "7-1" and not w["work"]
        # the car's vehicle-day repeats on every day of its type
        assert w["charges"] == [True] + [c["charges_today"]] * 5 + [True, True]
    assert any(c["charges_today"] for c in cars) and not all(c["charges_today"] for c in cars)


def test_empty_pools_stop_with_a_fail_line(capsys=None):
    """F2: an empty office pool, and an empty weekend pool, stop with [FAIL] naming the
    pool, the division or state and the day type."""
    weekday, weekend, office = _pools()
    hosts = [f"home_{k}" for k in range(10)]
    cars = evwatts_cars("uncontrolled", hosts, weekday, 0.5, 0.8, INPUTS, 3)
    assert _stops(work_cars, "uncontrolled", cars, 0.5, ["office_a"], INPUTS, 3, "evwatts_sessions",
                  office_pool=office.iloc[0:0], where="South Atlantic")
    if capsys is not None:
        assert "[FAIL] EV draw pool EV WATTS office sessions is empty: no row for South Atlantic, weekday." \
            in capsys.readouterr().out
    day_types = ["weekday"] * 6 + ["weekend"] * 2
    kwargs = dict(share={"weekday": 0.5, "weekend": 0.5}, where="South Atlantic")
    assert _stops(window_group, "uncontrolled", cars, "evwatts_sessions", day_types, 3, INPUTS, 3, 0.8,
                  pool={"weekday": weekday, "weekend": weekend.iloc[0:0]}, **kwargs)
    if capsys is not None:
        assert "[FAIL] EV draw pool EV WATTS residential sessions is empty: no row for South Atlantic, weekend." \
            in capsys.readouterr().out
    nhts = pd.DataFrame([dict(_nhts_30022175())])
    nhts_car = nhts_cars("uncontrolled", ["home_a"], nhts, 1.0, INPUTS, 3)
    assert _stops(window_group, "uncontrolled", nhts_car, "nhts_days", day_types, 3, INPUTS, 3, 1.0,
                  pool={"weekday": nhts, "weekend": nhts.iloc[0:0]}, where="NC")
    if capsys is not None:
        assert "[FAIL] EV draw pool NHTS vehicle-days is empty: no row for NC, weekend." in capsys.readouterr().out


def test_weekend_charging_share_and_inputs():
    pool = pd.DataFrame({
        "evse_id": [1, 1, 2],
        # charger 1: Saturday 6 and Sunday 14 January 2024 (used 2 of 4 weekend days);
        # charger 2: Sunday 7 January (1 of 1)
        "start_date": ["2024-01-06", "2024-01-14", "2024-01-07"],
    })
    assert np.isclose(charging_share(pool, day_type="weekend"), 3.0 / 5.0)
    assert np.isclose(charging_share(pool, [1], day_type="weekend"), 3.0 / 5.0)
    weekdays = pd.DataFrame({"evse_id": [1, 1], "start_date": ["2024-01-01", "2024-01-03"]})
    assert charging_share(weekdays) == charging_share(weekdays, day_type="weekday") == 2.0 / 3.0
    for value_set in ("typical", "stress"):
        files = load_inputs(INPUTS_PATH, value_set)["weekend_files"]
        assert files == {"evwatts_residential": "evwatts_residential_l2_weekend.csv",
                         "nhts": "{state}_nhts2017_vehicle_days_weekend.csv"}
    for state in ("NC", "TX"):
        assert os.path.exists(os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars",
                                           files["nhts"].format(state=state)))


# ---------------------------------------------------------------------------
# Controlled cars (D13)
# ---------------------------------------------------------------------------
def test_forecast_days_draws_each_day():
    model, k = "hour_ahead", {"a": 54.4, "b": 0.91, "c": 1.19}
    z = [rng(draw_name("forecast_feeder", d - 1), 5).standard_normal(24) for d in range(3)]
    curve = np.concatenate([CURVE, 0.5 * CURVE, 2.0 * CURVE])
    fc, err, w, cv = forecast_days(curve, model, k, z)
    assert fc.size == err.size == 288 and len(w) == len(cv) == 3
    for d in range(3):
        one = forecast_curve(curve[d * 96:(d + 1) * 96], model, k, z[d])
        assert np.array_equal(fc[d * 96:(d + 1) * 96], one[0]) and np.array_equal(err[d * 96:(d + 1) * 96], one[1])
        assert (w[d], cv[d]) == (one[2], one[3])
    # one day is forecast_curve, the one-day run
    one = forecast_curve(CURVE, model, k, z[1])
    got = forecast_days(CURVE, model, k, [z[1]])
    assert np.array_equal(got[0], one[0]) and np.array_equal(got[1], one[1])
    assert cv[1] > cv[0] > cv[2]                    # a smaller mean load has a larger relative error


def test_cheap_intervals_reads_the_weekend_row():
    rate = {"energyratestructure": [[{"rate": 0.20}], [{"rate": 0.05}]],
            "energyweekdayschedule": [[0] * 7 + [1] * 2 + [0] * 15] * 12,
            "energyweekendschedule": [[1] * 24] * 6 + [[0] * 20 + [1] * 4] * 6}
    assert cheap_intervals(rate, 7) == cheap_intervals(rate, 7, "weekday") == (1, list(range(28, 36)))
    assert cheap_intervals(rate, 7, "weekend") == (1, list(range(80, 96)))
    assert cheap_intervals(rate, 1, "weekend") == (1, list(range(96)))


# ---------------------------------------------------------------------------
# Storage over a window (D5, D6)
# ---------------------------------------------------------------------------
def _schedule_154fa8d(curve, kw, kwh, start, reserve, eff_charge, eff_discharge, dt):
    """The one-day schedule rule as it stood at commit 154fa8d, on the module's own _plan
    and _energy: the reference the one-day rule is held to."""
    f = np.asarray(curve, dtype=float)
    e0, e_min, e_max = start * kwh, reserve * kwh, kwh
    tol = kwh * 1e-9

    def ok(x):
        dis, chg, l_d, l_c = _plan(f, x, kw, eff_charge, eff_discharge, dt)
        e = _energy(dis, chg, e0, eff_charge, eff_discharge, dt)
        return ((l_c < l_d) and e.min() >= e_min - tol and e.max() <= e_max + tol
                and abs(e[-1] - e0) <= tol)

    lo, hi = 0.0, (1.0 - reserve) * kwh * eff_discharge
    if hi > 0 and ok(hi):
        lo = hi
    elif hi > 0:
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if mid == lo or mid == hi:
                break
            if ok(mid):
                lo = mid
            else:
                hi = mid
    if lo <= 0:
        z = np.zeros(f.size)
        return z, _energy(z, z, e0, eff_charge, eff_discharge, dt), 0.0
    dis, chg, _, _ = _plan(f, lo, kw, eff_charge, eff_discharge, dt)
    return dis - chg, _energy(dis, chg, e0, eff_charge, eff_discharge, dt), lo


def _fixtures():
    """The curves and batteries of test_storage_control.py."""
    falling = np.linspace(2000.0, 500.0, 96)
    late_valley = np.full(96, 800.0)
    late_valley[29:33] = 1500.0
    late_valley[89:96] = 400.0
    return [(CURVE, 150.0, 300.0, 0.2, 0.2), (falling, 100.0, 200.0, 0.2, 0.2),
            (late_valley, 100.0, 200.0, 0.2, 0.2), (late_valley, 100.0, 200.0, 0.5, 0.2),
            (np.full(96, 800.0), 100.0, 200.0, 0.5, 0.2), (CURVE, 150.0, 300.0, 0.6, 0.2)]


def test_schedule_at_one_day_is_the_154fa8d_rule():
    for curve, kw, kwh, start, reserve in _fixtures():
        want = _schedule_154fa8d(curve, kw, kwh, start, reserve, 0.95, 0.95, DT)
        for got in (schedule(curve, kw, kwh, start, reserve, 0.95, 0.95, DT),
                    schedule_days(curve, kw, kwh, start, reserve, 0.95, 0.95, DT)):
            assert np.array_equal(got[0], want[0]) and np.array_equal(got[1], want[1]) and got[2] == want[2]


def test_best_equals_best_window_at_one_day():
    starts = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for curve, kw, kwh, _, reserve in _fixtures():
        a = best_start(curve, kw, kwh, reserve, 0.95, 0.95, DT, starts)
        b = best_window_start(curve, kw, kwh, reserve, 0.95, 0.95, DT, starts)
        assert a[0] == b[0] and a[3] == b[3]
        assert np.array_equal(a[1], b[1]) and np.array_equal(a[2], b[2])


def test_schedule_days_on_three_days():
    """Each day ends at most at the start s, never below the reserve; the next day starts
    where the day before ended; a day that cannot refill ends lower, and the next day
    aims at s again."""
    kw, kwh, start, reserve, eff = 150.0, 300.0, 0.5, 0.2, 0.95
    flat = np.full(96, 1500.0)                       # no valley: the battery cannot refill
    curve = np.concatenate([CURVE, flat, CURVE])
    net, energy, x = schedule_days(curve, kw, kwh, start, reserve, eff, eff, DT)
    assert net.size == 288 and energy.size == 289 and x > 0
    assert np.all(np.abs(net) <= kw + 1e-9)
    assert energy.min() >= reserve * kwh - 1e-6 and energy.max() <= kwh + 1e-6
    ends = [energy[96], energy[192], energy[288]]
    assert all(e <= start * kwh + 1e-6 for e in ends)
    assert abs(energy[0] - start * kwh) < 1e-9 and abs(ends[0] - start * kwh) < 1e-6
    assert abs(ends[1] - reserve * kwh) < 1e-6        # the flat day gives down to the reserve and cannot refill
    assert abs(ends[2] - start * kwh) < 1e-6          # the next day starts at the reserve and refills to s
    # one continuous path: each step moves the stored energy by its own charge or discharge
    dis, chg = np.maximum(net, 0.0), np.maximum(-net, 0.0)
    assert np.allclose(np.diff(energy), (chg * eff - dis / eff) * DT, atol=1e-9)
    # day 3 starts lower than day 1, so it charges more and discharges at the same peak
    assert -net[192:].clip(max=0).sum() > -net[:96].clip(max=0).sum()
    # the battery charges only below the level it discharges above
    for d in range(3):
        day_net, day = net[d * 96:(d + 1) * 96], curve[d * 96:(d + 1) * 96]
        if (day_net > 0).any() and (day_net < 0).any():
            assert day[day_net < 0].max() <= day[day_net > 0].min() + 1e-9


def test_schedule_days_repeats_the_one_day_plan_in_a_deep_valley():
    kw, kwh, start, reserve, eff = 150.0, 300.0, 0.2, 0.2, 0.95
    one = schedule(CURVE, kw, kwh, start, reserve, eff, eff, DT)
    net, energy, x = schedule_days(np.tile(CURVE, 3), kw, kwh, start, reserve, eff, eff, DT)
    assert one[2] > 0 and abs(x - 3 * one[2]) < 1e-6
    for d in range(3):
        assert np.allclose(net[d * 96:(d + 1) * 96], one[0], atol=1e-6)
        assert np.allclose(energy[d * 96:(d + 1) * 96 + 1], one[1], atol=1e-6)
    # best_window on the repeated curve picks the start of the one-day rule
    starts = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    assert best_window_start(np.tile(CURVE, 3), kw, kwh, reserve, eff, eff, DT, starts)[0] == \
        best_start(CURVE, kw, kwh, reserve, eff, eff, DT, starts)[0]


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
