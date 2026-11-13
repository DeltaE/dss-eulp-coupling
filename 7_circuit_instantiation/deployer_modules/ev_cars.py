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

Under evwatts_sessions and nhts_days, work_cars moves a share (work_share of
ev_inputs.yaml, the case ev_work_share_case of pipeline_config.yaml) of each group's
charging cars to a workplace: a commercial load of the same circuit, where the car
charges its whole day's energy with a Business Office session of the EV WATTS office
extract or an NHTS weekday with a stop at work. session_rows keeps every car at home:
the work share is not applied under that source.

Values come from 7_circuit_instantiation/data_ev_cars/ev_inputs.yaml (load_inputs), the
value set that ev_day in pipeline_config.yaml names (typical or stress).
Intervals are 0 to 95 here and 1 to 96 in output files.

Every random draw has its own generator, seeded by seed(name, effective_seed) from the
mix's ev.effective_seed of scenario_assignments.json and the draw's name.

With horizon_days above 1 in pipeline_config.yaml the cars charge over a window of days
(the last part of this module): window_group gives each car one session for weekdays
and one for weekend days and a seeded draw of its charging days, and plan_car puts its
sessions and top-ups on the window's own timeline, where charging past midnight lands
on the next day. The car records of day X stay those of the one-day run.
"""
import math
import re
import sys

import numpy as np
import pandas as pd
import yaml

from heating_split import _stable_seed_offset

N_INTERVALS = 96
EVWATTS_EXTRACT_FILE = "evwatts_residential_l2_weekday.csv"
EVWATTS_OFFICE_EXTRACT_FILE = "evwatts_office_l2_weekday.csv"
NHTS_EXTRACT_FILE = "{state}_nhts2017_vehicle_days.csv"
EPS = 1e-9


def load_inputs(path, value_set="typical"):
    """Read ev_inputs.yaml and return the values of value_set (typical or stress):
    level2_kw, level1_kw, kwh_per_mile (= kwh_per_gallon_equivalent / mpge_bev),
    charging_share, months, season_months ({season: list of months}),
    check_curve_folder, check_curve_file, census_division ({state: division}),
    forecast_error (the model name), forecast_models ({model: coefficients}),
    start_spread_min, work_share ({low, moderate, high: share of the charging cars
    that charge at a workplace}) and weekend_files ({evwatts_residential, nhts: the
    weekend extract file names})."""
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
        "work_share": {k: float(s) for k, s in v["work_share"].items()},
        "weekend_files": dict(v["weekend_files"]),
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


def charge_window(window, p, e_kwh):
    """96 kW values of one car that charges e_kwh at power p (kW) through the intervals
    of window (a list, in plug order; its pieces need not be contiguous). E = 4 x e_kwh
    kW-intervals; n_full = floor(E / p + 1e-9); rem = E - n_full x p (0 below 1e-9). The
    first min(n_full, len(window)) intervals of the list get p; if n_full < len(window)
    and rem > 0, interval window[n_full] gets rem. For a window of window_intervals(a,
    n_w) this equals charge_shape(a, p, e_kwh, n_w)."""
    out = np.zeros(N_INTERVALS)
    if e_kwh <= 0 or p <= 0:
        return out
    energy = 4.0 * e_kwh
    n_full = int(math.floor(energy / p + EPS))
    rem = energy - n_full * p
    if rem < EPS:
        rem = 0.0
    for k in range(min(n_full, len(window))):
        out[window[k]] = p
    if n_full < len(window) and rem > 0:
        out[window[n_full]] = rem
    return out


def work_window(pieces):
    """The window of a work_pieces text of the NHTS extract (arrival:minutes pieces joined
    by |): for each piece in order, window_intervals(*plug_window(arrival, minutes)),
    joined, an interval already in the window not repeated. Returns (first plug-in
    interval, window, first arrival minute). The ASSUMPTIONs of plug_window apply to
    each piece."""
    window, first_a, first_minute = [], None, None
    for piece in str(pieces).split("|"):
        arrival, minutes = (float(x) for x in piece.split(":"))
        a, n_w = plug_window(arrival, minutes)
        if first_a is None:
            first_a, first_minute = a, arrival
        for i in window_intervals(a, n_w):
            if i not in window:
                window.append(i)
    return first_a, window, first_minute


def read_bus_coords(path):
    """{bus name in lower case: (longitude, latitude)} from a Buscoords.dss file, fields
    split on commas or spaces; lines that do not parse are skipped."""
    coords = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            fields = re.split(r"[,\s]+", line.strip())
            if len(fields) < 3:
                continue
            try:
                coords[fields[0].lower()] = (float(fields[1]), float(fields[2]))
            except ValueError:
                continue
    return coords


def read_evwatts_pool(extract_dir, division, months=None, file=EVWATTS_EXTRACT_FILE):
    """The EV WATTS draw pool: rows of the extract file in extract_dir (the residential
    extract by default) whose division is division and, when months is given, whose
    month is in months (every month when None), in the extract's order (session_id)."""
    ex = pd.read_csv(f"{extract_dir}/{file}",
                     dtype={"session_id": "int64", "evse_id": "int64", "division": str, "venue": str,
                            "start_date": str})
    keep = ex["division"] == division
    if months is not None:
        keep &= ex["month"].isin([int(m) for m in months])
    return ex[keep].reset_index(drop=True)


WEEKMASKS = {"weekday": "1111100", "weekend": "0000011"}  # Monday to Sunday, numpy busday weekmask


def charging_share(pool, months=None, day_type="weekday"):
    """Share of cars charging on a weekday, from the EV WATTS pool. For each EVSE: used
    weekdays = its distinct start_dates; in-service weekdays = the Monday to Friday
    dates from its first to its last start_date, inclusive, and, when months is given,
    in months only (the months of the pool). Returns sum of used / sum of in-service
    over all EVSE. With day_type weekend, the same on the weekend pool: used and
    in-service Saturdays and Sundays.

    ASSUMPTION: each residential charger serves one car and is in service on every
    weekday between its first and last recorded session; s is the share of those
    weekdays with a session."""
    weekmask = WEEKMASKS[day_type]
    g = pool.groupby("evse_id")["start_date"]
    used = g.nunique()
    first = pd.to_datetime(g.min()).values.astype("datetime64[D]")
    last = pd.to_datetime(g.max()).values.astype("datetime64[D]")
    if months is None:
        in_service = np.busday_count(first, last + np.timedelta64(1, "D"), weekmask=weekmask)
    else:
        days = np.arange(first.min(), last.max() + np.timedelta64(1, "D"))
        keep = np.is_busday(days, weekmask=weekmask) & np.isin(pd.DatetimeIndex(days).month, [int(m) for m in months])
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
         source_id="", day_class="", window_source_id="", share=None, start=None, plug_minute=None,
         place="home", place_load=None):
    """One car record: the columns of ev_cars.csv plus row (uncontrolled kW), window
    (list of intervals or None) and plug_minute (the clock minute of a charging car's
    plug-in, or None). place is home or work; place_load the load base whose bus carries
    the car's EV loads (the host when None is given)."""
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
        "place": place, "place_load": place_load if place_load is not None else host,
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


def fail_empty_pool(pool, name, where, day_type):
    """Stop with one [FAIL] line when a draw pool holds no row: name is the pool, where
    its census division or state, day_type weekday or weekend."""
    if len(pool) == 0:
        print(f"[FAIL] EV draw pool {name} is empty: no row for {where}, {day_type}.")
        sys.exit(1)


def work_cars(group, cars, share, offices, inputs, effective_seed, source, office_pool=None,
              work_day_pool=None, where=""):
    """The group's car list with its work cars replaced. The charging cars of the group
    are those with charges_today, in host order; chosen = pick(n_charging, share,
    rng(work_<group>)) over them. With share 0, or no charging car, cars is returned
    unchanged and nothing is drawn. Each chosen car draws an office, offices[i] for i
    from rng(office_<group>).integers(0, len(offices), size=n_chosen), in host order;
    offices is the sorted list of the circuit's commercial load bases, drawn with
    replacement, so several cars can share one office. Under evwatts_sessions each
    chosen car draws one row of office_pool with rng(evwatts_work_<group>).integers(0,
    len(office_pool), size=n_chosen): it plugs in at start_min for plug_min minutes
    (plug_window) and charges energy_kwh at the session's mean power energy_kwh /
    charge_h (charge_shape); level L2; source_id the session_id. Under nhts_days each
    chosen car draws one row of work_day_pool with draw_nhts(work_day_pool, n_chosen,
    rng(nhts_work_<group>)): its window is work_window(work_pieces), its energy
    driver_miles x kwh_per_mile, its power level2_kw, its row charge_window; level L2;
    day_class i; source_id HOUSEID-VEHID; plug_minute its first arrival at work. The
    replaced record keeps its car name, host, group and charging_share, with place work
    and place_load the office. Under session_rows the work share is not applied. An
    empty office_pool or work_day_pool stops with [FAIL] (fail_empty_pool; where names
    the census division or state of the pool).

    ASSUMPTION: each car charges at one place on the simulated weekday, so a work car
    charges its whole day's energy at work and nothing at home; a car that charged at
    both would split its energy, with less in the evening at home.
    ASSUMPTION: a work car charges at a commercial load of its own circuit, drawn at
    random with replacement, and cars leaving the feeder for work are taken to balance
    cars arriving from other feeders; a circuit with few commercial loads puts several
    cars on one office.
    ASSUMPTION: under evwatts_sessions a work car's energy and times are one Business
    Office session, one plug-in at a shared charger (median plugged 256 min in the South
    Atlantic against a median 510 min parked at work in NHTS), so a car's whole stay is
    not covered; a longer session would spread the same energy over more intervals.
    ASSUMPTION: under nhts_days a work charger delivers level2_kw (7.2 kW), while
    Business Office sessions in EV WATTS have median mean powers of 5.26 kW (South
    Atlantic) and 5.65 kW (West South Central), so a lower charger power would lengthen
    work charging. EV WATTS: https://doi.org/10.15483/1970735; NHTS:
    https://nhts.ornl.gov/assets/2016/download/Csv.zip."""
    charging = [k for k, c in enumerate(cars) if c["charges_today"]]
    if share <= 0 or not charging or source == "session_rows":
        return cars
    chosen = pick(len(charging), share, rng(f"work_{group}", effective_seed))
    chosen = [k for k, c in zip(charging, chosen) if c]
    n_chosen = len(chosen)
    office_idx = rng(f"office_{group}", effective_seed).integers(0, len(offices), size=n_chosen)
    if source == "evwatts_sessions":
        fail_empty_pool(office_pool, "EV WATTS office sessions", where, "weekday")
        idx = rng(f"evwatts_work_{group}", effective_seed).integers(0, len(office_pool), size=n_chosen)
    else:
        fail_empty_pool(work_day_pool, "NHTS vehicle-days with a work stop", where, "weekday")
        idx = draw_nhts(work_day_pool, n_chosen, rng(f"nhts_work_{group}", effective_seed))
    out = list(cars)
    for j, k in enumerate(chosen):
        car = cars[k]
        office = offices[int(office_idx[j])]
        if source == "evwatts_sessions":
            s = office_pool.iloc[int(idx[j])]
            e = float(s["energy_kwh"])
            power = e / float(s["charge_h"])
            a, n_w = plug_window(float(s["start_min"]), float(s["plug_min"]))
            out[k] = _car(group, k, car["host"], source, True, power, True, charge_shape(a, power, e, n_w), e,
                          window=window_intervals(a, n_w), plug=a, source_id=str(int(s["session_id"])),
                          share=car["charging_share"], start=a, plug_minute=float(s["start_min"]),
                          place="work", place_load=office)
        else:
            d = work_day_pool.iloc[int(idx[j])]
            a, window, minute = work_window(d["work_pieces"])
            e = float(d["driver_miles"]) * inputs["kwh_per_mile"]
            power = inputs["level2_kw"]
            out[k] = _car(group, k, car["host"], source, True, power, True, charge_window(window, power, e), e,
                          window=window, plug=a, source_id=f"{d['HOUSEID']}-{int(d['VEHID'])}", day_class="i",
                          share=car["charging_share"], start=a, plug_minute=minute,
                          place="work", place_load=office)
    return out


def cars_frame(cars):
    """The ev_cars.csv table of a list of car records (row, window and plug_minute left
    out); place and place_load are its last two columns."""
    df = pd.DataFrame([{k: v for k, v in c.items() if k not in ("row", "window", "plug_minute")} for c in cars])
    for col in ("plug_in_interval", "window_intervals", "first_interval"):
        df[col] = df[col].astype("Int64")
    return df


# ---------------------------------------------------------------------------
# A window of more than one day (horizon_days in pipeline_config.yaml above 1)
# ---------------------------------------------------------------------------
# Days are counted p = 0, 1, ..., n_days: p = 0 is the day before the window and p = 1
# its first day. Step t of the window's timeline is interval t - 96 x (p - 1) of day p,
# so the window covers t = 0 to 96 x n_days - 1 and day 0 covers t = -96 to -1.
# A session is a dict (_session): place (home or work), place_load, power (kW), energy
# (kWh), charges (False for an NHTS day without a trip), offsets (the plug-in window as
# intervals counted from 00:00 of its day, in plug order and not wrapped, so 96 and
# above fall on the next day; None for a car without a window), row_offsets (the
# intervals its uncontrolled charging runs through, the window unless stated),
# plug_minute (minutes from 00:00 of its day, or None), source_id and day_class.

DAY_START_MIN = 240  # the NHTS travel day runs from 04:00 (build_nhts_extract.py rule 3)


def draw_name(name, offset):
    """The name of a draw made for one day of the window: name itself on day X (offset
    0), the name of the one-day run, else name_d<offset>, the days from day X with their
    sign (charging_controlled_d-3, charging_controlled_d+2). A day keeps its draws when
    the window grows, and a new draw never moves an existing one."""
    return name if offset == 0 else f"{name}_d{offset:+d}"


def _session(place, place_load, power, energy, offsets, plug_minute, charges=True, source_id="",
             day_class="", row_offsets=None):
    return {"place": place, "place_load": place_load, "power": float(power), "energy": float(energy),
            "charges": bool(charges), "offsets": offsets,
            "row_offsets": offsets if row_offsets is None else row_offsets,
            "plug_minute": plug_minute, "source_id": source_id, "day_class": day_class}


def evwatts_session(s, place_load, level1_kw=None, place="home"):
    """The session of one EV WATTS extract row s: energy_kwh at the session's mean power
    energy_kwh / charge_h (at level1_kw when given, a Level 1 car), plugged in at
    start_min for plug_min minutes (plug_window), the window not wrapped."""
    energy = float(s["energy_kwh"])
    power = energy / float(s["charge_h"]) if level1_kw is None else level1_kw
    a, n_w = plug_window(float(s["start_min"]), float(s["plug_min"]))
    return _session(place, place_load, power, energy, [a + k for k in range(n_w)], float(s["start_min"]),
                    source_id=str(int(s["session_id"])))


def _travel_minute(t):
    """Clock minute t of an NHTS travel day as minutes from 00:00 of its calendar day: a
    time before 04:00 (DAY_START_MIN) lies after midnight, on the next calendar day."""
    return float(t) + 1440.0 if float(t) < DAY_START_MIN else float(t)


def nhts_session(d, host, power, kwh_per_mile):
    """The session of one NHTS vehicle-day d at home. Class (i): driver_miles x
    kwh_per_mile at power, plugged in at arrival_min for window_min minutes
    (plug_window), the window not wrapped and an arrival before 04:00 on the next
    calendar day (_travel_minute). Class (ii): no session (charges False) and the whole
    day as its window."""
    sid = f"{d['HOUSEID']}-{int(d['VEHID'])}"
    if d["day_class"] != "i":
        return _session("home", host, power, 0.0, list(range(N_INTERVALS)), None, charges=False,
                        source_id=sid, day_class=d["day_class"])
    minute = _travel_minute(d["arrival_min"])
    a, n_w = plug_window(minute, float(d["window_min"]))
    return _session("home", host, power, float(d["driver_miles"]) * kwh_per_mile,
                    [a + k for k in range(n_w)], minute, source_id=sid, day_class="i")


def nhts_work_session(d, office, power, kwh_per_mile):
    """The session of one NHTS vehicle-day d at work: driver_miles x kwh_per_mile at
    power through the pieces of work_pieces (arrival:minutes joined by |), each piece
    plug_window(arrival, minutes) not wrapped, an arrival before 04:00 on the next
    calendar day, an interval already in the window not repeated. A stay parked to
    04:00 so lands on the next day."""
    offsets, first_minute = [], None
    for piece in str(d["work_pieces"]).split("|"):
        arrival, minutes = (float(x) for x in piece.split(":"))
        minute = _travel_minute(arrival)
        if first_minute is None:
            first_minute = minute
        a, n_w = plug_window(minute, minutes)
        for k in range(n_w):
            if a + k not in offsets:
                offsets.append(a + k)
    return _session("work", office, power, float(d["driver_miles"]) * kwh_per_mile, offsets, first_minute,
                    source_id=f"{d['HOUSEID']}-{int(d['VEHID'])}", day_class="i")


def window_group(group, cars, source, day_types, x, inputs, effective_seed, l2_share, share=None,
                 pool=None, work=None, curve=None, where=""):
    """The cars of one group over a window: for each car of cars (the group's records of
    day X, in host order) its session of each day type and its charging days.

    day_types[p] is weekday or weekend for p = 0 (the day before the window) to n_days;
    day X is p = x + 1 and its type is weekday, the type of the one-day run's draw,
    whatever its date. Returns one dict per car: sessions {weekday, weekend}, charges
    (one bool per p) and work (True for a car that charges at a workplace on weekdays).

    Level: pick(level_<group>), the draw of the one-day run.
    evwatts_sessions (pool {weekday, weekend}: the residential draw pools; share
    {weekday, weekend}: the share of cars charging on a day of that type):
    - weekday session: the pool row of rng(evwatts_<group>), the one-day run's draw, for
      every car; weekend session: the weekend pool row of rng(evwatts_weekend_<group>).
    - charging days: day X as the one-day run (charges_today); any other day, for every
      car, rng(charging_<group>_d<offset>).random() below the share of the day's type
      (every car when the share is 1).
    - work cars (work = {share, offices, office_pool}): the work cars of day X keep
      their office and Business Office session. Among the cars that do not charge on
      day X, pick(work_<group>_others) with the same share chooses more, each with an
      office from rng(office_<group>_others) and a session from
      rng(evwatts_work_<group>_others), so that on every weekday the work share of the
      charging cars charges at a workplace. A work car charges at its office on
      weekdays and at home, with its weekend session, on weekend days.
    nhts_days (pool {weekday, weekend}: the NHTS draw pools; work = {work_day_pool}):
    - weekday vehicle-day: draw_nhts with rng(nhts_<group>), the one-day run's draw;
      weekend vehicle-day: draw_nhts on the weekend pool with rng(nhts_weekend_<group>).
      A car charges on every day whose vehicle-day is class (i). The work cars of day X
      keep their work vehicle-day on weekdays.
    session_rows (curve: the check curve; share as evwatts_sessions): one block for
    every day, weekday or weekend, because the check curve has no weekend file. The
    cars that charge on day X keep their start; the others draw theirs as
    session_rows_cars does, with rng(session_rows_<group>_others) on a target of
    (number of those cars) x curve. Controlled cars keep their NHTS window. Charging
    days as evwatts_sessions.
    An empty pool stops with [FAIL] (fail_empty_pool; where names the census division
    or state).

    ASSUMPTION: over a horizon of more than one day each car keeps its one drawn
    session and charger, and on every day other than the simulated peak day it charges
    with probability equal to the measured share of days of that type (weekdays, or
    Saturdays and Sundays) with a session at home chargers of its census division,
    drawn independently each day. Real drivers keep habits such as fixed charging days,
    so drawn days spread more evenly than real ones, while the expected sessions per
    car and the fleet energy per day equal the measured values (charging_share in
    ev_inputs.yaml).
    ASSUMPTION: workplace charging happens on weekdays only (weekend_files in
    ev_inputs.yaml)."""
    n = len(cars)
    n_p = len(day_types)
    is_l2 = pick(n, l2_share, rng(f"level_{group}", effective_seed))
    hosts = [c["host"] for c in cars]
    x_charges = [bool(c["charges_today"]) for c in cars]
    out = [{"sessions": {}, "charges": [False] * n_p, "work": False} for _ in range(n)]

    def drawn_days(k_out):
        for p in range(n_p):
            offset = p - 1 - x
            if offset == 0:
                flags = x_charges
            elif share[day_types[p]] >= 1.0:
                flags = [True] * n
            else:
                flags = rng(draw_name(f"charging_{group}", offset), effective_seed).random(n) < share[day_types[p]]
            for k in range(n):
                k_out[k]["charges"][p] = bool(flags[k])

    if source == "evwatts_sessions":
        for day_type in ("weekday", "weekend"):
            fail_empty_pool(pool[day_type], "EV WATTS residential sessions", where, day_type)
        idx = {"weekday": rng(f"evwatts_{group}", effective_seed).integers(0, len(pool["weekday"]), size=n),
               "weekend": rng(f"evwatts_weekend_{group}", effective_seed).integers(0, len(pool["weekend"]), size=n)}
        office_of = {}
        if work is not None:
            office_pool = work["office_pool"]
            fail_empty_pool(office_pool, "EV WATTS office sessions", where, "weekday")
            by_id = {int(s): i for i, s in enumerate(office_pool["session_id"])}
            for k, c in enumerate(cars):
                if c["place"] == "work":
                    office_of[k] = (c["place_load"], office_pool.iloc[by_id[int(c["source_id"])]])
            others = [k for k in range(n) if not x_charges[k]]
            if work["share"] > 0 and others:
                chosen = pick(len(others), work["share"], rng(f"work_{group}_others", effective_seed))
                chosen = [k for k, c in zip(others, chosen) if c]
                office_idx = rng(f"office_{group}_others", effective_seed).integers(
                    0, len(work["offices"]), size=len(chosen))
                session_idx = rng(f"evwatts_work_{group}_others", effective_seed).integers(
                    0, len(office_pool), size=len(chosen))
                for j, k in enumerate(chosen):
                    office_of[k] = (work["offices"][int(office_idx[j])], office_pool.iloc[int(session_idx[j])])
        for k in range(n):
            level1 = None if is_l2[k] else inputs["level1_kw"]
            if k in office_of:
                out[k]["work"] = True
                out[k]["sessions"]["weekday"] = evwatts_session(office_of[k][1], office_of[k][0], place="work")
            else:
                out[k]["sessions"]["weekday"] = evwatts_session(pool["weekday"].iloc[int(idx["weekday"][k])],
                                                                hosts[k], level1)
            out[k]["sessions"]["weekend"] = evwatts_session(pool["weekend"].iloc[int(idx["weekend"][k])],
                                                            hosts[k], level1)
        drawn_days(out)
    elif source == "nhts_days":
        for day_type in ("weekday", "weekend"):
            fail_empty_pool(pool[day_type], "NHTS vehicle-days", where, day_type)
        idx = {"weekday": draw_nhts(pool["weekday"], n, rng(f"nhts_{group}", effective_seed)),
               "weekend": draw_nhts(pool["weekend"], n, rng(f"nhts_weekend_{group}", effective_seed))}
        work_days = {}
        if work is not None:
            work_days = {f"{d['HOUSEID']}-{int(d['VEHID'])}": d for _, d in work["work_day_pool"].iterrows()}
        for k, c in enumerate(cars):
            power = inputs["level2_kw"] if is_l2[k] else inputs["level1_kw"]
            if c["place"] == "work":
                out[k]["work"] = True
                out[k]["sessions"]["weekday"] = nhts_work_session(work_days[c["source_id"]], c["place_load"],
                                                                  inputs["level2_kw"], inputs["kwh_per_mile"])
            else:
                out[k]["sessions"]["weekday"] = nhts_session(pool["weekday"].iloc[int(idx["weekday"][k])],
                                                             hosts[k], power, inputs["kwh_per_mile"])
            out[k]["sessions"]["weekend"] = nhts_session(pool["weekend"].iloc[int(idx["weekend"][k])],
                                                         hosts[k], power, inputs["kwh_per_mile"])
            out[k]["charges"] = [out[k]["sessions"][day_types[p]]["charges"] for p in range(n_p)]
    else:  # session_rows
        c96 = np.asarray(curve, dtype=float)
        energy = c96.sum() / 4.0
        blocks = np.array([charge_shape(s, inputs["level2_kw"], energy, N_INTERVALS) for s in range(N_INTERVALS)])
        mask = blocks > 0
        others = [k for k in range(n) if not x_charges[k]]
        starts = {k: int(c["first_interval"]) - 1 for k, c in enumerate(cars) if x_charges[k]}
        resid = len(others) * c96
        gen = rng(f"session_rows_{group}_others", effective_seed)
        for k in others:
            w = mask @ np.maximum(resid, 0.0)
            if w.sum() == 0:
                w = np.ones(N_INTERVALS)
            starts[k] = int(gen.choice(N_INTERVALS, p=w / w.sum()))
            resid = resid - blocks[starts[k]]
        for k, c in enumerate(cars):
            power = inputs["level2_kw"] if is_l2[k] else inputs["level1_kw"]
            offsets, minute = None, c["plug_minute"]
            if c["window"] is not None and c["plug_in_interval"] is None:
                offsets = list(range(N_INTERVALS))
            elif c["window"] is not None:
                a = int(c["plug_in_interval"]) - 1
                offsets = [a + j for j in range(len(c["window"]))]
                minute = a * 15.0 if minute is None else minute
            one = _session("home", hosts[k], power, energy, offsets, minute,
                           row_offsets=[starts[k] + j for j in range(N_INTERVALS)])
            out[k]["sessions"] = {"weekday": one, "weekend": one}
        drawn_days(out)
    # Day X is the one-day run: its session is that of the car's record
    for k, c in enumerate(cars):
        if source != "session_rows" and x_charges[k]:
            s = out[k]["sessions"]["weekday"]
            if s["source_id"] != c["source_id"] or abs(s["energy"] - c["energy_kwh"]) > 1e-9:
                raise RuntimeError(f"Window session of {c['car']} ({s['source_id']}, {s['energy']} kWh) differs "
                                   f"from its day X record ({c['source_id']}, {c['energy_kwh']} kWh).")
    return out


def plan_car(sessions, charges, n_days, top_up=True):
    """The charging of one car over a window of n_days days, on the window's timeline.

    sessions[p] and charges[p] for p = 0 to n_days: the session the car would use on day
    p (its weekday or weekend session) and whether it charges on that day.
    - A charging day is a session event: the car charges the session's energy at its
      power through the session's intervals, from 00:00 of day p on the timeline, so
      charging past midnight lands on the next day.
    - Energy that does not fit in the window is the car's backlog. On the next day
      without a drawn session (and with top_up) the car has a top-up event: it charges
      its backlog from its own plug-in time, at its own power, inside its own window of
      that day's type; what still does not fit stays in the backlog for the next such
      day.
    - A window ends where the car's next event begins.
    - Day 0, the day before the window, gives day 1 the part of its session after
      midnight; it leaves no backlog and has no top-up.
    - Energy placed after the window's last step, the tail, is not charged in the run;
      it is owed, as is the backlog left at the end.

    Returns (events, days). events: one dict per event in day order, with p, kind
    (session or top_up), energy (to charge), power, place, place_load, placed ({step:
    kW}, steps of the timeline, also those outside the window), window (the steps of the
    car's window inside the run, in plug order), plug_abs (minutes from the window's
    first midnight; the end of day p when the session has no plug-in time), fit_kwh
    (charged inside the car's window), delivered_kwh (the part on the run's steps),
    tail_kwh (the part after the run's last step) and source_id. days: one dict per p,
    with charges, kind ("" without an event), place, place_load, source_id, needed_kwh
    (the session's energy on a charging day of the window; for day 0 the part that
    lands in the run), fit_kwh, delivered_kwh, topup_kwh (delivered_kwh of a top-up),
    tail_kwh, backlog_kwh (the backlog after the day's event) and owed_kwh (needed less
    delivered, summed from day 0 to this day). Over the car, sum of needed_kwh = sum of
    delivered_kwh + the last owed_kwh, and the last owed_kwh = the last backlog_kwh +
    the sum of tail_kwh.

    ASSUMPTION: energy a car cannot charge inside its plug-in window on a charging day
    is charged on the next evening the car has no drawn session, from its own plug-in
    time, at its own power, inside its own window; energy still owed when the horizon
    ends is reported and not charged (charging_share in ev_inputs.yaml).
    ASSUMPTION: a car's plug-in window ends when the car plugs in again, so two events
    of one car never share an interval; this cuts a window only where consecutive days
    use sessions with different plug-in times (a weekday followed by a weekend day, or
    the reverse), and the energy cut off joins the backlog."""
    n_steps = n_days * N_INTERVALS
    events, state = [], {"backlog": 0.0}

    def fit(event, steps):
        """{step: kW} of event's energy at its power through steps, as charge_window."""
        energy, power = 4.0 * event["energy"], event["power"]
        if energy <= 0 or power <= 0:
            return {}
        n_full = int(math.floor(energy / power + EPS))
        rem = energy - n_full * power
        placed = {t: power for t in steps[:n_full]}
        if n_full < len(steps) and rem >= EPS:
            placed[steps[n_full]] = rem
        return placed

    def change(event, placed):
        """What event adds to the backlog when it charges placed."""
        if event["p"] == 0:
            return 0.0
        fit_kwh = sum(placed.values()) / 4.0
        return event["energy"] - fit_kwh if event["kind"] == "session" else -fit_kwh

    def close(event, cut=None):
        if cut is not None:
            event["row_steps"] = [t for t in event["row_steps"] if t < cut]
            event["window_steps"] = [t for t in event["window_steps"] if t < cut]
        event["placed"] = fit(event, event["row_steps"])
        state["backlog"] = max(0.0, state["backlog"] + change(event, event["placed"]))
        event["backlog_after"] = state["backlog"]

    pending = None
    for p in range(n_days + 1):
        s = sessions[p]
        base = (p - 1) * N_INTERVALS
        is_session = bool(charges[p]) and s["energy"] > 0
        if not is_session:
            open_change = change(pending, fit(pending, pending["row_steps"])) if pending is not None else 0.0
            if not (top_up and p >= 1 and state["backlog"] + open_change > EPS):
                continue
        start = base + s["row_offsets"][0]
        if pending is not None:
            close(pending, cut=start)
        day_steps = [base + k for k in range(N_INTERVALS)]
        pending = {"p": p, "kind": "session" if is_session else "top_up",
                   "energy": s["energy"] if is_session else state["backlog"], "power": s["power"],
                   "place": s["place"], "place_load": s["place_load"], "source_id": s["source_id"],
                   "row_steps": [base + o for o in s["row_offsets"]],
                   "window_steps": day_steps if s["offsets"] is None else [base + o for o in s["offsets"]],
                   "plug_abs": base * 15.0 + (s["plug_minute"] if s["plug_minute"] is not None else 1440.0)}
        events.append(pending)
    if pending is not None:
        close(pending)

    by_day = {}
    for event in events:
        inside = sum(kw for t, kw in event["placed"].items() if 0 <= t < n_steps) / 4.0
        event["fit_kwh"] = sum(event["placed"].values()) / 4.0
        event["delivered_kwh"] = inside
        event["tail_kwh"] = sum(kw for t, kw in event["placed"].items() if t >= n_steps) / 4.0
        event["window"] = [t for t in event["window_steps"] if 0 <= t < n_steps]
        by_day[event["p"]] = event
    days, backlog, needed_sum, delivered_sum = [], 0.0, 0.0, 0.0
    for p in range(n_days + 1):
        event = by_day.get(p)
        row = {"charges": bool(charges[p]), "kind": "", "place": sessions[p]["place"],
               "place_load": sessions[p]["place_load"], "source_id": "", "needed_kwh": 0.0, "fit_kwh": 0.0,
               "delivered_kwh": 0.0, "topup_kwh": 0.0, "tail_kwh": 0.0}
        if event is not None:
            backlog = event["backlog_after"]
            session = event["kind"] == "session"
            needed = (event["energy"] if p >= 1 else event["delivered_kwh"] + event["tail_kwh"]) if session else 0.0
            row.update({"kind": event["kind"], "source_id": event["source_id"], "needed_kwh": needed,
                        "fit_kwh": event["fit_kwh"], "delivered_kwh": event["delivered_kwh"],
                        "topup_kwh": 0.0 if session else event["delivered_kwh"], "tail_kwh": event["tail_kwh"]})
        needed_sum += row["needed_kwh"]
        delivered_sum += row["delivered_kwh"]
        row["backlog_kwh"] = backlog
        row["owed_kwh"] = needed_sum - delivered_sum
        days.append(row)
    return events, days


def event_row(event, n_steps):
    """The kW of one event of plan_car on the n_steps steps of the run."""
    row = np.zeros(n_steps)
    for t, kw in event["placed"].items():
        if 0 <= t < n_steps:
            row[t] = kw
    return row
