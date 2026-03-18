# -*- coding: utf-8 -*-
"""
Created on Mon Mar 17 09:42:15 2025

@author: luisfernando
"""

import pandas as pd
from ast import literal_eval
import time

START_TIME = time.time()

STATE_STR = 'NC'

# ===================================================
# =========== RESIDENTIAL FILTERING SECTION =========
# ===================================================
FILTER_RESIDENTIAL = True
if FILTER_RESIDENTIAL:
    print("\n=== RESIDENTIAL FILTERING ===\n")

    # 1) Read the matches file
    df_res_matches_out = pd.read_csv("df_res_matches_out_" + STATE_STR + ".csv")

    # 2) Ensure 'Matched_Buildings' is a list rather than a string
    #    (If your column is already a list, you can skip this step)
    df_res_matches_out["Matched_Buildings"] = df_res_matches_out["Matched_Buildings"].apply(
        lambda x: literal_eval(str(x)) if not isinstance(x, list) else x
    )

    # 3) Collect all unique bldg_ids, and track which Source_File(s) mention them
    bldg_source_map_res = {}
    for _, row in df_res_matches_out.iterrows():
        source_file = row["Source_File"]
        bldg_list = row["Matched_Buildings"]
        for bldg_id in bldg_list:
            if bldg_id not in bldg_source_map_res:
                bldg_source_map_res[bldg_id] = []
            bldg_source_map_res[bldg_id].append(source_file)

    unique_bldg_ids_res = set(bldg_source_map_res.keys())
    print(f"Found {len(unique_bldg_ids_res)} unique residential building IDs in df_res_matches_out_" + STATE_STR + ".csv")

    # 4) Filter the residential_data_SELECT_STATES_" + STATE_STR + ".csv by these bldg_ids
    df_res = pd.read_csv("residential_data_SELECT_STATES.csv")
    df_res_filtered = df_res[df_res["bldg_id"].isin(unique_bldg_ids_res)]
    df_res_filtered.to_csv("residential_data_SELECT_STATES_FILTERED_" + STATE_STR + ".csv", index=False)
    print("Wrote residential_data_SELECT_STATES_FILTERED_" + STATE_STR + ".csv")

    # 5) Output a summary CSV to show how many times each bldg_id occurs and in which Source_Files
    #    That way, you can see if a bldg_id was matched under multiple Source_File entries
    res_rows = []
    for bldg_id, sf_list in bldg_source_map_res.items():
        # Remove duplicates from sf_list if desired
        unique_source_files = list(set(sf_list))
        res_rows.append({
            "bldg_id": bldg_id,
            "Occurrence_Count": len(sf_list),
            "Unique_Source_Files": unique_source_files
        })
    df_res_summary = pd.DataFrame(res_rows)
    df_res_summary.to_csv("residential_building_source_map_" + STATE_STR + ".csv", index=False)
    print("Wrote residential_building_source_map_" + STATE_STR + ".csv")

    # ---------------------------------------------------------------------------
    # 6) SUB-SLICING BY INCOME GROUP (KEEPING 'Not Available' IF IT'S PART OF MATCHED ROWS)
    # ---------------------------------------------------------------------------
    print("\n=== SUB-SLICING BY INCOME GROUP ===")
    # We'll map specific income ranges to Low, Mid, High; anything else -> 'Not Available'
    income_mapping = {
        "0-30%":     "Low",
        "30-60%":    "Low",
        "60-80%":    "Low",
        "80-100%":   "Mid",
        "100-120%":  "Mid",
        "120-150%":  "High",
        "150%+":     "High",
    }

    # Create a new column "income_group"
    df_res_filtered["income_group"] = df_res_filtered["in.area_median_income"].apply(
        lambda x: income_mapping[x] if x in income_mapping else "Not Available"
    )

    # Separate data for Low, Mid, High, Not Available
    df_low = df_res_filtered[df_res_filtered["income_group"] == "Low"]
    df_mid = df_res_filtered[df_res_filtered["income_group"] == "Mid"]
    df_high = df_res_filtered[df_res_filtered["income_group"] == "High"]
    df_na = df_res_filtered[df_res_filtered["income_group"] == "Not Available"]

    # Write CSVs for Low, Mid, High
    df_low.to_csv("residential_data_SELECT_STATES_FILTERED_low_" + STATE_STR + ".csv", index=False)
    df_mid.to_csv("residential_data_SELECT_STATES_FILTERED_mid_" + STATE_STR + ".csv", index=False)
    df_high.to_csv("residential_data_SELECT_STATES_FILTERED_high_" + STATE_STR + ".csv", index=False)

    # Only write Not Available if it has any rows
    if not df_na.empty:
        df_na.to_csv("residential_data_SELECT_STATES_FILTERED_not_available_" + STATE_STR + ".csv", index=False)

    print("Wrote sub-slices by income group:")
    print("  - residential_data_SELECT_STATES_FILTERED_low_" + STATE_STR + ".csv")
    print("  - residential_data_SELECT_STATES_FILTERED_mid_" + STATE_STR + ".csv")
    print("  - residential_data_SELECT_STATES_FILTERED_high_" + STATE_STR + ".csv")
    if not df_na.empty:
        print("  - residential_data_SELECT_STATES_FILTERED_not_available.csv")

    print("=== DONE RESIDENTIAL FILTERING ===\n")


# ===================================================
# =========== COMMERCIAL FILTERING SECTION ==========
# ===================================================
FILTER_COMMERCIAL = True
if FILTER_COMMERCIAL:
    print("\n=== COMMERCIAL FILTERING ===\n")

    # 1) Read the commercial matches file
    df_com_matches_out = pd.read_csv("df_com_matches_out_" + STATE_STR + ".csv")

    # 2) Ensure 'Matched_Buildings' is a list
    df_com_matches_out["Matched_Buildings"] = df_com_matches_out["Matched_Buildings"].apply(
        lambda x: literal_eval(str(x)) if not isinstance(x, list) else x
    )

    # 3) Collect all unique bldg_ids, and track which Source_File(s) mention them
    bldg_source_map_com = {}
    for _, row in df_com_matches_out.iterrows():
        source_file = row["Source_File"]
        bldg_list = row["Matched_Buildings"]
        for bldg_id in bldg_list:
            if bldg_id not in bldg_source_map_com:
                bldg_source_map_com[bldg_id] = []
            bldg_source_map_com[bldg_id].append(source_file)

    unique_bldg_ids_com = set(bldg_source_map_com.keys())
    print(f"Found {len(unique_bldg_ids_com)} unique commercial building IDs in df_com_matches_out_" + STATE_STR + ".csv")

    # 4) Filter the commercial_data_SELECT_STATES_" + STATE_STR + ".csv by these bldg_ids
    df_com = pd.read_csv("commercial_data_SELECT_STATES.csv")
    df_com_filtered = df_com[df_com["bldg_id"].isin(unique_bldg_ids_com)]
    df_com_filtered.to_csv("commercial_data_SELECT_STATES_FILTERED_" + STATE_STR + ".csv", index=False)
    print("Wrote commercial_data_SELECT_STATES_FILTERED_" + STATE_STR + ".csv")

    # 5) Output a summary CSV to show bldg_id occurrences
    com_rows = []
    for bldg_id, sf_list in bldg_source_map_com.items():
        unique_source_files = list(set(sf_list))
        com_rows.append({
            "bldg_id": bldg_id,
            "Occurrence_Count": len(sf_list),
            "Unique_Source_Files": unique_source_files
        })
    df_com_summary = pd.DataFrame(com_rows)
    df_com_summary.to_csv("commercial_building_source_map_" + STATE_STR + ".csv", index=False)
    print("Wrote commercial_building_source_map_" + STATE_STR + ".csv")

    print("=== DONE COMMERCIAL FILTERING ===\n")

# Finish the time period below
END_TIME = time.time()

# Calculate and print elapsed time
ELAPSED_TIME = END_TIME - START_TIME
print(f"Time taken: {ELAPSED_TIME} seconds")
