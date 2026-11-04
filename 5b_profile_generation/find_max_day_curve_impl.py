# -*- coding: utf-8 -*-
"""
Phase 5b: find each feeder's winter and summer peak day and save that day of every
building profile.

Usage: python find_max_day_curve_impl.py --scenario {baseline,dm,uncontrolled}
       python find_max_day_curve_impl.py --mix <mix name>
Run through phase5b_peak.py (baseline, step 5b) and phase5b_variants_dm.py and
phase5b_variants_uncontrolled.py (step 5b_variants) in configs/phases.yaml, and with
--mix through mix_days.py (phase mix_days). State, work root and parquet root come
from the PIPELINE_* variables through pipeline_utils.load_config; a missing variable
exits 1.

Inputs
- baseline: <work_root>/5b_profile_generation/<STATE>_required_parquets_per_feeder.csv
- dm, uncontrolled: <work_root>/5d_scenario_controls/get_scenario_csv_controls/
  <STATE>_required_parquets_per_feeder_<scenario>.csv
  Columns Feeder, Parquet_Folder, Parquet_File, REAL_LOAD_COUNT.
- <parquet_data_root>/<Parquet_Folder>/<Parquet_File>: EULP building time series
  with timestamp and out.electricity.total.energy_consumption (kWh per 15 minutes).

Steps
1. Per feeder, in CSV order: sums energy * 4 * REAL_LOAD_COUNT over its rows into one
   kW curve.
2. Puts the curve on a 15-minute index from 2025-01-01 00:00; per month, takes the day
   with the highest single 15-minute value; keeps it if it has 96 points.
3. Winter peak day: the kept month in {12, 1, 2} with the highest point; summer: the
   same in {6, 7, 8}. Both seasons are always processed; the run's season is not used.
4. For each CSV row of the feeder, reads the full parquet, keeps the rows whose
   timestamp month and day equal the peak day (any year), and writes them.

Outputs
- baseline only: <work_root>/5b_profile_generation/<STATE>_peak_days.csv, one row per
  feeder and season (Feeder, Season, Month, Day, Peak_kW). Phase 7 takes each
  circuit's PV daily shape from this date.
- <work_root>/5b_profile_generation/daily_parquets/
  <STATE>_<feeder with "--" as "_">_<winter|summer><suffix>/<Parquet_File>,
  suffix "" (baseline), "_dm" or "_uncontrolled". Folders are created if missing and
  never cleared. Plots are closed unsaved. The winter and summer peak days are also
  printed for every scenario.

Fallbacks
- Curve pass: an unreadable parquet prints "Error reading ..." and is left out of the
  feeder sum.
- A month whose peak day lacks 96 points prints "Incomplete daily curve ..." and is
  left out.

Stops
- Slice pass, every scenario: an empty peak day exits 1 (winter) or 3 (summer); an
  unreadable parquet exits 2 (winter) or 4 (summer).
- A missing input CSV raises FileNotFoundError (exit 1).

--mix <name> (peak_day_rule: per_circuit in pipeline_config.yaml; with per_group it
prints one line and writes nothing)
1. Labels every load of every feeder in the feeder registry with heating_split, from
   the same SMART-DS Loads.dss and the same mix entry (PIPELINE_MIXES_FILE) as Phase 7b.
2. Links each loadshape <prefix>_kw_<num>_pu to its building, Parquet_Name
   <prefix>_<num>, in <STATE>_parquet_and_bldgs.csv (baseline) or
   <STATE>_parquet_and_bldgs_<dm|uncontrolled>.csv, and the building's Parquet_File to
   the scenario's required-parquet list.
3. Weight of building b in group g: REAL_LOAD_COUNT of b x (b's loads labelled g / b's
   loads). Weights of buildings that share a parquet file are summed per file.
4. Feeder curve: per group (baseline, dm, uncontrolled) and required-list row in CSV
   order, energy * 4 * weight, summed. Steps 2 and 3 above give the peak day, day X.
5. Writes <work_root>/mix_days/<STATE>_circuit_days.csv (Feeder, Season, Mix, Month,
   Day, Peak_kW), <STATE>_circuit_labels.csv (Feeder, Mix, daily_name, scenario,
   n_loads, Parquet_Name, REAL_LOAD_COUNT) and <STATE>_circuit_weights.csv (Feeder,
   Mix, Group, Parquet_File, Weight), replacing the rows of this mix.
6. A mix that is 100 % baseline: its rows must equal <STATE>_peak_days.csv (month, day
   and Peak_kW as written), else [FAIL]; nothing is cut. Any other mix: step 4 above
   for every required-list row of every group and feeder, both seasons, on day X, into
   <work_root>/mix_days/<mix>/5b_profile_generation/daily_parquets/ with the same
   folder names.
Stops with [FAIL]: unknown mix; a load whose building is in some group's mapping but
not in the group it is labelled with; a building file missing from that group's
required list. A loadshape whose building is in no group's mapping (Phase 7b gives it
a flat shape) is left out of the curve and printed.
"""

import argparse
import io
import json
import os
import re
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pandas as pd
from datetime import timedelta
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import (load_config, load_feeder_registry, peak_day_rule,
                            resolve_config_path, resolve_work_path)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '7_circuit_instantiation'))
from heating_split import is_baseline_only, read_loads, split_heating

START_PROCESS = time.time()

SCENARIO_INPUTS = {
    "baseline": ("5b_profile_generation", "_required_parquets_per_feeder.csv"),
    "dm": (os.path.join("5d_scenario_controls", "get_scenario_csv_controls"), "_required_parquets_per_feeder_dm.csv"),
    "uncontrolled": (os.path.join("5d_scenario_controls", "get_scenario_csv_controls"), "_required_parquets_per_feeder_uncontrolled.csv"),
}
parser = argparse.ArgumentParser(description="Phase 5b peak-day slices for one scenario, or for one mix.")
_mode = parser.add_mutually_exclusive_group(required=True)
_mode.add_argument("--scenario", choices=sorted(SCENARIO_INPUTS))
_mode.add_argument("--mix", help="mix name in the mixes file (phase mix_days)")
ARGS = parser.parse_args()

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
STR_STATE = STATE
STR_TITLE = STR_STATE

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PARQUET_DATA_ROOT = Path(cfg['parquet_data_root'])
if not PARQUET_DATA_ROOT.is_absolute():
    PARQUET_DATA_ROOT = (REPO_ROOT / PARQUET_DATA_ROOT).resolve()

# --- run controls (added) ---
SHOW_PLOTS = False              # True = show spaghetti plots; False = skip (won't block on a server)
SCENARIO = "" if ARGS.scenario == "baseline" else ARGS.scenario  # daily_parquets suffix so baseline/dm/uncontrolled don't overwrite each other
_SCEN_SUFFIX = f"_{SCENARIO}" if SCENARIO else ""

WINTER_MONTHS = [1, 2, 12]
SUMMER_MONTHS = [6, 7, 8]


def monthly_peak_curves(feeder, total_curve):
    """Per month, the day with the highest 15-minute value of total_curve (index from
    2025-01-01 00:00, 15 minutes) and its 96 points; a day without 96 points is skipped.
    Returns (peak_curves, df_curve), peak_curves[month] = {"date": (month, date), "curve"}."""
    # Create a time index assuming first point is Jan 1st 00:00 and 15-min intervals
    start_time = pd.Timestamp("2025-01-01 00:00:00")
    time_index = [start_time + timedelta(minutes=15 * i) for i in range(len(total_curve))]

    # Create DataFrame for easier time-based aggregation
    df_curve = pd.DataFrame({"time": time_index, "demand": total_curve})

    # Extract month & day
    df_curve["month"] = df_curve["time"].dt.month
    df_curve["day"] = df_curve["time"].dt.date

    # Find the day with the highest total demand per month
    daily_max_peaks = df_curve.groupby(["month", "day"])["demand"].max()  # Max point each day
    peak_days = daily_max_peaks.groupby("month").idxmax()  # Day with the highest peak in the month

    # Store full 24-hour load curve for each peak day
    peak_curves = {}
    for month, peak_day in peak_days.items():
        peak_day_date = peak_day[1]  # Extract only the date part
        df_curve["day"] = df_curve["time"].dt.date  # Extract date properly
        daily_curve = df_curve[df_curve["day"] == peak_day_date].copy()

        # Ensure exactly 96 points (24 hours at 15-min intervals)
        if len(daily_curve) != 96:
            print(f"Incomplete daily curve for {feeder} month {month}, skipping...")
            continue

        peak_curves[month] = {
            "date": peak_day,
            "curve": daily_curve["demand"].to_numpy()
        }
    return peak_curves, df_curve


def peak_daily_frame(peak_load_curves):
    """One row per feeder and month: Feeder, Month, Peak Day, Point_0 to Point_95."""
    records = []
    for feeder, months in peak_load_curves.items():
        for month, data in months.items():
            records.append([feeder, month, data["date"], *data["curve"]])

    columns = ["Feeder", "Month", "Peak Day"] + [f"Point_{i}" for i in range(96)]
    return pd.DataFrame(records, columns=columns)


def season_peak_row(df_peak_daily, feeder, months):
    """The row of df_peak_daily for feeder whose month is in months and whose highest
    point is the highest; None when the feeder has no such month."""
    df_feeder = df_peak_daily[df_peak_daily["Feeder"] == feeder]
    df_season = df_feeder[df_feeder["Month"].isin(months)]
    if df_season.empty:
        return None
    return df_season.loc[df_season.iloc[:, 3:].max(axis=1).idxmax()]


def cut_peak_day(feeder, df_rows, target_date, output_dir, season):
    """Write the rows of every parquet in df_rows whose timestamp month and day equal
    target_date (any year) to output_dir/<Parquet_File>. An empty day exits 1 (winter)
    or 3 (summer); an unreadable parquet exits 2 (winter) or 4 (summer)."""
    exit_empty, exit_read = (1, 2) if season == "winter" else (3, 4)
    os.makedirs(output_dir, exist_ok=True)
    for _, row in df_rows.iterrows():
        parquet_path = PARQUET_DATA_ROOT / row['Parquet_Folder'] / row['Parquet_File']
        try:
            table = pq.read_table(parquet_path)
            df_full = table.to_pandas()
            df_full["timestamp"] = pd.to_datetime(df_full["timestamp"])

            # Extract target day/month from peak date (ignore year)
            target_month = target_date.month
            target_day = target_date.day

            # Filter by month and day only (ignore year)
            df_day = df_full[(df_full["timestamp"].dt.month == target_month) &
                            (df_full["timestamp"].dt.day == target_day)]

            out_path = os.path.join(output_dir, row['Parquet_File'])
            if not df_day.empty:
                df_day.to_parquet(out_path, index=False)
            else:
                print(f"Emptiness for {season.upper()} day for {feeder} to {out_path}")
                sys.exit(exit_empty)
        except Exception as e:
            print(f"{season.capitalize()} error reading {parquet_path}: {e}")
            sys.exit(exit_read)


# --mix: heating group label in Phase 7b, scenario name in Phases 5b to 5d, folder suffix
MIX_GROUPS = (("baseline", "baseline", ""), ("dm", "dm", "_dm"), ("un", "uncontrolled", "_uncontrolled"))
ENERGY_COL = "out.electricity.total.energy_consumption"


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _upsert_rows(path, mix_name, df_new):
    """Write df_new into the CSV at path in place of that file's rows of mix_name. Values
    already in the file are kept as written. Returns this mix's rows as strings."""
    new_text = df_new.to_csv(index=False)
    df_new_str = pd.read_csv(io.StringIO(new_text), dtype=str, keep_default_na=False)
    if os.path.exists(path):
        df_old = pd.read_csv(path, dtype=str, keep_default_na=False)
        df_old = df_old[df_old["Mix"] != mix_name]
        df_new_str = pd.concat([df_old, df_new_str], ignore_index=True)
    df_new_str.to_csv(path, index=False)
    return df_new_str[df_new_str["Mix"] == mix_name]


def run_mix(mix_name):
    """Find day X for every feeder and season of mix_name, then cut its profiles (see
    the module docstring)."""
    rule = peak_day_rule(cfg)
    if rule != "per_circuit":
        print(f"[mix_days] peak_day_rule is {rule}: mix {mix_name} skipped, nothing written.")
        return
    with open(cfg["mixes_file"], "r", encoding="utf-8") as f:
        mixes = json.load(f)
    if mix_name not in mixes:
        _fail(f"mix {mix_name!r} is not in {cfg['mixes_file']}.")
    mix_cfg = mixes[mix_name]
    shares = mix_cfg['shares']
    heating_seed = int(mix_cfg.get('heating_seed', 123))  # same default as Phase 7b

    # Feeders as Phase 7b finds them
    registry = load_feeder_registry()
    smartds_root = resolve_config_path(cfg['smart_ds_root'])
    skip_circuits = {int(n) for n in cfg.get('skip_circuits', [])}
    feeders = []
    for entry in registry["feeders"]:
        child = smartds_root / Path(entry["original_path"])
        names = {nm.lower() for nm in os.listdir(child)} if child.is_dir() else set()
        if "loads.dss" not in names or "loadshapes.dss" not in names:
            continue
        if int(entry["circuit_id"]) in skip_circuits:
            continue
        feeders.append(child)
    if cfg.get('max_feeders') is not None:
        feeders = feeders[:int(cfg.get('max_feeders'))]

    maps, reqs = {}, {}
    for label, scen, _ in MIX_GROUPS:
        if scen == "baseline":
            map_path = resolve_work_path("5b_profile_generation", f"{STATE}_parquet_and_bldgs.csv")
        else:
            map_path = resolve_work_path("5d_scenario_controls", "get_scenario_csv_controls",
                                         f"{STATE}_parquet_and_bldgs_{scen}.csv")
        mp = pd.read_csv(map_path, usecols=["Feeder", "Parquet_Name", "Parquet_File", "REAL_LOAD_COUNT"])
        mp["building"] = mp["Parquet_Name"].map(lambda v: os.path.splitext(v)[0])
        maps[label] = mp
        req_dir, req_suffix = SCENARIO_INPUTS[scen]
        reqs[label] = pd.read_csv(resolve_work_path(req_dir, STR_STATE + req_suffix))

    label_rows, weight_rows = [], []
    mix_peak_curves = {}
    n_buildings = n_count_diff = 0
    for feeder_dir in feeders:
        substation_name = feeder_dir.parent.name
        feeder_name = feeder_dir.name
        loads_src = None
        for nm in os.listdir(feeder_dir):
            if nm.lower() == 'loads.dss':
                loads_src = feeder_dir / nm

        # 1) Labels, as Phase 7b gives them
        unique_bases, base_to_daily = read_loads(loads_src)
        heat = split_heating(unique_bases, base_to_daily, shares, heating_seed,
                             substation_name, feeder_name)
        daily_to_scen = heat["daily_to_scen"]
        loads_of = {}
        for base in sorted(base_to_daily):
            for ls in sorted(base_to_daily[base]):
                loads_of.setdefault(ls, []).append(base)

        # 2) and 3) Buildings and weights per group and parquet file
        weights = {label: {} for label, _, _ in MIX_GROUPS}
        no_building = []
        for ls in sorted(loads_of):
            loads = loads_of[ls]
            # Phase 7b takes a loadshape's CSV from daily_to_scen, baseline when absent
            load_labels = [daily_to_scen.get(ls, 'baseline') for _ in loads]
            m = re.match(r"^(.+)_kw_(.+)_pu$", ls)
            building = f"{m.group(1)}_{m.group(2)}" if m else None
            found = {}
            for label, _, _ in MIX_GROUPS:
                mp = maps[label]
                hit = mp[(mp["Feeder"] == feeder_name) & (mp["building"] == building)]
                if len(hit) > 1:
                    _fail(f"building {building} has {len(hit)} rows for feeder {feeder_name} "
                          f"in the {label} mapping.")
                if len(hit) == 1:
                    found[label] = hit.iloc[0]
            if not found:
                no_building.append(ls)
                label_rows.append([feeder_name, mix_name, ls, load_labels[0], len(loads), "", ""])
                continue
            n_buildings += 1
            for label in sorted(set(load_labels)):
                if label not in found:
                    _fail(f"load {loads[0]} (loadshape {ls}) is labelled {label}, but building "
                          f"{building} is not in the {label} mapping for feeder {feeder_name}.")
            first = found[load_labels[0]]
            rlc = int(first["REAL_LOAD_COUNT"])
            if rlc != len(loads):
                n_count_diff += 1
            label_rows.append([feeder_name, mix_name, ls, load_labels[0], len(loads),
                               first["Parquet_Name"], rlc])
            for label, _, _ in MIX_GROUPS:
                n_g = sum(1 for lab in load_labels if lab == label)
                if n_g == 0:
                    continue
                row = found[label]
                pfile = row["Parquet_File"]
                rq = reqs[label]
                if not ((rq["Feeder"] == feeder_name) & (rq["Parquet_File"] == pfile)).any():
                    _fail(f"{pfile} of building {building} is not in the {label} required-parquet "
                          f"list for feeder {feeder_name}.")
                w = int(row["REAL_LOAD_COUNT"]) * (n_g / len(loads))
                weights[label][pfile] = weights[label].get(pfile, 0.0) + w
        if no_building:
            print(f"[mix_days] {feeder_name}: {len(no_building)} loadshape(s) with no building in "
                  f"any group, left out of the curve: {', '.join(no_building)}")

        # 4) Feeder curve
        total_curve = None
        for label, scen, _ in MIX_GROUPS:
            rq = reqs[label]
            for _, row in rq[rq["Feeder"] == feeder_name].iterrows():
                w = weights[label].get(row["Parquet_File"], 0.0)
                if w == 0:
                    continue
                weight_rows.append([feeder_name, mix_name, label, row["Parquet_File"], w])
                parquet_path = PARQUET_DATA_ROOT / row['Parquet_Folder'] / row['Parquet_File']
                try:
                    table = pq.read_table(parquet_path, columns=[ENERGY_COL])
                except Exception as e:
                    print(f"Error reading {parquet_path}: {e}")
                    continue
                power_demand = table[ENERGY_COL].to_numpy() * 4
                scaled_demand = power_demand * w
                if total_curve is None:
                    total_curve = scaled_demand
                else:
                    total_curve += scaled_demand
        if total_curve is not None:
            mix_peak_curves[feeder_name], _ = monthly_peak_curves(feeder_name, total_curve)

    # 5) Day X per feeder and season
    df_peak_mix = peak_daily_frame(mix_peak_curves)
    day_rows, day_x = [], {}
    for feeder in df_peak_mix["Feeder"].unique():
        for season, months in (("winter", WINTER_MONTHS), ("summer", SUMMER_MONTHS)):
            peak = season_peak_row(df_peak_mix, feeder, months)
            if peak is None:
                continue
            peak_date = peak["Peak Day"][1]
            day_x[(feeder, season)] = peak_date
            day_rows.append([feeder, season, mix_name, peak_date.month, peak_date.day, max(peak[3:])])
            print(f"[mix_days] {mix_name} {feeder} {season}: day X {peak_date.month:02d}-"
                  f"{peak_date.day:02d}, Peak_kW {max(peak[3:]):.2f}")

    out_dir = resolve_work_path("mix_days")
    os.makedirs(out_dir, exist_ok=True)
    days_path = os.path.join(out_dir, f"{STR_STATE}_circuit_days.csv")
    written = _upsert_rows(days_path, mix_name, pd.DataFrame(
        day_rows, columns=["Feeder", "Season", "Mix", "Month", "Day", "Peak_kW"]))
    _upsert_rows(os.path.join(out_dir, f"{STR_STATE}_circuit_labels.csv"), mix_name, pd.DataFrame(
        label_rows, columns=["Feeder", "Mix", "daily_name", "scenario", "n_loads",
                             "Parquet_Name", "REAL_LOAD_COUNT"]))
    _upsert_rows(os.path.join(out_dir, f"{STR_STATE}_circuit_weights.csv"), mix_name, pd.DataFrame(
        weight_rows, columns=["Feeder", "Mix", "Group", "Parquet_File", "Weight"]))
    print(f"[mix_days] {mix_name}: {n_buildings} buildings, {n_count_diff} with a load count "
          f"different from REAL_LOAD_COUNT. Written: {days_path}")

    # 6) Baseline check, or the cut on day X
    if is_baseline_only(shares):
        peak_days_path = resolve_work_path("5b_profile_generation", STR_STATE + "_peak_days.csv")
        ref = pd.read_csv(peak_days_path, dtype=str, keep_default_na=False)
        ref_keys = {(r.Feeder, r.Season): (r.Month, r.Day, r.Peak_kW) for r in ref.itertuples()}
        got_keys = {(r.Feeder, r.Season): (r.Month, r.Day, r.Peak_kW) for r in written.itertuples()}
        if ref_keys != got_keys:
            for key in sorted(set(ref_keys) | set(got_keys)):
                if ref_keys.get(key) != got_keys.get(key):
                    print(f"[FAIL] baseline check, {key[0]} {key[1]}: {STR_STATE}_peak_days.csv "
                          f"{ref_keys.get(key)}, mix {mix_name} {got_keys.get(key)}")
            sys.exit(1)
        for key in sorted(ref_keys):
            print(f"[mix_days] baseline check passed: mix {mix_name}, {key[0]} {key[1]}, "
                  f"month {ref_keys[key][0]} day {ref_keys[key][1]} Peak_kW {ref_keys[key][2]}")
        return

    for label, scen, suffix in MIX_GROUPS:
        rq = reqs[label]
        for (feeder, season), target_date in day_x.items():
            output_leaf = f"{STR_STATE}_{feeder.replace('--', '_')}_{season}{suffix}"
            output_dir = resolve_work_path("mix_days", mix_name, "5b_profile_generation",
                                           "daily_parquets", output_leaf)
            cut_peak_day(feeder, rq[rq["Feeder"] == feeder], target_date, output_dir, season)
    print(f"[mix_days] {mix_name}: profiles cut on day X under {resolve_work_path('mix_days', mix_name)}")


if ARGS.mix is not None:
    run_mix(ARGS.mix)
    sys.exit(0)

# 🔹 NEW: Store df_curve per feeder
df_curve_per_feeder = {}  # 🔹 NEW

# Load required parquet summary
_input_dir, _input_suffix = SCENARIO_INPUTS[ARGS.scenario]
df_summary_result = pd.read_csv(
    resolve_work_path(_input_dir, STR_STATE + _input_suffix)
)

# Dictionary to store peak daily curves per month per feeder
peak_load_curves = {}

# Dictionary to store max loads per month per feeder
max_load_per_month = {}

# Iterate per substation (Feeder)
for feeder in df_summary_result["Feeder"].unique():
    print(f"Processing feeder: {feeder}")

    # Filter data for current feeder
    df_feeder = df_summary_result[df_summary_result["Feeder"] == feeder]

    # Initialize total load curve (empty array to accumulate)
    total_curve = None

    # Iterate through each load profile in the feeder
    for _, row in df_feeder.iterrows():
        # parquet_path = './' + row["Parquet_Folder"] + '/' + row["Parquet_File"]
        parquet_path = PARQUET_DATA_ROOT / row['Parquet_Folder'] / row['Parquet_File']

        # print('Check path')
        # sys.exit()

        try:
            # Read parquet file
            table = pq.read_table(parquet_path)
            # print("FOUND")
            '''
            USE THIS WHEN WANTING TO ADD MORE COLUMNS
            
            df = table.to_pandas()
            x = df.columns.tolist()
            '''
        except Exception as e:
            print(f"Error reading {parquet_path}: {e}")
            table = 'Nothing'
            continue

        if table != 'Nothing':
            # Extract "total demand" column (UPDATE this with correct column name)
            energy_consumption = table["out.electricity.total.energy_consumption"].to_numpy()

            # This is needed if we assume the above is power times 0.25
            power_demand = energy_consumption * 4

            # print('FIND IF WE REACHED HERE PLEASE')
            # sys.exit()

            # Scale demand curve by REAL_LOAD_COUNT
            scaled_demand = power_demand * row["REAL_LOAD_COUNT"]

            # Accumulate demand curve
            if total_curve is None:
                total_curve = scaled_demand
            else:
                total_curve += scaled_demand



    # Once all loads are accumulated for this feeder, compute peak daily curves
    if total_curve is not None:
        peak_curves, df_curve = monthly_peak_curves(feeder, total_curve)

        # Store results for the feeder
        peak_load_curves[feeder] = peak_curves

        # Inside your main feeder loop (after df_curve is created)
        df_curve_per_feeder[feeder] = df_curve.copy()  # 🔹 NEW

# Convert results into structured DataFrame
df_peak_daily = peak_daily_frame(peak_load_curves)

import matplotlib.pyplot as plt

# Define month names for better readability
month_names = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

# 🔹 NEW: Loop through each feeder for plotting
for feeder, df_curve in df_curve_per_feeder.items():  #
    # Create subplots (3x4 grid for 12 months)
    fig, axes = plt.subplots(3, 4, figsize=(20, 12), sharex=True, sharey=True)
    axes = axes.flatten()

    # Time labels (15-min intervals over 24 hours)
    time_labels = [f"{h}:00" for h in range(0, 24)]

    # Generate 12 spaghetti plots, one per month
    for i, month in enumerate(range(1, 13)):
        ax = axes[i]

        # Filter all daily curves for the current month from `df_curve`
        df_month = df_curve[df_curve["month"] == month]

        # Plot all daily curves (background)
        for day in df_month["day"].unique():
            daily_curve = df_month[df_month["day"] == day]["demand"].to_numpy()
            if len(daily_curve) == 96:  # Ensure correct shape
                ax.plot(range(96), daily_curve, alpha=0.2, color="gray")  # Light gray for all curves

        # Filter data for the current month
        df_peak_month  = df_peak_daily[(df_peak_daily["Month"] == month) & (df_peak_daily["Feeder"] == feeder)]  # 🔹 NEW

        # Plot the maximum peak curve in bold for distinction
        if not df_peak_month.empty:
            max_peak_row = df_peak_month.loc[df_peak_month["Peak Day"].idxmax()]
            max_peak_curve = max_peak_row[3:].to_numpy()
            ax.plot(range(96), max_peak_curve, alpha=1.0, color="red", linewidth=2, label="Max Peak")

        # Formatting
        ax.set_xticks(range(0, 96, 8))
        ax.set_xticklabels(time_labels[::2], rotation=45)
        ax.set_title(f"{month_names[month]}")
        ax.set_ylabel("Demand (kW)")
        ax.grid(True, linestyle="--", alpha=0.5)

    # Overall figure adjustments
    fig.suptitle(f"Peak Daily Curves per Month (Spaghetti Plots) – Feeder: {feeder}", fontsize=16)
    fig.tight_layout()
    if SHOW_PLOTS:
        plt.show()
    else:
        plt.close(fig)

# Display results
# import ace_tools as tools
# tools.display_dataframe_to_user(name="Max Load per Month per Feeder", dataframe=df_max_loads)

# 🔹 NEW: Identify winter and summer peak days per feeder
print("\n🔍 Peak Days Summary (Winter & Summer):\n")  # 🔹 NEW
peak_day_rows = []  # one row per feeder and season, written for the baseline scenario
for feeder in df_peak_daily["Feeder"].unique():  # 🔹 NEW
    # Winter months
    winter_peak = season_peak_row(df_peak_daily, feeder, WINTER_MONTHS)  # Highest single point in winter
    if winter_peak is not None:
        winter_peak_value = max(winter_peak[3:])  # 🔹 NEW: Get max kW in curve
        print(f"Feeder {feeder} - ❄️ Winter Peak Day: {winter_peak['Peak Day']} (Month {winter_peak['Month']}) – Peak Value: {winter_peak_value:.2f} kW")  # 🔹 NEW
        peak_day_rows.append([feeder, "winter", winter_peak["Peak Day"][1].month,
                              winter_peak["Peak Day"][1].day, winter_peak_value])

    # Summer months
    summer_peak = season_peak_row(df_peak_daily, feeder, SUMMER_MONTHS)
    if summer_peak is not None:
        summer_peak_value = max(summer_peak[3:])  # 🔹 NEW: Get max kW in curve
        print(f"Feeder {feeder} - ☀️ Summer Peak Day: {summer_peak['Peak Day']} (Month {summer_peak['Month']}) – Peak Value: {summer_peak_value:.2f} kW")  # 🔹 NEW
        peak_day_rows.append([feeder, "summer", summer_peak["Peak Day"][1].month,
                              summer_peak["Peak Day"][1].day, summer_peak_value])

# Record of the baseline peak days (month and day; the year is ignored downstream).
# Phase 7 takes each circuit's PV daily shape from this date.
if ARGS.scenario == "baseline":
    peak_days_path = resolve_work_path("5b_profile_generation", STR_STATE + "_peak_days.csv")
    pd.DataFrame(peak_day_rows, columns=["Feeder", "Season", "Month", "Day", "Peak_kW"]).to_csv(
        peak_days_path, index=False)
    print(f"Peak days written: {peak_days_path}")

# 🔁 Slicing and saving only winter/summer peak day parquets
BOOL_SAVE_SLICES = True
if BOOL_SAVE_SLICES:
    for feeder in df_peak_daily["Feeder"].unique():
        df_feeder_rows = df_summary_result[df_summary_result["Feeder"] == feeder]
        for season, months in (("winter", WINTER_MONTHS), ("summer", SUMMER_MONTHS)):
            season_peak = season_peak_row(df_peak_daily, feeder, months)
            if season_peak is None:
                continue
            output_leaf = f"{STR_STATE}_{feeder.replace('--', '_')}_{season}{_SCEN_SUFFIX}"
            output_dir = resolve_work_path("5b_profile_generation", "daily_parquets", output_leaf)
            cut_peak_day(feeder, df_feeder_rows, season_peak["Peak Day"][1], output_dir, season)


END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')

