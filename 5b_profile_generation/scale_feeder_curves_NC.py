# -*- coding: utf-8 -*-
"""
Created on Mon Mar 24 00:41:05 2025

@author: luisfernando
"""

import pandas as pd
import os
import sys
import time

START_PROCESS = time.time()

STR_STATE = 'NC'

# Load SUMMARY_COPY_PASTE sheet from parsed_loads_PIVOT.xlsx
summary_file = "parsed_loads_PIVOT.xlsx"
df_summary = pd.read_excel(summary_file, sheet_name="SUMMARY_COPY_PASTE")

# Load commercial and residential mapping files
commercial_file = STR_STATE + "_final_commercial.csv"
residential_file = STR_STATE + "_final_residential.csv"
df_commercial = pd.read_csv(commercial_file)
df_residential = pd.read_csv(residential_file)

# Extract relevant feeders from the provided image
relevant_feeders = [
    "uhs0_1247--udt12274", "uhs0_1247--udt14717", "uhs0_1247--udt16115",
    "uhs1_1247--udt15926", "uhs1_1247--udt20176",
    "uhs2_1247--udt10746", "uhs2_1247--udt12473", "uhs2_1247--udt9312",
    "uhs3_1247--udt1567", "uhs3_1247--udt1571", "uhs3_1247--udt1582",
    "uhs4_1247--p1umv7", "uhs4_1247--p1umv8", "uhs4_1247--udt11389", "uhs4_1247--udt12982",
    "uhs5_1247--udt159", "uhs5_1247--udt18558", "uhs5_1247--udt19869", "uhs5_1247--udt20368",
    "uhs6_1247--udt10788", "uhs6_1247--udt6570", "uhs6_1247--udt9964",
    "uhs7_1247--udt15849", "uhs7_1247--udt9662", "uhs7_1247--udt9675",
    "uhs8_1247--udt12494", "uhs8_1247--udt7252",
    "uhs9_1247--udt11456", "uhs9_1247--udt13714", "uhs9_1247--udt14110", "uhs9_1247--udt16813", "uhs9_1247--udt2508",
    "uhs10_1247--udt11713", "uhs10_1247--udt12084", "uhs10_1247--udt13528",
    "uhs11_1247--p1umv22", "uhs11_1247--udt7105", "uhs11_1247--udt8110",
    "uhs12_1247--udt1278", "uhs12_1247--udt15482", "uhs12_1247--udt15805", "uhs12_1247--udt17650",
    "uhs13_1247--udt4015", "uhs13_1247--udt4819",
    "uhs14_1247--udt11665", "uhs14_1247--udt12226", "uhs14_1247--udt5493",
    "uhs15_1247--udt19670", "uhs15_1247--udt20824",
    "uhs16_1247--udt15512", "uhs16_1247--udt310",
    "uhs17_1247--udt6592", "uhs17_1247--udt9551",
    "uhs18_1247--udt11616", "uhs18_1247--udt13374", "uhs18_1247--udt17294",
    "uhs19_1247--udt15839", "uhs19_1247--udt19872",
    "uhs20_1247--udt5173", "uhs20_1247--udt8894", "uhs20_1247--udt9897"
]

'''
relevant_feeders = ["uhs0_1247--udt12274"]
'''

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
    commercial_merged = commercial_merged.assign(Parquet_Folder="parquet_commercial_20250330_comm_NC")
    residential_merged = residential_merged.assign(Parquet_Folder="parquet_residential_short_20250330_NC")

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

