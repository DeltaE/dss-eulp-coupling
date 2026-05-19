# -*- coding: utf-8 -*-
"""
Created on Mon Mar 24 00:41:05 2025

@author: luisfernando
"""

import pandas as pd
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, load_feeder_registry

START_PROCESS = time.time()

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
DOWNLOAD_DATE = cfg.get('eulp_download_date', '20250330')
STR_STATE = STATE
registry = load_feeder_registry()

# Load SUMMARY_COPY_PASTE sheet from parsed_loads_PIVOT.xlsx
summary_file = "parsed_loads_PIVOT.xlsx"
df_summary = pd.read_excel(summary_file, sheet_name="SUMMARY_COPY_PASTE")

# Load commercial and residential mapping files
commercial_file = STR_STATE + "_final_commercial.csv"
residential_file = STR_STATE + "_final_residential.csv"
df_commercial = pd.read_csv(commercial_file)
df_residential = pd.read_csv(residential_file)

relevant_feeders = [entry["feeder_name"] for entry in registry["feeders"]]

df_filtered = df_summary[df_summary["Feeder"].isin(relevant_feeders)].copy()

# Create new column safely using `.assign()` instead of modifying a slice
df_filtered = df_filtered.assign(Parquet_Name=df_filtered["Yearly_Type"] + "_" + df_filtered["Yearly_Number"].astype(str) + ".parquet")

# Initialize empty list to store results
merged_results = []

# Iterate over each feeder separately
for feeder in relevant_feeders:
    df_feeder = df_filtered[df_filtered["Feeder"] == feeder].copy()  # Ensure it's a copy

    # print('get here')
    # sys.exit()

    # Merge with final_commercial and final_residential to get bldg_id
    commercial_merged_raw = df_feeder.merge(df_commercial, left_on=["Parquet_Name"], right_on=["Chosen_Parquet"], how="left")
    residential_merged_raw = df_feeder.merge(df_residential, left_on=["Parquet_Name"], right_on=["Chosen_Parquet"], how="left")

    # Count before dropping NaNs
    initial_commercial_rows = len(commercial_merged_raw)
    initial_residential_rows = len(residential_merged_raw)

    # Drop NaNs from critical columns
    commercial_merged = commercial_merged_raw.dropna(subset=["bldg_id"]).copy()
    residential_merged = residential_merged_raw.dropna(subset=["bldg_id"]).copy()

    # Count dropped rows
    dropped_commercial_rows = initial_commercial_rows - len(commercial_merged)
    dropped_residential_rows = initial_residential_rows - len(residential_merged)

    # Assign folder paths using `.assign()`
    commercial_merged = commercial_merged.assign(Parquet_Folder="parquet_commercial_" + DOWNLOAD_DATE + "_comm_" + STR_STATE)
    residential_merged = residential_merged.assign(Parquet_Folder="parquet_residential_short_" + DOWNLOAD_DATE + "_" + STR_STATE)

    residential_merged_index = residential_merged.index.tolist()
    residential_merged_index_len = len(residential_merged_index)
    commercial_merged_index = commercial_merged.index.tolist()
    commercial_merged_index_len = len(commercial_merged_index)

    # Combine results
    merged_results.append(commercial_merged)
    merged_results.append(residential_merged)

    print(f"Feeder: {feeder}")
    print(f"Dropped commercial rows (residential complement): {dropped_commercial_rows} | {residential_merged_index_len}")
    print(f"Dropped residential rows (commercial complement): {dropped_residential_rows} | {commercial_merged_index_len}")
    print('\n')

    # print('check it up until here 1')
    # sys.exit()

# print('check it up until here 2')
# sys.exit()

# Concatenate all processed feeder results
df_result = pd.concat(merged_results, ignore_index=True)

# Extract parquet filename format (from bldg_id)
def extract_parquet_filename(bldg_id):
    if pd.notna(bldg_id):
        return f"{int(bldg_id)}-0.parquet"  # Convert to integer before formatting
    return None

df_result["Parquet_File"] = df_result["bldg_id"].apply(extract_parquet_filename)

# Save results of detailed merged
df_result.to_csv(STR_STATE + "_parquet_and_bldgs.csv", index=False)

# print('what happened up until here')
# sys.exit()

# Aggregate how many times each parquet file is needed per feeder
df_summary_result = df_result.groupby(["Feeder", "Parquet_Folder", "Parquet_File"])['REAL_LOAD_COUNT'].sum().reset_index()

# Save results
df_summary_result.to_csv(STR_STATE + "_required_parquets_per_feeder.csv", index=False)

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')

