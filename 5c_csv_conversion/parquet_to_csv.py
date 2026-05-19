# -*- coding: utf-8 -*-
"""
Created on Sat Apr  5 15:14:51 2025

@author: luisfernando
"""

# -*- coding: utf-8 -*-
"""
Script #1: Convert daily-sliced EULP Parquet files into CSV loadshapes for SMART DS usage.
Output folders are structured as: daily_csv/FL_circuit_1_summer, etc.
"""

import os
import pickle
import pyarrow.parquet as pq
import pandas as pd
import numpy as np
from copy import deepcopy
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, load_feeder_registry

START_PROCESS = time.time()

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
registry = load_feeder_registry()

# ---------------------------------------------------------------------
# 1) Basic setup
# ---------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
base_parquet_dir = os.path.join(SCRIPT_DIR, "..", "5b_profile_generation", "daily_parquets")
if not os.path.exists(base_parquet_dir):
    base_parquet_dir = os.path.join(SCRIPT_DIR, "..", "daily_parquets")

folder_timestamps = {}
folder_equiv = {}
folder_list_loadshapes = {}

# Map from underscored folder name → dashed circuit name
feeder_to_circuit = registry["circuit_name_map"]
feeder_by_folder_key = {
    entry["feeder_name"].replace("--", "_"): entry["feeder_name"]
    for entry in registry["feeders"]
}

# Map from dashed circuit name → circuit_n
# ---------------------------------------------------------------------
# 2) Load the three mapping CSVs
# ---------------------------------------------------------------------

control_output_dir = os.path.join(SCRIPT_DIR, "..", "5d_scenario_controls", "get_scenario_csv_controls")
df_state = pd.read_csv(os.path.join(control_output_dir, f"{STATE}_parquet_and_bldgs_dm.csv"))
df_state["STATE"] = STATE

df_mapping = pd.concat([df_state], ignore_index=True)

required_cols = ["Feeder", "Parquet_File", "Parquet_Name", "STATE"]
missing_cols = [c for c in required_cols if c not in df_mapping.columns]
if missing_cols:
    raise ValueError(f"Missing columns in CSV(s): {missing_cols}")

# ---------------------------------------------------------------------
# 3) Scan subfolders
# ---------------------------------------------------------------------

folder_list = [f for f in os.listdir(base_parquet_dir) 
               if os.path.isdir(os.path.join(base_parquet_dir, f))]

folder_list_raw = deepcopy(folder_list)

folder_list = [i for i in folder_list_raw if 'RES_' not in i]

#folder_list = [folder_list_raw[0]]

for folder_name in folder_list:
    parts = folder_name.split("_")
    if len(parts) < 3:
        print(f"Skipping {folder_name} (unexpected format)")
        # continue
        sys.exit()
    
    state  = parts[0]
    season = parts[-1]
    circuit_underscore = "_".join(parts[1:-1])

    if 'RES_' in circuit_underscore:
        circuit_underscore_orig = deepcopy(circuit_underscore)
        circuit_underscore = circuit_underscore_orig.replace('RES_', '')
    else:
        circuit_underscore_orig = ''

    circuit_dashed = feeder_by_folder_key.get(circuit_underscore, circuit_underscore)
    circuit_id = feeder_to_circuit.get(circuit_dashed, "unknown_circuit")

    if 'RES_' in circuit_underscore_orig:
        # print('stop here')
        # sys.exit()
        circuit_id_orig = deepcopy(circuit_id)
        circuit_id = 'RES_' + circuit_id_orig

    output_folder_name = f"{state}_{circuit_id}_{season}"
    out_folder = os.path.join(output_folder_name)
    os.makedirs(out_folder, exist_ok=True)

    print(f"\n=== Processing folder: {folder_name} ===")
    print(f"   → Writing to: {output_folder_name}")

    df_filtered = df_mapping[
        (df_mapping["STATE"] == state) &
        (df_mapping["Feeder"] == circuit_dashed)
    ].copy()

    if df_filtered.empty:
        print(f"   ⚠️ No rows in mapping for {folder_name}. Skipping.")
        # continue
        sys.exit()

    subfolder_path = os.path.join(base_parquet_dir, folder_name)
    parquet_files  = [p for p in os.listdir(subfolder_path) if p.endswith(".parquet")]

    # Update the system here:
    folder_list_loadshapes.update({folder_name:[]})

    # for parquet_file in parquet_files:
    for n in range(len(df_filtered.index.tolist())):
        '''
        THIS IS COMMENTED BECAUSE THERE WAS AN ERROR WHEN THIS FOR LOOP HAD
        THE FOLLOWING: *for parquet_file in parquet_files* DEFINITION.

        THE NEW DEFINITION IS RELATED TO THE DF_FILTERED

        WHEN THE ERROR WAS ACTIVATED, NOTE WE HAD THAT
        len(df_filtered.index.tolist() > len(parquet_files)
        thus, leaving out some important pieces of information.

        match_rows = df_filtered[df_filtered["Parquet_File"] == parquet_file]
        if match_rows.empty:
            print(f"   ⚠️ No match in CSV for {parquet_file}, skipping.")
            # continue
            sys.exit()
        '''

        row = df_filtered.iloc[n]
        # final_name = row["Parquet_Name"]

        parquet_file = row["Parquet_File"]

        parquet_fullpath = os.path.join(subfolder_path, parquet_file)

        base_name = os.path.splitext(row["Parquet_Name"])[0]  # e.g., "com_12774"

        if base_name not in folder_list_loadshapes[folder_name]:
            folder_list_loadshapes[folder_name].append(base_name)

        # Extract prefix and number
        prefix, num = base_name.split("_")
        final_name = f"{prefix}_kw_{num}_pu"

        # print(parquet_file, ' - ', final_name, ' - ', circuit_dashed)
        # print('\n')

        # print('get up until here')
        # sys.exit()

        try:
            table = pq.read_table(parquet_fullpath)
            df_parq = table.to_pandas()
        except Exception as e:
            print(f"   ⚠️ Error reading {parquet_fullpath}: {e}")
            # continue
            sys.exit()

        if "out.electricity.total.energy_consumption" not in df_parq.columns:
            print(f"   ❌ Missing 'out.electricity.total.energy_consumption' in {parquet_file}, skipping.")
            # continue
            sys.exit()

        df_parq["kw"] = df_parq["out.electricity.total.energy_consumption"] * 4.0

        if "timestamp" in df_parq.columns:
            arr_time = df_parq["timestamp"].astype(str).tolist()
            folder_timestamps.setdefault(output_folder_name, {})[parquet_file] = arr_time
            folder_equiv.setdefault(output_folder_name, {})[parquet_file] = base_name

        arr_kw = df_parq["kw"].values

        kw_csv_name = f"{final_name}.csv"
        kw_csv_path = os.path.join(out_folder, kw_csv_name)
        # np.savetxt(kw_csv_path, arr_kw, delimiter="\n")
        np.savetxt(kw_csv_path, arr_kw, delimiter="\n", fmt="%.4f")

        # print('check how you got up until here')
        # sys.exit()

        print(f"   ✅ Created KW CSV: {kw_csv_path}")

# ---------------------------------------------------------------------
# 4) Save timestamps
# ---------------------------------------------------------------------

if folder_timestamps:
    with open("folder_timestamps.pkl", "wb") as f:
        pickle.dump(folder_timestamps, f)
    print("\n✅ Stored timestamps in folder_timestamps.pkl")

if folder_equiv:
    with open("folder_equiv.pkl", "wb") as f:
        pickle.dump(folder_equiv, f)
    print("\n✅ Stored EQUIVALENCE in folder_equiv.pkl")

if folder_list_loadshapes:
    with open("folder_list_loadshapes.pkl", "wb") as f:
        pickle.dump(folder_list_loadshapes, f)
    print("\n✅ Stored LOADSHAPES in folder_list_loadshapes.pkl")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')
