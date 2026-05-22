# -*- coding: utf-8 -*-
"""
Created on Sat Apr  5 16:56:09 2025

@author: luisfernando
"""

# -*- coding: utf-8 -*-
"""
Script 2b: For each original Parquet from 'needed_parquets.pkl', 
extract KW/KVAR ratio for the specific timestamps we used in daily slices.

We'll store ratio arrays (and the associated timestamps) in 'kvar_ratios.pkl'.
"""

import os
import pickle
import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import sys
import time
from pathlib import Path

START_PROCESS = time.time()

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
from pipeline_utils import load_config, resolve_config_path

cfg = load_config()
DEFAULT_SMART_DS_PARQUET_ROOT = REPO_ROOT / "3b_smartds_eulp_match" / "parquet_data"

# Adjust these paths:
needed_parquets_path = "needed_parquets.pkl"
timestamp_pickle      = "folder_timestamps.pkl"
configured_parquet_root = cfg.get("smart_ds_parquet_root")
original_parquet_dir = (
    resolve_config_path(configured_parquet_root)
    if configured_parquet_root
    else DEFAULT_SMART_DS_PARQUET_ROOT.resolve()
)
kvar_ratios_output    = "kvar_ratios.pkl"          # we'll store a dict here

print(f"Using SMART-DS source parquet root: {original_parquet_dir}")

# Columns in original Parquet representing real & reactive energy (kWh / kvarh)
REAL_COL    = "total_site_electricity_kw"
REACTIVE_COL= "total_site_electricity_kvar"

# 1) Load the needed Parquet list
with open(needed_parquets_path, "rb") as f:
    needed_parquets = pickle.load(f)

print(f"Loaded {len(needed_parquets)} needed Parquets from {needed_parquets_path}")

# 2) Load the folder_timestamps from Script #1
with open(timestamp_pickle, "rb") as f:
    folder_timestamps_raw = pickle.load(f)
print(f"Loaded folder_timestamps from {timestamp_pickle}")

# 3) Convert to a simplified version: one time_list per folder  # NEW
folder_timestamps = {}
for folder_name, file_dict in folder_timestamps_raw.items():  # NEW
    try:
        some_list = list(file_dict.values())[0]  # Take any of the values, assuming all are the same  # NEW
        folder_timestamps[folder_name] = some_list  # NEW
    except Exception as e:
        print(f"⚠️ Could not extract timestamps from {folder_name}: {e}")  # NEW
        sys.exit()
        # continue  # NEW

# 4) Prepare to store results
#    kvar_ratios[ "com_12774.parquet" ] = { "some_folder": { "timestamps": [...], "ratios": [...] }, ... }
kvar_ratios = {}

# 5) Main processing loop  # MODIFIED
# for i, (folder_name, time_list) in enumerate(folder_timestamps.items()):  # ✅ same loop
for folder_name, time_list in folder_timestamps.items():  # MODIFIED
    #if i > 0:  # ✅ only allow first iteration
    #    break
    print(f"\n📁 Processing folder: {folder_name}")  # NEW

    for parquet_file in needed_parquets:  # MODIFIED
        full_parquet_path = os.path.join(original_parquet_dir, parquet_file)

        # print('what is the path?')
        # sys.exit()

        if not os.path.exists(full_parquet_path):
            print(f"⚠️ Missing {full_parquet_path}, skipping.")
            sys.exit()
            # continue

        try:
            table = pq.read_table(full_parquet_path, columns=["Time", REAL_COL, REACTIVE_COL])
            df_orig = table.to_pandas()

            col_names = df_orig.columns.tolist()
            # print('what are the columns of this dataframe?')
            # sys.exit()

        except Exception as e:
            print(f"⚠️ Error reading {full_parquet_path}: {e}")
            sys.exit()
            # continue

        # Optional debug check
        # print(df_orig.columns.tolist()); sys.exit()

        if REAL_COL not in df_orig.columns or REACTIVE_COL not in df_orig.columns:
            print(f"⚠️ {REAL_COL} or {REACTIVE_COL} missing in {parquet_file}, skipping.")
            sys.exit()
            # continue
        if "Time" not in df_orig.columns:
            print(f"⚠️ 'timestamp' missing in {parquet_file}, skipping.")
            sys.exit()
            # continue

        # df_orig["Time"] = pd.to_datetime(df_orig["Time"])

        # If there's an extra ":00" at the end of the timestamp, fix it
        df_orig["Time"] = df_orig["Time"].astype(str).str.replace(r":\d{2}$", "", regex=True)  # ✅ Remove extra :00
        df_orig["Time"] = pd.to_datetime(df_orig["Time"], errors='coerce')  # ✅ Parse, allow NaT

        arr_ratio = []
        n_missing = 0

        # Ensure time_list is datetime
        time_series = pd.to_datetime(time_list)

        # Filter only the rows with matching timestamps
        df_filtered = df_orig[df_orig["Time"].isin(time_series)].copy()

        # Set index to Time for faster lookup
        df_filtered.set_index("Time", inplace=True)

        # Reindex to match original time_series order, fill missing with NaN
        df_filtered = df_filtered.reindex(time_series)

        # Calculate ratio safely
        ratios = np.where(
            (df_filtered[REAL_COL].abs() > 1e-9) & (~df_filtered[REAL_COL].isna()),
            df_filtered[REACTIVE_COL] / df_filtered[REAL_COL],
            0.0
        )

        arr_ratio = ratios.tolist()
        n_missing = df_filtered[REAL_COL].isna().sum()

        if len(arr_ratio) != 96 or n_missing > 0:
            print('⚠️ Something is odd!')
            sys.exit()

        if parquet_file not in kvar_ratios:
            kvar_ratios[parquet_file] = {}
        kvar_ratios[parquet_file][folder_name] = arr_ratio

        # kvar_ratios[parquet_file][folder_name] = {
        #    "timestamps": time_list,
        #    "ratios": arr_ratio
        #}

        if n_missing:
            print(f"   ⚠️ {n_missing} timestamps missing in {parquet_file} for {folder_name}.")
            sys.exit()

# 6) Store result
with open(kvar_ratios_output, "wb") as f:
    pickle.dump(kvar_ratios, f)

print(f"\n✅ Stored ratio data in {kvar_ratios_output}")

END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} seconds")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')
