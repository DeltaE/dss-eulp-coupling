# -*- coding: utf-8 -*-
"""
ev_cars.py
----------
The EV cars of the Phase 7 deploy: one car per EV host, each one row of kW over the 96
fifteen-minute intervals of the simulated day (its uncontrolled row), with its charger
level, its plug-in window at home and its source. ev_cars in pipeline_config.yaml picks
the source:

- evwatts_sessions: each car draws one measured weekday home Level 2 charging session
  of the EV WATTS extract (build_evwatts_extract.py) of the donor state's census
  division.
- nhts_days: each car draws one weighted 2017 NHTS weekday vehicle-day of the donor
  state (build_nhts_extract.py).
- session_rows: each charging car charges the daily energy of the Team-Nando check
  curve as one block, started where the fleet is furthest below the curve.

Values come from 7_circuit_instantiation/data_ev_cars/ev_inputs.yaml (load_inputs), the
value set that ev_day in pipeline_config.yaml names (typical or stress).
Intervals are 0 to 95 here and 1 to 96 in output files.

Every random draw has its own generator, seeded by seed(name, effective_seed) from the
mix's ev.effective_seed of scenario_assignments.json and the draw's name.
"""
import math

import numpy as np
import pandas as pd
import yaml

from heating_split import _stable_seed_offset

N_INTERVALS = 96
EVWATTS_EXTRACT_FILE = "evwatts_residential_l2_weekday.csv"
NHTS_EXTRACT_FILE = "{state}_nhts2017_vehicle_days.csv"
EPS = 1e-9


def load_inputs(path, value_set="typical"):
    """Read ev_inputs.yaml and return the values of value_set (typical or stress):
    level2_kw, level1_kw, kwh_per_mile (= kwh_per_gallon_equivalent / mpge_bev),
    charging_share, months, season_months ({season: list of months}),
    check_curve_folder, check_curve_file, census_division ({state: division}),
    forecast_error (the model name), forecast_models ({model: coefficients}) and
    start_spread_min."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    v = {k: raw[k][value_set] for k in raw}
    return {
        "level2_kw": float(v["level2_kw"]),
        "level1_kw": float(v["level1_kw"]),
        "kwh_per_mile": float(v["kwh_per_gallon_equivalent"]) / float(v["mpge_bev"]),
        "charging_share": v["charging_share"],
        "months": v["months"],
        "check_curve_folder": raw["check_curve"]["folder"],
        "check_curve_file": v["check_curve"],
        "census_division": dict(v["census_division"]),
        "season_months": {s: [int(m) for m in ms] for s, ms in v["season_months"].items()},
        "forecast_error": v["forecast_error"],
        "forecast_models": dict(raw["forecast_error"]["models"]),
        "start_spread_min": float(v["start_spread_min"]),
    }


def draw_months(inputs, season):
    """The months the draw pools keep: None (every month) when months is all, else the
    season_months of season. Raises ValueError for a season without months."""
    if inputs["months"] == "all":
        return None
    if season not in inputs["season_months"]:
        raise ValueError(f"No season_months for season {season!r} in ev_inputs.yaml.")
    return inputs["season_months"][season]


def seed(name, effective_seed):
    """The seed of the draw called name: effective_seed + _stable_seed_offset(name)
    (sha256 of name, first 8 bytes big-endian, modulo 10,000,000; heating_split.py).
    The circuits of one feeder share effective_seed, so their mixes share draws."""
    return int(effective_seed) + _stable_seed_offset(name)


def rng(name, effective_seed):
    """A numpy Generator of its own for the draw called name."""
    return np.random.default_rng(seed(name, effective_seed))


def pick(n, share, generator):
    """Boolean array of n cars, True for floor(share x n + 0.5) cars at the positions
    generator.permutation(n)[:count]."""
    out = np.zeros(n, dtype=bool)
    count = int(math.floor(share * n + 0.5))
    out[generator.permutation(n)[:count]] = True
    return out


def plug_window(t, m):
    """The window of a car plugged in at clock minute t (0 to 1440) for m minutes:
    (a, n_w) with a = floor(t / 15) and n_w = min(96, max(1, ceil((t + m) / 15) - a)).
    The ceiling ignores 1e-9 of rounding so an end on an interval boundary does not
    open the next interval.

    ASSUMPTION: a car can charge in every 15-minute interval it is plugged in for any
    part of; this overstates the time available by at most 15 minutes at each end of a
    session.
    ASSUMPTION: a window that runs past midnight wraps onto the first intervals of the
    same simulated day, because the run covers one day; the car's morning charging then
    falls on the same day's early intervals instead of the next day's."""
    a = int(math.floor(t / 15.0))
    n_w = min(N_INTERVALS, max(1, int(math.ceil((t + m) / 15.0 - EPS)) - a))
    return a, n_w


def window_intervals(a, n_w):
    """The intervals a, a+1, ... (modulo 96) of a window of n_w intervals, in plug
    order."""
    return [(a + k) % N_INTERVALS for k in range(n_w)]


def charge_shape(a, p, e_kwh, n_w):
    """96 kW values of one car that charges e_kwh at power p (kW) from interval a in a
    window of n_w intervals. E = 4 x e_kwh kW-intervals; n_full = floor(E / p + 1e-9);
    rem = E - n_full x p (0 below 1e-9). The first min(n_full, n_w) intervals of the
    window get p; if n_full < n_w and rem > 0, interval (a + n_full) mod 96 gets rem.
    Delivered kWh = sum / 4; the rest of e_kwh is left over."""
    out = np.zeros(N_INTERVALS)
    if e_kwh <= 0 or p <= 0:
        return out
    energy = 4.0 * e_kwh
    n_full = int(math.floor(energy / p + EPS))
    rem = energy - n_full * p
    if rem < EPS:
        rem = 0.0
    n_w = min(int(n_w), N_INTERVALS)
    for k in range(min(n_full, n_w)):
        out[(a + k) % N_INTERVALS] = p
    if n_full < n_w and rem > 0:
        out[(a + n_full) % N_INTERVALS] = rem
    return out


def read_evwatts_pool(extract_dir, division, months=None):
    """The EV WATTS draw pool: rows of the extract in extract_dir whose division is
    division and, when months is given, whose month is in months (every month when
    None), in the extract's order (session_id)."""
    ex = pd.read_csv(f"{extract_dir}/{EVWATTS_EXTRACT_FILE}",
                     dtype={"session_id": "int64", "evse_id": "int64", "division": str, "venue": str,
                            "start_date": str})
    keep = ex["division"] == division
    if months is not None:
        keep &= ex["month"].isin([int(m) for m in months])
    return ex[keep].reset_index(drop=True)


def charging_share(pool, months=None):
    """Share of cars charging on a weekday, from the EV WATTS pool. For each EVSE: used
    weekdays = its distinct start_dates; in-service weekdays = the Monday to Friday
    dates from its first to its last start_date, inclusive, and, when months is given,
    in months only (the months of the pool). Returns sum of used / sum of in-service
    over all EVSE.

    ASSUMPTION: each residential charger serves one car and is in service on every
    weekday between its first and last recorded session; s is the share of those
    weekdays with a session."""
    g = pool.groupby("evse_id")["start_date"]
    used = g.nunique()
    first = pd.to_datetime(g.min()).values.astype("datetime64[D]")
    last = pd.to_datetime(g.max()).values.astype("datetime64[D]")
    if months is None:
        in_service = np.busday_count(first, last + np.timedelta64(1, "D"))
    else:
        days = np.arange(first.min(), last.max() + np.timedelta64(1, "D"))
        keep = np.is_busday(days) & np.isin(pd.DatetimeIndex(days).month, [int(m) for m in months])
        cum = np.concatenate([[0], np.cumsum(keep)])
        in_service = cum[(last - days[0]).astype(int) + 1] - cum[(first - days[0]).astype(int)]
    return float(used.sum()) / float(in_service.sum())


def read_nhts_pool(path, months=None, classes=("i", "ii")):
    """The NHTS draw pool: vehicle-days of the state's extract whose class is in classes
    (class (i) or (ii) by default) and, when months is given, whose TDAYDATE month
    (YYYYMM) is in months, sorted by HOUSEID and VEHID.

    ASSUMPTION: vehicle-days that drive but neither end nor start at home are left out
    of the draw; they are about 6 percent of weekday vehicle-days in NC and TX (913 of
    14,623 in NC and 2,498 of 38,816 in TX, 6.2 and 6.4 percent). Class (iv) days, with a
    driver trip faster than nhts_max_trip_speed_mph of ev_inputs.yaml, are never drawn
    (105 in NC and 215 in TX, 0.7 and 0.6 percent)."""
    days = pd.read_csv(path, dtype={"HOUSEID": str, "TDAYDATE": str, "TRAVDAY": str, "day_class": str})
    days = days[days["day_class"].isin(list(classes))]
    if months is not None:
        days = days[days["TDAYDATE"].str[4:6].astype(int).isin([int(m) for m in months])]
    return days.sort_values(["HOUSEID", "VEHID"], kind="mergesort").reset_index(drop=True)


def draw_nhts(pool, n, generator):
    """n row positions of pool, drawn with replacement in proportion to WTHHFIN."""
    w = pool["WTHHFIN"].to_numpy(dtype=float)
    return generator.choice(len(pool), size=n, replace=True, p=w / w.sum())


def nhts_window(day):
    """(plug-in interval a or None, window intervals) of one NHTS vehicle-day: class (i)
    from arrival_min and window_min (plug_window); class (ii) the whole day."""
    if day["day_class"] == "i":
        a, n_w = plug_window(float(day["arrival_min"]), float(day["window_min"]))
        return a, window_intervals(a, n_w)
    return None, list(range(N_INTERVALS))


def _car(group, k, host, source, level, power, charges, row, energy, window=None, plug=None,
         source_id="", day_class="", window_source_id="", share=None, start=None, plug_minute=None):
    """One car record: the columns of ev_cars.csv plus row (uncontrolled kW), window
    (list of intervals or None) and plug_minute (the clock minute of a charging car's
    plug-in, or None)."""
    delivered = row.sum() / 4.0
    return {
        "car": f"{'EVu' if group == 'uncontrolled' else 'EVc'}_{k}", "host": host, "group": group,
        "ev_cars": source, "level": "L2" if level else "L1", "power_kw": power,
        "charges_today": bool(charges), "source_id": source_id, "day_class": day_class,
        "window_source_id": window_source_id,
        "plug_in_interval": plug + 1 if plug is not None else None,
        "window_intervals": len(window) if window is not None else None,
        "energy_kwh": energy,
        "first_interval": start + 1 if (start is not None and row.any()) else None,
        "n_intervals": int(np.count_nonzero(row)),
        "delivered_kwh": delivered, "leftover_kwh": energy - delivered,
        "charging_share": share, "row": row, "window": window, "plug_minute": plug_minute,
    }


def evwatts_cars(group, hosts, pool, share, l2_share, inputs, effective_seed):
    """ev_cars evwatts_sessions, one group. Level: pick(level_<group>); charging today:
    pick(charging_<group>) with the measured share; every car draws one pool row,
    idx = rng(evwatts_<group>).integers(0, len(pool), size=N). A charging car plugs in
    at start_min for plug_min minutes and charges energy_kwh: Level 2 at the session's
    mean power energy_kwh / charge_h, Level 1 at level1_kw. A car that does not charge
    has an all-zero row and no window.

    ASSUMPTION: EV WATTS timestamps are the local clock time of the charger; the
    database gives no time zone, and a shift of one hour would move every plug-in time
    by four intervals."""
    n = len(hosts)
    is_l2 = pick(n, l2_share, rng(f"level_{group}", effective_seed))
    charges = pick(n, share, rng(f"charging_{group}", effective_seed))
    idx = rng(f"evwatts_{group}", effective_seed).integers(0, len(pool), size=n)
    cars = []
    for k, host in enumerate(hosts):
        if not charges[k]:
            power = inputs["level2_kw"] if is_l2[k] else inputs["level1_kw"]
            cars.append(_car(group, k, host, "evwatts_sessions", is_l2[k], power, False,
                             np.zeros(N_INTERVALS), 0.0, share=share))
            continue
        s = pool.iloc[int(idx[k])]
        e = float(s["energy_kwh"])
        power = e / float(s["charge_h"]) if is_l2[k] else inputs["level1_kw"]
        a, n_w = plug_window(float(s["start_min"]), float(s["plug_min"]))
        row = charge_shape(a, power, e, n_w)
        cars.append(_car(group, k, host, "evwatts_sessions", is_l2[k], power, True, row, e,
                         window=window_intervals(a, n_w), plug=a, source_id=str(int(s["session_id"])),
                         share=share, start=a, plug_minute=float(s["start_min"])))
    return cars


def nhts_cars(group, hosts, pool, l2_share, inputs, effective_seed):
    """ev_cars nhts_days, one group. Level: pick(level_<group>); each car draws one
    vehicle-day (draw_nhts with rng(nhts_<group>)). Class (i): plugs in at arrival_min
    for window_min minutes and charges driver_miles x kwh_per_mile at its level's power.
    Class (ii): all-zero row, window the whole day."""
    n = len(hosts)
    is_l2 = pick(n, l2_share, rng(f"level_{group}", effective_seed))
    idx = draw_nhts(pool, n, rng(f"nhts_{group}", effective_seed))
    cars = []
    for k, host in enumerate(hosts):
        d = pool.iloc[int(idx[k])]
        power = inputs["level2_kw"] if is_l2[k] else inputs["level1_kw"]
        a, window = nhts_window(d)
        sid = f"{d['HOUSEID']}-{int(d['VEHID'])}"
        if d["day_class"] == "i":
            e = float(d["driver_miles"]) * inputs["kwh_per_mile"]
            row = charge_shape(a, power, e, len(window))
            cars.append(_car(group, k, host, "nhts_days", is_l2[k], power, True, row, e, window=window,
                             plug=a, source_id=sid, day_class="i", start=a,
                             plug_minute=float(d["arrival_min"])))
        else:
            cars.append(_car(group, k, host, "nhts_days", is_l2[k], power, False, np.zeros(N_INTERVALS),
                             0.0, window=window, source_id=sid, day_class=d["day_class"]))
    return cars


def session_rows_cars(group, hosts, curve, share, l2_share, inputs, effective_seed, window_pool=None):
    """ev_cars session_rows (the repaired 2024 generator), one group.

    curve: the 96 kW means c of the check curve; E = sum(c) / 4 kWh per charging car.
    Level: pick(level_<group>); charging today: pick(charging_<group>), n_ch cars.
    Target F = n_ch x c; R = F. For each charging car in host order: for every start s,
    block_s = charge_shape(s, level2_kw, E, 96) and w[s] = sum of max(R, 0) over the
    intervals of block_s (w = 1 everywhere if all are 0); s is drawn with
    rng(session_rows_<group>).choice(96, p=w / sum(w)); R = R - block_s. A Level 2 car's
    row is block_s, a Level 1 car's charge_shape(s, level1_kw, E, 96). Uncontrolled cars
    have no window. With window_pool (controlled cars), each car takes the window of one
    NHTS vehicle-day drawn as nhts_days with rng(nhts_windows_controlled).

    ASSUMPTION: each charging car charges the curve's daily energy per plugged-in EV as
    one block at Level 2 power, starting where the fleet is furthest below the
    Team-Nando curve, drawn at random in proportion to that shortfall; fleet energy
    equals the curve's."""
    n = len(hosts)
    c = np.asarray(curve, dtype=float)
    e = c.sum() / 4.0
    is_l2 = pick(n, l2_share, rng(f"level_{group}", effective_seed))
    charges = pick(n, share, rng(f"charging_{group}", effective_seed))
    blocks = np.array([charge_shape(s, inputs["level2_kw"], e, N_INTERVALS) for s in range(N_INTERVALS)])
    mask = blocks > 0
    resid = int(charges.sum()) * c
    gen = rng(f"session_rows_{group}", effective_seed)
    windows = [None] * n
    if window_pool is not None:
        widx = draw_nhts(window_pool, n, rng("nhts_windows_controlled", effective_seed))
        windows = [window_pool.iloc[int(i)] for i in widx]
    cars = []
    for k, host in enumerate(hosts):
        power = inputs["level2_kw"] if is_l2[k] else inputs["level1_kw"]
        plug, window, wsid, minute = None, None, "", None
        if windows[k] is not None:
            plug, window = nhts_window(windows[k])
            wsid = f"{windows[k]['HOUSEID']}-{int(windows[k]['VEHID'])}"
            if windows[k]["day_class"] == "i":
                minute = float(windows[k]["arrival_min"])
        if not charges[k]:
            cars.append(_car(group, k, host, "session_rows", is_l2[k], power, False, np.zeros(N_INTERVALS),
                             0.0, window=window, plug=plug, window_source_id=wsid, share=share))
            continue
        w = mask @ np.maximum(resid, 0.0)
        if w.sum() == 0:
            w = np.ones(N_INTERVALS)
        s = int(gen.choice(N_INTERVALS, p=w / w.sum()))
        resid = resid - blocks[s]
        row = blocks[s].copy() if is_l2[k] else charge_shape(s, inputs["level1_kw"], e, N_INTERVALS)
        cars.append(_car(group, k, host, "session_rows", is_l2[k], power, True, row, e, window=window,
                         plug=plug, window_source_id=wsid, share=share, start=s, plug_minute=minute))
    return cars


def cars_frame(cars):
    """The ev_cars.csv table of a list of car records (row, window and plug_minute left
    out)."""
    df = pd.DataFrame([{k: v for k, v in c.items() if k not in ("row", "window", "plug_minute")} for c in cars])
    for col in ("plug_in_interval", "window_intervals", "first_interval"):
        df[col] = df[col].astype("Int64")
    return df
