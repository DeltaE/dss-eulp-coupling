# -*- coding: utf-8 -*-
"""
build_evwatts_extract.py
------------------------
Maintainer step outside --all: the residential Level 2 weekday sessions of EV WATTS
that ev_cars: evwatts_sessions and session_rows draw from (deployer_modules/ev_cars.py).

Run once from the repository root:  python 7_circuit_instantiation/build_evwatts_extract.py

Inputs
- configs/local.yaml: evwatts_raw_dir (the folder that holds evwatts.public.session.csv
  and evwatts.public.evse.csv of the EV WATTS public database,
  https://doi.org/10.15483/1970735, downloaded from
  https://livewire.energy.gov/ds/evwatts/evwatts.public) and evwatts_extract_dir (where
  the extract goes; outside the repository).
- 7_circuit_instantiation/data_ev_cars/ev_inputs.yaml: census_division (typical), the
  divisions kept, and level2_max_kw (typical), the highest Level 2 power.

Rules, in this order (each filter's dropped rows are counted):
1. sessions joined to the evse table on evse_id; sessions without a match are left out;
2. charge_level L2;
3. venue Single Family Residential or Multi-Unit Dwelling;
4. region in the divisions of census_division;
5. start_datetime on Monday to Friday;
6. end_datetime - start_datetime present, not below 0 and at most 24 h;
7. flag_id 0 (an empty flag_id counts as 0);
8. end_datetime - start_datetime above 0;
9. energy_kwh above 0;
10. charge_duration above 0 and at most end_datetime - start_datetime plus one minute;
11. energy_kwh / charge_duration (the session's mean power) at most level2_max_kw.
Timestamps are read as the local clock time of the charger: the database gives no time
zone (ASSUMPTION in ev_cars.py).

Outputs (in evwatts_extract_dir)
- evwatts_residential_l2_weekday.csv, sorted by session_id, columns session_id,
  evse_id, division, venue, start_date (YYYY-MM-DD), weekday (0 Monday to 4 Friday),
  month, start_min (clock minute of start_datetime with seconds as decimals), plug_min
  (end_datetime - start_datetime in minutes), charge_h (charge_duration, hours),
  energy_kwh.
- evwatts_extract.yaml: sources, input file names and bytes, build time UTC,
  level2_max_kw, filters, rows dropped by each filter, rows kept per division and venue.

Stops (exit 1): a key missing from configs/local.yaml, an input file missing, or the
extract folder inside the repository.
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.path.join(REPO_ROOT, "7_circuit_instantiation", "data_ev_cars", "ev_inputs.yaml")
SESSION_FILE = "evwatts.public.session.csv"
EVSE_FILE = "evwatts.public.evse.csv"
OUT_CSV = "evwatts_residential_l2_weekday.csv"
OUT_YAML = "evwatts_extract.yaml"
VENUES = ["Single Family Residential", "Multi-Unit Dwelling"]
CHUNK = 2_000_000
FILTERS = [
    "evse_id in the evse table",
    "charge_level L2",
    "venue Single Family Residential or Multi-Unit Dwelling",
    "region in the census divisions",
    "start_datetime on Monday to Friday",
    "end_datetime - start_datetime present, not below 0 and at most 24 h",
    "flag_id 0 (empty counts as 0)",
    "end_datetime - start_datetime above 0",
    "energy_kwh above 0",
    "charge_duration above 0 and at most end_datetime - start_datetime plus one minute",
    "energy_kwh / charge_duration at most level2_max_kw",
]


def fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def local_value(local, key):
    if not local.get(key):
        fail(f"{key} is not set in configs/local.yaml.")
    return local[key]


def apply_filters(s, evse, divisions, level2_max_kw):
    """Apply the eleven rules to one session table s (columns of the session file) and the
    evse table (indexed by evse_id). Returns (kept rows with the extract columns, list
    of rows dropped by each rule)."""
    dropped = []

    def keep(df, mask):
        dropped.append(int((~mask).sum()))
        return df[mask]

    s = keep(s, s["evse_id"].isin(evse.index))
    s = s.join(evse[["charge_level", "venue", "region"]], on="evse_id")
    s = keep(s, s["charge_level"] == "L2")
    s = keep(s, s["venue"].isin(VENUES))
    s = keep(s, s["region"].isin(divisions))
    t0 = pd.to_datetime(s["start_datetime"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    t1 = pd.to_datetime(s["end_datetime"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    s = s.assign(t0=t0, t1=t1)
    s = keep(s, s["t0"].dt.dayofweek < 5)
    plug_s = (s["t1"] - s["t0"]).dt.total_seconds()
    s = keep(s, plug_s.notna() & (plug_s >= 0) & (plug_s <= 24 * 3600))
    before_flag = s.groupby("region").size().to_dict()
    s = keep(s, s["flag_id"].fillna(0).astype("int64") == 0)
    plug_s = (s["t1"] - s["t0"]).dt.total_seconds()
    s = keep(s, plug_s > 0)
    s = keep(s, s["energy_kwh"] > 0)
    plug_h = (s["t1"] - s["t0"]).dt.total_seconds() / 3600.0
    s = keep(s, (s["charge_duration"] > 0) & (s["charge_duration"] <= plug_h + 1.0 / 60.0))
    s = keep(s, s["energy_kwh"] / s["charge_duration"] <= level2_max_kw)
    t0 = s["t0"]
    out = pd.DataFrame({
        "session_id": s["session_id"],
        "evse_id": s["evse_id"],
        "division": s["region"],
        "venue": s["venue"],
        "start_date": t0.dt.strftime("%Y-%m-%d"),
        "weekday": t0.dt.dayofweek,
        "month": t0.dt.month,
        "start_min": t0.dt.hour * 60 + t0.dt.minute + t0.dt.second / 60.0,
        "plug_min": (s["t1"] - t0).dt.total_seconds() / 60.0,
        "charge_h": s["charge_duration"],
        "energy_kwh": s["energy_kwh"],
    })
    return out, dropped, before_flag


def main():
    with open(os.path.join(REPO_ROOT, "configs", "local.yaml"), encoding="utf-8") as f:
        local = yaml.safe_load(f) or {}
    raw_dir = local_value(local, "evwatts_raw_dir")
    out_dir = local_value(local, "evwatts_extract_dir")
    if os.path.abspath(out_dir).lower().startswith(REPO_ROOT.lower()):
        fail(f"evwatts_extract_dir {out_dir} is inside the repository; set a folder outside it.")
    with open(INPUTS, encoding="utf-8") as f:
        inputs = yaml.safe_load(f)
    divisions = sorted(set(inputs["census_division"]["typical"].values()))
    level2_max_kw = float(inputs["level2_max_kw"]["typical"])
    paths = {name: os.path.join(raw_dir, name) for name in (SESSION_FILE, EVSE_FILE)}
    for p in paths.values():
        if not os.path.exists(p):
            fail(f"EV WATTS file not found: {p}")
    evse = pd.read_csv(paths[EVSE_FILE], encoding="utf-8-sig").set_index("evse_id")
    n_read, dropped, parts, before_flag = 0, [0] * len(FILTERS), [], {}
    for ch in pd.read_csv(paths[SESSION_FILE], chunksize=CHUNK, encoding="utf-8-sig",
                          usecols=["session_id", "evse_id", "start_datetime", "end_datetime",
                                   "charge_duration", "energy_kwh", "flag_id"]):
        n_read += len(ch)
        kept, d, bf = apply_filters(ch, evse, divisions, level2_max_kw)
        dropped = [a + b for a, b in zip(dropped, d)]
        for k, v in bf.items():
            before_flag[k] = before_flag.get(k, 0) + int(v)
        parts.append(kept)
        print(f"  read {n_read:,} session rows, kept {sum(len(p) for p in parts):,}")
    out = pd.concat(parts, ignore_index=True).sort_values("session_id", kind="mergesort")
    os.makedirs(out_dir, exist_ok=True)
    out.to_csv(os.path.join(out_dir, OUT_CSV), index=False)
    kept_by = {f"{d} | {v}": int(n) for (d, v), n in out.groupby(["division", "venue"]).size().items()}
    remaining, rows_after = n_read, []
    for name, n in zip(FILTERS, dropped):
        remaining -= n
        rows_after.append({"filter": name, "dropped": n, "rows_after": remaining})
    record = {
        "source": "EV WATTS public database, U.S. Department of Energy",
        "doi": "https://doi.org/10.15483/1970735",
        "download_page": "https://livewire.energy.gov/ds/evwatts/evwatts.public",
        "input_files": {name: os.path.getsize(p) for name, p in paths.items()},
        "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "divisions": divisions,
        "level2_max_kw": level2_max_kw,
        "session_rows_read": n_read,
        "filters": rows_after,
        "rows_before_flag_rule_by_division": dict(sorted(before_flag.items())),
        "rows_kept": len(out),
        "rows_kept_by_division_and_venue": kept_by,
    }
    with open(os.path.join(out_dir, OUT_YAML), "w", encoding="utf-8") as f:
        yaml.safe_dump(record, f, sort_keys=False, allow_unicode=True)
    print(f"[OK] {len(out):,} sessions -> {os.path.join(out_dir, OUT_CSV)}")


if __name__ == "__main__":
    main()
