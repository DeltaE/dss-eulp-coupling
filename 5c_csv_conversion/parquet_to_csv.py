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

START_PROCESS = time.time()

# ---------------------------------------------------------------------
# 1) Basic setup
# ---------------------------------------------------------------------

base_parquet_dir = "../daily_parquets"

folder_timestamps = {}
folder_equiv = {}
folder_list_loadshapes = {}

# Map from underscored folder name → dashed circuit name
CIRCUIT_NAME_MAP = {
    "uhs0_1247_udt12274": "uhs0_1247--udt12274",
    "uhs0_1247_udt14717": "uhs0_1247--udt14717",
    "uhs0_1247_udt16115": "uhs0_1247--udt16115",
    "uhs1_1247_udt15926": "uhs1_1247--udt15926",
    "uhs1_1247_udt20176": "uhs1_1247--udt20176",
    "uhs2_1247_udt10746": "uhs2_1247--udt10746",
    "uhs2_1247_udt12473": "uhs2_1247--udt12473",
    "uhs2_1247_udt9312": "uhs2_1247--udt9312",
    "uhs3_1247_udt1567": "uhs3_1247--udt1567",
    "uhs3_1247_udt1571": "uhs3_1247--udt1571",
    "uhs3_1247_udt1582": "uhs3_1247--udt1582",
    "uhs4_1247_p1umv7": "uhs4_1247--p1umv7",
    "uhs4_1247_p1umv8": "uhs4_1247--p1umv8",
    "uhs4_1247_udt11389": "uhs4_1247--udt11389",
    "uhs4_1247_udt12982": "uhs4_1247--udt12982",
    "uhs5_1247_udt159": "uhs5_1247--udt159",
    "uhs5_1247_udt18558": "uhs5_1247--udt18558",
    "uhs5_1247_udt19869": "uhs5_1247--udt19869",
    "uhs5_1247_udt20368": "uhs5_1247--udt20368",
    "uhs6_1247_udt10788": "uhs6_1247--udt10788",
    "uhs6_1247_udt6570": "uhs6_1247--udt6570",
    "uhs6_1247_udt9964": "uhs6_1247--udt9964",
    "uhs7_1247_udt15849": "uhs7_1247--udt15849",
    "uhs7_1247_udt9662": "uhs7_1247--udt9662",
    "uhs7_1247_udt9675": "uhs7_1247--udt9675",
    "uhs8_1247_udt12494": "uhs8_1247--udt12494",
    "uhs8_1247_udt7252": "uhs8_1247--udt7252",
    "uhs9_1247_udt11456": "uhs9_1247--udt11456",
    "uhs9_1247_udt13714": "uhs9_1247--udt13714",
    "uhs9_1247_udt14110": "uhs9_1247--udt14110",
    "uhs9_1247_udt16813": "uhs9_1247--udt16813",
    "uhs9_1247_udt2508": "uhs9_1247--udt2508",
    "uhs10_1247_udt11713": "uhs10_1247--udt11713",
    "uhs10_1247_udt12084": "uhs10_1247--udt12084",
    "uhs10_1247_udt13528": "uhs10_1247--udt13528",
    "uhs11_1247_p1umv22": "uhs11_1247--p1umv22",
    "uhs11_1247_udt7105": "uhs11_1247--udt7105",
    "uhs11_1247_udt8110": "uhs11_1247--udt8110",
    "uhs12_1247_udt1278": "uhs12_1247--udt1278",
    "uhs12_1247_udt15482": "uhs12_1247--udt15482",
    "uhs12_1247_udt15805": "uhs12_1247--udt15805",
    "uhs12_1247_udt17650": "uhs12_1247--udt17650",
    "uhs13_1247_udt4015": "uhs13_1247--udt4015",
    "uhs13_1247_udt4819": "uhs13_1247--udt4819",
    "uhs14_1247_udt11665": "uhs14_1247--udt11665",
    "uhs14_1247_udt12226": "uhs14_1247--udt12226",
    "uhs14_1247_udt5493": "uhs14_1247--udt5493",
    "uhs15_1247_udt19670": "uhs15_1247--udt19670",
    "uhs15_1247_udt20824": "uhs15_1247--udt20824",
    "uhs16_1247_udt15512": "uhs16_1247--udt15512",
    "uhs16_1247_udt310": "uhs16_1247--udt310",
    "uhs17_1247_udt6592": "uhs17_1247--udt6592",
    "uhs17_1247_udt9551": "uhs17_1247--udt9551",
    "uhs18_1247_udt11616": "uhs18_1247--udt11616",
    "uhs18_1247_udt13374": "uhs18_1247--udt13374",
    "uhs18_1247_udt17294": "uhs18_1247--udt17294",
    "uhs19_1247_udt15839": "uhs19_1247--udt15839",
    "uhs19_1247_udt19872": "uhs19_1247--udt19872",
    "uhs20_1247_udt5173": "uhs20_1247--udt5173",
    "uhs20_1247_udt8894": "uhs20_1247--udt8894",
    "uhs20_1247_udt9897": "uhs20_1247--udt9897",
}

# Map from dashed circuit name → circuit_n
REVERSE_CIRCUIT_MAP = {
    "uhs0_1247--udt12274": "circuit_1",
    "uhs0_1247--udt14717": "circuit_2",
    "uhs0_1247--udt16115": "circuit_3",
    "uhs1_1247--udt15926": "circuit_4",
    "uhs1_1247--udt20176": "circuit_5",
    "uhs2_1247--udt10746": "circuit_6",
    "uhs2_1247--udt12473": "circuit_7",
    "uhs2_1247--udt9312": "circuit_8",
    "uhs3_1247--udt1567": "circuit_9",
    "uhs3_1247--udt1571": "circuit_10",
    "uhs3_1247--udt1582": "circuit_11",
    "uhs4_1247--p1umv7": "circuit_12",
    "uhs4_1247--p1umv8": "circuit_13",
    "uhs4_1247--udt11389": "circuit_14",
    "uhs4_1247--udt12982": "circuit_15",
    "uhs5_1247--udt159": "circuit_16",
    "uhs5_1247--udt18558": "circuit_17",
    "uhs5_1247--udt19869": "circuit_18",
    "uhs5_1247--udt20368": "circuit_19",
    "uhs6_1247--udt10788": "circuit_20",
    "uhs6_1247--udt6570": "circuit_21",
    "uhs6_1247--udt9964": "circuit_22",
    "uhs7_1247--udt15849": "circuit_23",
    "uhs7_1247--udt9662": "circuit_24",
    "uhs7_1247--udt9675": "circuit_25",
    "uhs8_1247--udt12494": "circuit_26",
    "uhs8_1247--udt7252": "circuit_27",
    "uhs9_1247--udt11456": "circuit_28",
    "uhs9_1247--udt13714": "circuit_29",
    "uhs9_1247--udt14110": "circuit_30",
    "uhs9_1247--udt16813": "circuit_31",
    "uhs9_1247--udt2508": "circuit_32",
    "uhs10_1247--udt11713": "circuit_33",
    "uhs10_1247--udt12084": "circuit_34",
    "uhs10_1247--udt13528": "circuit_35",
    "uhs11_1247--p1umv22": "circuit_36",
    "uhs11_1247--udt7105": "circuit_37",
    "uhs11_1247--udt8110": "circuit_38",
    "uhs12_1247--udt1278": "circuit_39",
    "uhs12_1247--udt15482": "circuit_40",
    "uhs12_1247--udt15805": "circuit_41",
    "uhs12_1247--udt17650": "circuit_42",
    "uhs13_1247--udt4015": "circuit_43",
    "uhs13_1247--udt4819": "circuit_44",
    "uhs14_1247--udt11665": "circuit_45",
    "uhs14_1247--udt12226": "circuit_46",
    "uhs14_1247--udt5493": "circuit_47",
    "uhs15_1247--udt19670": "circuit_48",
    "uhs15_1247--udt20824": "circuit_49",
    "uhs16_1247--udt15512": "circuit_50",
    "uhs16_1247--udt310": "circuit_51",
    "uhs17_1247--udt6592": "circuit_52",
    "uhs17_1247--udt9551": "circuit_53",
    "uhs18_1247--udt11616": "circuit_54",
    "uhs18_1247--udt13374": "circuit_55",
    "uhs18_1247--udt17294": "circuit_56",
    "uhs19_1247--udt15839": "circuit_57",
    "uhs19_1247--udt19872": "circuit_58",
    "uhs20_1247--udt5173": "circuit_59",
    "uhs20_1247--udt8894": "circuit_60",
    "uhs20_1247--udt9897": "circuit_61",
}

# ---------------------------------------------------------------------
# 2) Load the three mapping CSVs
# ---------------------------------------------------------------------

df_NC = pd.read_csv("../NC_parquet_and_bldgs_dm.csv")
df_NC["STATE"] = "NC"

df_mapping = pd.concat([df_NC], ignore_index=True)

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

    circuit_dashed = CIRCUIT_NAME_MAP.get(circuit_underscore, circuit_underscore)
    circuit_id = REVERSE_CIRCUIT_MAP.get(circuit_dashed, "unknown_circuit")

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
