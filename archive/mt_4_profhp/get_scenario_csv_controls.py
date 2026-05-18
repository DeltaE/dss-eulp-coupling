# -*- coding: utf-8 -*-
"""
Created on Wed Apr  9 18:31:37 2025

@author: luisfernando
"""

import pandas as pd
import os
import sys
import numpy as np
import time

START_PROCESS = time.time()

# Create output folder
output_folder = "get_scenario_csv_controls"
os.makedirs(output_folder, exist_ok=True)

# Load scenario summary
scenario_file = os.path.join("plot_parquet_differences", "combined_scenarios.csv")
if not os.path.exists(scenario_file):
    print(f"❌ Scenario file not found: {scenario_file}")
    sys.exit()

df_scenarios = pd.read_csv(scenario_file)

# Build lookup dictionary
scenario_dict = {}
for _, row in df_scenarios.iterrows():
    folder = row["folder"]
    building_id = str(row["building_id"])
    un_id = str(row.get("uncontrolled_scenario_id", ""))
    dm_id = str(row.get("demand_management_scenario_id", ""))
    scenario_dict[(folder, building_id)] = (un_id, dm_id)

# Define base filenames (without suffix)
base_files = [
    "MT_required_parquets_per_feeder",
    "MT_parquet_and_bldgs"
]

# Process each file
for base in base_files:
    input_path = f"{base}.csv"
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit()

    print(f"✅ Processing: {input_path}")
    df = pd.read_csv(input_path)
    df_un = df.copy()
    df_dm = df.copy()

    if "Parquet_File" not in df.columns or "Parquet_Folder" not in df.columns:
        print(f"⚠️  Missing required columns in {input_path}")
        sys.exit()

    for i in df.index:
        folder = df.at[i, "Parquet_Folder"]
        original_pqt = df.at[i, "Parquet_File"]
        if "-" not in str(original_pqt):
            print(f"⚠️ Invalid Parquet_File format at row {i}: {original_pqt}")
            sys.exit()
        building_id = str(original_pqt).split("-")[0]

        key = (folder, building_id)
        if key in scenario_dict:
            un_id, dm_id = scenario_dict[key]
            df_un.at[i, "Parquet_File"] = f"{building_id}-{un_id}.parquet"
            df_dm.at[i, "Parquet_File"] = f"{building_id}-{dm_id}.parquet"
        else:
            print(f"❌ Building ID {building_id} in folder {folder} not found in scenarios")
            sys.exit()

    # Save to output folder
    un_out = os.path.join(output_folder, f"{base}_uncontrolled.csv")
    dm_out = os.path.join(output_folder, f"{base}_dm.csv")
    df_un.to_csv(un_out, index=False)
    df_dm.to_csv(dm_out, index=False)
    print(f"✅ Wrote: {un_out}")
    print(f"✅ Wrote: {dm_out}")

print("\n🎉 All done! Output in folder:", output_folder)



END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} seconds")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')


