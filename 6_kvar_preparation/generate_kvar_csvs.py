# -*- coding: utf-8 -*-
"""
Created on Sat Apr  5 22:25:38 2025

@author: luisfernando
"""

import os
import pandas as pd
import pickle
import numpy as np
import sys
import time

START_PROCESS = time.time()

# Folder where the kW CSVs are
base_csv_folder = "./"

# Load the pickle of ratios (from Script 2b)
with open("kvar_ratios.pkl", "rb") as f:
    kvar_ratios = pickle.load(f)

folder_list = [i for i in os.listdir(base_csv_folder) if '.' not in i]

# Loop through folders inside daily_csv
for folder_name in folder_list:
   
    folder_path = os.path.join(base_csv_folder, folder_name)
    if not os.path.isdir(folder_path):
        continue

    print(f"📂 Processing folder: {folder_name}")

    # print("debug here - folder_name")
    # sys.exit()

    # Loop through all *_kw_*.csv files
    for fname in os.listdir(folder_path):
        if "_kw_" not in fname or not fname.endswith(".csv"):
            continue

        kw_csv_path = os.path.join(folder_path, fname)

        # Read kW values
        kw_values = pd.read_csv(kw_csv_path, header=None).iloc[:, 0].to_numpy()

        # Infer parquet name from kw filename
        # e.g. com_kw_12774_pu.csv → com_12774.parquet
        name_parts = fname.replace(".csv", "").split("_")
        prefix = name_parts[0]  # com or res
        id_part = name_parts[2]
        parquet_name = f"{prefix}_{id_part}.parquet"

        # Retrieve ratio
        if parquet_name not in list(kvar_ratios.keys()):
            print(f"⚠️ Missing ratio for {parquet_name}, skipping.")
            sys.exit()
            # continue

        ratio_list = kvar_ratios[parquet_name][folder_name]
        ratio_arr = np.array(ratio_list)
        if len(ratio_arr) != 96 or len(kw_values) != 96:
            print(f"⚠️ Length mismatch in {fname}, skipping.")
            sys.exit()
            # continue

        # Calculate kvar = kw * ratio
        kvar_values = kw_values * ratio_arr

        # Round both for visual clarity
        kvar_values = np.round(kvar_values, 4)

        # Save as *_kvar_*.csv
        kvar_fname = fname.replace("_kw_", "_kvar_")
        kvar_path = os.path.join(folder_path, kvar_fname)

        # print("debug here - folder_name - fname")
        # sys.exit()

        pd.DataFrame(kvar_values).to_csv(kvar_path, index=False, header=False)

print("✅ Finished generating kvar CSVs!")

END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} seconds")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')
