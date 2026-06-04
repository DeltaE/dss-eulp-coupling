# -*- coding: utf-8 -*-
"""
Created on Wed Apr  9 17:28:19 2025

@author: luisfernando
"""

import os
import glob
import pandas as pd
import time
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config

START_PROCESS = time.time()

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
DOWNLOAD_DATE = cfg.get('eulp_download_date', '20250330')
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PARQUET_DATA_ROOT = Path(cfg.get('parquet_data_root', '../parquet_data'))
if not PARQUET_DATA_ROOT.is_absolute():
    PARQUET_DATA_ROOT = (REPO_ROOT / PARQUET_DATA_ROOT).resolve()

# Create output folder if it doesn't exist
output_folder = SCRIPT_DIR / "plot_parquet_differences"
output_folder.mkdir(exist_ok=True)

# Define which scenario IDs are baseline, uncontrolled, demand_mgmt for each building type
residential_ids = {
    "baseline": ["0"],
    "uncontrolled": ["1"],  # only one possibility
    "demand_management": ["4"]  # only one possibility
}

commercial_ids = {
    "baseline": ["0"],
    "uncontrolled": ["1", "8"],  # pick whichever has largest abs diff from baseline
    "demand_management": ["2", "9", "20"]  # pick largest abs diff from baseline
}

# Scenario name lookups
residential_names = {
    "0": "Baseline",
    "1": "ENERGY STAR heat pump with elec backup",
    "4": "ENERGY STAR heat pump with existing system as backup",
}

commercial_names = {
    "0": "Baseline",
    "1": "Variable Speed HP RTU, Electric Backup",
    "2": "Variable Speed HP RTU, Original Heating Fuel Backup",
    "8": "HP Boiler, Electric Backup",
    "9": "HP Boiler, Gas Backup"
}

# Folders to process
folders = [
    PARQUET_DATA_ROOT / ("parquet_commercial_" + DOWNLOAD_DATE + "_comm_" + STATE),
    PARQUET_DATA_ROOT / ("parquet_residential_short_" + DOWNLOAD_DATE + "_" + STATE)
]

# We'll keep partial results in a dict: 
# keys = (folder, building_id, scenario_id), value = sum of demand
sum_demand_dict = {}

# -----------------------------
# Step 1: Read all parquets and gather sums
# -----------------------------
for folder_path in folders:
    folder = folder_path.name
    # print('stop')
    # sys.exit()
    print(folder)
    # Figure out if this is residential or commercial
    is_residential = "residential" in folder.lower()

    # Get all parquet files
    parquet_files = glob.glob(os.path.join(folder_path, "*.parquet"))
    
    # print('got up until here')
    # sys.exit()
    
    for fpath in parquet_files:
        fname = os.path.basename(fpath)
        # Example: "68646-0.parquet" => building_id="68646", scenario_id="0"
        if not fname.endswith(".parquet"):
            print('happens? 1')
            continue
        parts = fname[:-8].split("-")  # remove ".parquet", then split by "-"
        if len(parts) != 2:
            print('happens? 2')
            continue
        building_id, scenario_id = parts

        # If residential and scenario not in residential_names, skip
        # If commercial and scenario not in commercial_names, skip
        allowed_residential_ids = list(set(residential_names.keys()))
        if is_residential and (scenario_id not in allowed_residential_ids):
            # print('happens? 3')
            continue
        # else:
            # print('nothings')
        allowed_commercial_ids = list(set(commercial_names.keys()))
        if not is_residential and (scenario_id not in commercial_names):
            # print('happens? 4')
            continue

        # Read the parquet
        df = pd.read_parquet(fpath)
        # Extract "out.electricity.total.energy_consumption" column
        energy_consumption = df["out.electricity.total.energy_consumption"].to_numpy()
        # Convert from kWh in each 15-minute interval to kW by multiplying by 4
        power_demand = energy_consumption * 4
        # Sum it
        total_power_demand = power_demand.sum()

        sum_demand_dict[(folder, building_id, scenario_id)] = total_power_demand

print('\n Finish when this is done.\n')

# -----------------------------
# Step 2: Build final records for each (folder, building_id)
# picking baseline + best uncontrolled + best demand_management
# -----------------------------
final_rows = []

for folder_path in folders:
    folder = folder_path.name
    print(folder)
    is_residential = "residential" in folder.lower()
    if is_residential:
        scenario_ids = residential_ids
        scenario_names = residential_names
    else:
        scenario_ids = commercial_ids
        scenario_names = commercial_names

    building_ids_in_folder = set()
    for (fold, bldg, sid) in sum_demand_dict.keys():
        if fold == folder:
            building_ids_in_folder.add(bldg)

    for bldg_id in building_ids_in_folder:
        row = {
            "folder": folder,
            "building_id": bldg_id,
            "baseline_demand": np.nan,
            "uncontrolled_demand": np.nan,
            "demand_management_demand": np.nan,
            "uncontrolled_scenario_name": "",
            "demand_management_scenario_name": "",
            "uncontrolled_diff": np.nan,
            "demand_management_diff": np.nan
        }

        # Get baseline
        baseline_key = (folder, bldg_id, "0")
        if baseline_key in sum_demand_dict:
            baseline_sum = sum_demand_dict[baseline_key]
            row["baseline_demand"] = baseline_sum
        else:
            continue  # Skip if no baseline

        # Best uncontrolled (largest absolute difference from baseline)
        best_uncontrolled_id = None
        best_uncontrolled_diff = None
        for sid in scenario_ids["uncontrolled"]:
            key = (folder, bldg_id, sid)
            if key in sum_demand_dict:
                val = sum_demand_dict[key]
                diff = abs(val - baseline_sum)
                if (best_uncontrolled_id is None) or (diff > best_uncontrolled_diff):
                    best_uncontrolled_id = sid
                    best_uncontrolled_diff = diff

        if best_uncontrolled_id is not None:
            val = sum_demand_dict[(folder, bldg_id, best_uncontrolled_id)]
            row["uncontrolled_demand"] = val
            row["uncontrolled_scenario_name"] = scenario_names[best_uncontrolled_id]
            row["uncontrolled_scenario_id"] = best_uncontrolled_id
            row["uncontrolled_diff"] = val - baseline_sum  # signed difference

        # Demand management: pick the scenario with the **lowest absolute demand**
        best_dm_id = None
        best_dm_val = None
        for sid in scenario_ids["demand_management"]:
            key = (folder, bldg_id, sid)
            if key in sum_demand_dict:
                val = sum_demand_dict[key]
                if (best_dm_id is None) or (val < best_dm_val):
                    best_dm_id = sid
                    best_dm_val = val

        if best_dm_id is not None:
            row["demand_management_demand"] = best_dm_val
            row["demand_management_scenario_name"] = scenario_names[best_dm_id]
            row["demand_management_scenario_id"] = best_dm_id
            row["demand_management_diff"] = best_dm_val - baseline_sum  # signed difference

        final_rows.append(row)

# -----------------------------
# Step 3: Create DataFrame and write CSV
# -----------------------------
df_combined = pd.DataFrame(final_rows)
df_combined.sort_values(by=["folder", "building_id"], inplace=True)

output_path = os.path.join(output_folder, "combined_scenarios.csv")
df_combined.to_csv(output_path, index=False)
print(f"Done! Output CSV at: {output_path}")



END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} seconds")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')


