# -*- coding: utf-8 -*-
"""
build_nhts_extract.py
---------------------
Maintainer step outside --all: the 2017 NHTS weekday vehicle-days of NC and TX that
ev_cars: nhts_days draws from, and the windows of the controlled cars under
ev_cars: session_rows (deployer_modules/ev_cars.py).

Run once from the repository root:  python 7_circuit_instantiation/build_nhts_extract.py
and once more with --day-type weekend for the Saturday and Sunday vehicle-days (the
weekend days of a horizon of more than one day draw from them).

Inputs
- configs/local.yaml: nhts2017_csv_dir, the unpacked
  https://nhts.ornl.gov/assets/2016/download/Csv.zip (hhpub.csv, vehpub.csv,
  trippub.csv). Codebook: https://nhts.ornl.gov/assets/codebook.pdf

Rules
1. Vehicle-days: vehpub.csv rows with HHSTATE NC or TX, VEHTYPE 01 to 04 (car, van,
   SUV, pickup) and TRAVDAY 02 to 06 (Monday to Friday), or with --day-type weekend
   TRAVDAY 07 (Saturday) and 01 (Sunday). TDAYDATE comes from hhpub.csv by HOUSEID;
   WTHHFIN from vehpub.csv.
2. Driver trips: trippub.csv rows with DRVR_FLG 01, joined to the vehicle-days on
   HOUSEID and VEHID. A duplicate driver trip (same vehicle, STRTTIME, ENDTIME, WHYFROM
   and WHYTO) is kept once. Clock minutes from HHMM; a negative time is missing.
3. A vehicle's driver trips are ordered by (start minute - 240) mod 1440: the travel day
   runs from 04:00 to 04:00. The 2022 NextGen NHTS User's Guide, page 8
   (https://nhts.ornl.gov/media/2022/doc/2022%20NextGen%20NHTS%20%20User's%20Guide%20V1_PubUse.pdf):
   "The 24-hour tour begins at 4 AM on the assigned travel date and ends at 4 AM on the
   following day".
   ASSUMPTION: the 2017 NHTS travel day of every NC and TX vehicle also starts at 04:00,
   as the 2022 survey states for its own; the 2017 public files carry no day start,
   and a different start would move trips near 04:00 between the start and the end of
   the day and can change which trip is the last arrival home.
4. Home is WHYFROM or WHYTO 01 (regular home activities) or 02 (work from home).
   Class (i): arrival_min = ENDTIME of the last trip with WHYTO home, departure_min =
   STRTTIME of the first trip with WHYFROM home, window_min = d' - a' when d' >= a',
   else d' + 1440 - a', with x' = (x - 240) mod 1440: the car is home from its last
   arrival to its first departure, and on a day that starts away from home this is the
   same day's span. Class (ii): no driver trip. Class (iii): driver trips,
   but none ending or none starting at home (with a valid time).
5. driver_miles = sum of TRPMILES of the driver trips; a negative TRPMILES is counted in
   n_miles_missing and taken as 0.
6. Speed check: for a driver trip with a valid start, end and miles, duration =
   end_min - start_min (plus 1440 when negative) and speed = miles / ((duration + 1) / 60)
   mph. A vehicle-day with any driver trip faster than nhts_max_trip_speed_mph (typical
   value of data_ev_cars/ev_inputs.yaml) is class (iv), with no window, whatever its
   class under rule 4. Trips with a missing time or missing miles are not tested.
7. Work is WHYTO 03. Over the vehicle's driver trips in the rule 3 order, each trip with
   WHYTO 03 and a valid end time starts a work piece at its ENDTIME. The piece ends at
   the STRTTIME of the vehicle's next driver trip in that order when that trip exists
   and its start time is valid, else at 04:00 (minute 240), the end of the travel day.
   Parked minutes = e' - a' when e' >= a', else e' + 1440 - a', with x' = (x - 240) mod
   1440, as the home window of rule 4. Work pieces are computed for every class.

Outputs (in 7_circuit_instantiation/data_ev_cars/)
- <ST>_nhts2017_vehicle_days.csv for NC and TX, sorted by HOUSEID and VEHID, columns
  HOUSEID, VEHID, TDAYDATE, TRAVDAY, WTHHFIN, day_class, arrival_min, departure_min,
  window_min, driver_miles, n_driver_trips, n_miles_missing, n_work_pieces (0 when
  none), work_min (the sum of parked minutes at work, empty when none), work_pieces
  (the pieces in day order as arrival:minutes joined by |, for example 480:240|780:290,
  arrival as a clock minute; empty when none).
- nhts2017_extract.yaml: source URLs, build time UTC, filters, window rule, speed rule,
  work rule, rows per state and class (i to iv), days with a work stop per state and
  class.
- With --day-type weekend: <ST>_nhts2017_vehicle_days_weekend.csv for NC and TX, with
  the same columns and rules (TRAVDAY is the day column: 07 Saturday, 01 Sunday), and
  the block weekend of nhts2017_extract.yaml: its files, build time UTC, the TRAVDAY
  filter, rows per state, day and class, and days with a work stop per state and class.
  The rest of the record is kept as it is; a weekday build keeps the weekend block.

Stops (exit 1): nhts2017_csv_dir missing from configs/local.yaml, or an input file
missing.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars")
STATES = ["NC", "TX"]
CAR_TYPES = {1, 2, 3, 4}
WEEKDAYS = {2, 3, 4, 5, 6}
# --day-type: the TRAVDAY values kept, the end of the output file names and the filter text
DAY_TYPES = {
    "weekday": (WEEKDAYS, "", "TRAVDAY 02 to 06"),
    "weekend": ({7, 1}, "_weekend", "TRAVDAY 07 (Saturday) or 01 (Sunday)"),
}
WEEKEND_DAY_NAMES = {7: "Saturday", 1: "Sunday"}
HOME = {1, 2}
WORK = 3
DAY_START_MIN = 240
COLUMNS = ["HOUSEID", "VEHID", "TDAYDATE", "TRAVDAY", "WTHHFIN", "day_class", "arrival_min",
           "departure_min", "window_min", "driver_miles", "n_driver_trips", "n_miles_missing",
           "n_work_pieces", "work_min", "work_pieces"]


def hhmm_to_min(s):
    """HHMM (string or number) to clock minutes; negative or unparseable gives NaN."""
    v = pd.to_numeric(s, errors="coerce")
    v = v.where(v >= 0)
    return (v // 100) * 60 + (v % 100)


def work_pieces(t):
    """Rule 7 on the sorted driver trips t (columns HOUSEID, VEHID, start_min, end_min,
    WHYTO, in the rule 3 order). Returns a frame indexed by (HOUSEID, VEHID) with
    n_work_pieces, work_min and work_pieces for the vehicles that have a piece."""
    next_start = t.groupby(["HOUSEID", "VEHID"], sort=False)["start_min"].shift(-1)
    at_work = (pd.to_numeric(t["WHYTO"], errors="coerce") == WORK) & t["end_min"].notna()
    a = t.loc[at_work, "end_min"]
    e = next_start[at_work].fillna(DAY_START_MIN)
    a1 = (a - DAY_START_MIN) % 1440
    e1 = (e - DAY_START_MIN) % 1440
    parked = (e1 - a1).where(e1 >= a1, e1 + 1440 - a1)
    pieces = pd.DataFrame({"HOUSEID": t.loc[at_work, "HOUSEID"], "VEHID": t.loc[at_work, "VEHID"],
                           "parked": parked.astype("int64"),
                           "text": [f"{int(x)}:{int(m)}" for x, m in zip(a, parked)]})
    g = pieces.groupby(["HOUSEID", "VEHID"], sort=False)
    return pd.DataFrame({"n_work_pieces": g.size(), "work_min": g["parked"].sum(),
                         "work_pieces": g["text"].agg("|".join)})


def vehicle_days(veh, trips, max_speed_mph):
    """Classify vehicle-days (rules 2 to 7).

    veh: one row per vehicle-day with HOUSEID, VEHID (integer), TDAYDATE, TRAVDAY,
    WTHHFIN. trips: trippub.csv rows with HOUSEID, VEHID, STRTTIME, ENDTIME, WHYFROM,
    WHYTO, DRVR_FLG, TRPMILES. max_speed_mph: the speed above which a driver trip makes
    its vehicle-day class (iv). Returns veh with the extract columns, sorted by HOUSEID
    and VEHID."""
    v = veh.copy()
    v["VEHID"] = pd.to_numeric(v["VEHID"], errors="coerce").astype("int64")
    t = trips.copy()
    t["VEHID"] = pd.to_numeric(t["VEHID"], errors="coerce")
    t = t[pd.to_numeric(t["DRVR_FLG"], errors="coerce") == 1]
    keys = set(zip(v["HOUSEID"], v["VEHID"]))
    t = t[[k in keys for k in zip(t["HOUSEID"], t["VEHID"])]]
    t = t[~t.duplicated(["HOUSEID", "VEHID", "STRTTIME", "ENDTIME", "WHYFROM", "WHYTO"])].copy()
    t["VEHID"] = t["VEHID"].astype("int64")
    t["start_min"] = hhmm_to_min(t["STRTTIME"])
    t["end_min"] = hhmm_to_min(t["ENDTIME"])
    t["order"] = (t["start_min"] - DAY_START_MIN) % 1440
    t["from_home"] = pd.to_numeric(t["WHYFROM"], errors="coerce").isin(HOME)
    t["to_home"] = pd.to_numeric(t["WHYTO"], errors="coerce").isin(HOME)
    miles = pd.to_numeric(t["TRPMILES"], errors="coerce")
    t["miles_missing"] = (miles < 0) | miles.isna()
    t["miles"] = miles.where(~t["miles_missing"], 0.0)
    duration = t["end_min"] - t["start_min"]
    duration = duration.where(duration >= 0, duration + 1440)
    speed = t["miles"] / ((duration + 1) / 60)
    t["too_fast"] = (speed > max_speed_mph) & ~t["miles_missing"] & duration.notna()
    t = t.sort_values(["HOUSEID", "VEHID", "order"], kind="mergesort")
    g = t.groupby(["HOUSEID", "VEHID"], sort=False)
    stats = pd.DataFrame({"n_driver_trips": g.size(), "driver_miles": g["miles"].sum(),
                          "n_miles_missing": g["miles_missing"].sum(), "too_fast": g["too_fast"].any()})
    arr = t[t["to_home"] & t["end_min"].notna()].groupby(["HOUSEID", "VEHID"])["end_min"].last()
    dep = t[t["from_home"] & t["start_min"].notna()].groupby(["HOUSEID", "VEHID"])["start_min"].first()
    v = v.join(stats, on=["HOUSEID", "VEHID"])
    v = v.join(work_pieces(t), on=["HOUSEID", "VEHID"])
    v["n_work_pieces"] = v["n_work_pieces"].fillna(0).astype("int64")
    v["work_min"] = v["work_min"].astype("Int64")
    v["work_pieces"] = v["work_pieces"].fillna("")
    v["arrival_min"] = [arr.get(k, np.nan) for k in zip(v["HOUSEID"], v["VEHID"])]
    v["departure_min"] = [dep.get(k, np.nan) for k in zip(v["HOUSEID"], v["VEHID"])]
    v["n_driver_trips"] = v["n_driver_trips"].fillna(0).astype("int64")
    v["n_miles_missing"] = v["n_miles_missing"].fillna(0).astype("int64")
    v["driver_miles"] = v["driver_miles"].fillna(0.0)
    has_window = v["arrival_min"].notna() & v["departure_min"].notna()
    v["day_class"] = np.where(v["n_driver_trips"] == 0, "ii", np.where(has_window, "i", "iii"))
    v.loc[v["too_fast"].fillna(False).astype(bool), "day_class"] = "iv"
    a1 = (v["arrival_min"] - DAY_START_MIN) % 1440
    d1 = (v["departure_min"] - DAY_START_MIN) % 1440
    v["window_min"] = (d1 - a1).where(d1 >= a1, d1 + 1440 - a1).where(v["day_class"] == "i")
    v.loc[v["day_class"] != "i", ["arrival_min", "departure_min"]] = np.nan
    for col in ("arrival_min", "departure_min", "window_min"):
        v[col] = v[col].astype("Int64")
    return v.sort_values(["HOUSEID", "VEHID"], kind="mergesort")[COLUMNS].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Build the NHTS 2017 vehicle-day extract.")
    parser.add_argument("--day-type", choices=sorted(DAY_TYPES), default="weekday",
                        help="weekday (default): TRAVDAY 02 to 06; weekend: TRAVDAY 07 and 01, "
                             "written to <ST>_nhts2017_vehicle_days_weekend.csv")
    day_type = parser.parse_args().day_type
    travdays, file_end, travday_text = DAY_TYPES[day_type]
    with open(os.path.join(REPO_ROOT, "configs", "local.yaml"), encoding="utf-8") as f:
        local = yaml.safe_load(f) or {}
    src = local.get("nhts2017_csv_dir")
    if not src:
        print("[FAIL] nhts2017_csv_dir is not set in configs/local.yaml.")
        sys.exit(1)
    paths = {n: os.path.join(src, n) for n in ("hhpub.csv", "vehpub.csv", "trippub.csv")}
    for p in paths.values():
        if not os.path.exists(p):
            print(f"[FAIL] NHTS file not found: {p}")
            sys.exit(1)
    hh = pd.read_csv(paths["hhpub.csv"], dtype=str, usecols=["HOUSEID", "TDAYDATE"])
    vh = pd.read_csv(paths["vehpub.csv"], dtype=str,
                     usecols=["HOUSEID", "VEHID", "VEHTYPE", "HHSTATE", "TRAVDAY", "WTHHFIN"])
    tr = pd.read_csv(paths["trippub.csv"], dtype=str,
                     usecols=["HOUSEID", "VEHID", "STRTTIME", "ENDTIME", "WHYFROM", "WHYTO",
                              "DRVR_FLG", "TRPMILES"])
    vh = vh[vh["HHSTATE"].isin(STATES)
            & pd.to_numeric(vh["VEHTYPE"], errors="coerce").isin(CAR_TYPES)
            & pd.to_numeric(vh["TRAVDAY"], errors="coerce").isin(travdays)]
    vh = vh.merge(hh, on="HOUSEID", how="left")
    vh["WTHHFIN"] = pd.to_numeric(vh["WTHHFIN"])
    with open(os.path.join(OUT_DIR, "ev_inputs.yaml"), encoding="utf-8") as f:
        max_speed_mph = yaml.safe_load(f)["nhts_max_trip_speed_mph"]["typical"]
    counts, work_counts, day_counts = {}, {}, {}
    for st in STATES:
        days = vehicle_days(vh[vh["HHSTATE"] == st][["HOUSEID", "VEHID", "TDAYDATE", "TRAVDAY", "WTHHFIN"]],
                            tr[tr["HOUSEID"].isin(set(vh.loc[vh["HHSTATE"] == st, "HOUSEID"]))],
                            max_speed_mph)
        days.to_csv(os.path.join(OUT_DIR, f"{st}_nhts2017_vehicle_days{file_end}.csv"), index=False)
        travday = pd.to_numeric(days["TRAVDAY"], errors="coerce")
        day_counts[st] = {name: {c: int(((travday == code) & (days["day_class"] == c)).sum())
                                 for c in ("i", "ii", "iii", "iv")}
                          for code, name in WEEKEND_DAY_NAMES.items()}
        counts[st] = {c: int((days["day_class"] == c).sum()) for c in ("i", "ii", "iii", "iv")}
        work_counts[st] = {c: int(((days["day_class"] == c) & (days["n_work_pieces"] > 0)).sum())
                           for c in ("i", "ii", "iii", "iv")}
        print(f"[OK] {st}: {len(days):,} vehicle-days {counts[st]}, with a work stop {work_counts[st]}")
    record_path = os.path.join(OUT_DIR, "nhts2017_extract.yaml")
    old_record = {}
    if os.path.exists(record_path):
        with open(record_path, encoding="utf-8") as f:
            old_record = yaml.safe_load(f) or {}
    if day_type == "weekend":
        # The weekend block; the rest of the record stays as the weekday build wrote it.
        old_record["weekend"] = {
            "files": [f"{st}_nhts2017_vehicle_days{file_end}.csv" for st in STATES],
            "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "travday_filter": travday_text,
            "rows_per_state_day_and_class": day_counts,
            "rows_per_state_and_class": counts,
            "work_days_per_state_and_class": work_counts,
        }
        with open(record_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(old_record, f, sort_keys=False)
        return
    record = {
        "source": "2017 National Household Travel Survey, U.S. Department of Transportation, Federal Highway Administration",
        "data_url": "https://nhts.ornl.gov/assets/2016/download/Csv.zip",
        "codebook_url": "https://nhts.ornl.gov/assets/codebook.pdf",
        "input_files": sorted(paths),
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filters": [
            "HHSTATE NC or TX",
            "VEHTYPE 01 to 04",
            "TRAVDAY 02 to 06",
            "driver trips: DRVR_FLG 01, joined on HOUSEID and VEHID, duplicates (vehicle, STRTTIME, ENDTIME, WHYFROM, WHYTO) kept once",
            "home: WHYFROM or WHYTO 01 or 02",
            "trips ordered by (start minute - 240) mod 1440",
        ],
        "window_rule": "class i: window_min = d' - a' when d' >= a', else d' + 1440 - a', with x' = (x - 240) mod 1440, a the last arrival home and d the first departure from home",
        "speed_rule": f"class iv: a driver trip with a valid start, end and miles faster than {max_speed_mph} mph, speed = miles / ((end - start, plus 1440 when negative, + 1) / 60)",
        "work_rule": "work pieces: each driver trip with WHYTO 03 and a valid end time starts a piece at its ENDTIME; the piece ends at the STRTTIME of the next driver trip when it exists and is valid, else at 04:00; parked minutes as the window rule",
        "rows_per_state_and_class": counts,
        "work_days_per_state_and_class": work_counts,
    }
    if "weekend" in old_record:
        record["weekend"] = old_record["weekend"]
    with open(record_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, sort_keys=False)


if __name__ == "__main__":
    main()
