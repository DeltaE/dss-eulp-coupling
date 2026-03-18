# -*- coding: utf-8 -*-
"""
Created on Sun Mar  9 20:27:09 2025

@author: luisfernando
"""

import os
import pandas as pd
import sys
from copy import deepcopy
import time

START_TIME = time.time()

STATE_STR = 'NC'

'''
GOAL: to find a suitable match, per state, to each row in review_parquet_matches.csv
'''

# 1. READ THE CSV FILES
df_matches = pd.read_csv("review_parquet_matches.csv")
df_com_ALL = pd.read_csv("commercial_data_SELECT_STATES.csv")
df_res_ALL = pd.read_csv("residential_data_SELECT_STATES.csv")

df_com = df_com_ALL.loc[df_com_ALL['State'] == STATE_STR]
df_res = df_res_ALL.loc[df_res_ALL['State'] == STATE_STR]

df_com_states = list(set(df_com['State'].tolist()))
df_com_states.sort()
df_res_states = list(set(df_res['State'].tolist()))
df_res_states.sort()

# Define variables holding the column names
cols_review = df_matches.columns.tolist()
cols_commercial = df_com.columns.tolist()
cols_residential = df_res.columns.tolist()

# 2. PREPARE A PIVOT OF THE REVIEW_PARQUET_MATCHES FOR COMMERCIAL
#    We want a row per Source_File with columns for each month’s peak.
df_matches_com = df_matches[df_matches["Type"] == "com"].copy()

# Pivot so that each Source_File has up to 12 columns: Peak_1, Peak_2, ...
df_matches_com_pivot = df_matches_com.pivot(
    index="Source_File", 
    columns="Month", 
    values="Monthly_Peak"
).reset_index()

# The pivot columns will be months 1..12, named as integers. Let’s rename them for clarity.
# e.g. 1 -> Peak_1, 2 -> Peak_2, etc.
df_matches_com_pivot.columns = [
    "Source_File" if col == "Source_File" else f"Peak_{col}"
    for col in df_matches_com_pivot.columns
]

# print('Stop here')
# sys.exit()

df_matches_com_pivot_states = []
for st in df_com_states:
    # Create a copy for each state and add a "State" column
    df_temp = df_matches_com_pivot.copy()
    df_temp["State"] = st  # Assign the state
    df_matches_com_pivot_states.append(df_temp)

# Combine all the state-based instances into one DataFrame
df_matches_com_pivot_expanded = pd.concat(df_matches_com_pivot_states, ignore_index=True)

# 3. CREATE A MAP FROM MONTH INTEGER TO COMMERCIAL COLUMN NAME
#    so we know which column to compare to for each month
month_to_peak_col_com = {
    1: "out.qoi.maximum_daily_peak_jan..kw",
    2: "out.qoi.maximum_daily_peak_feb..kw",
    3: "out.qoi.maximum_daily_peak_mar..kw",
    4: "out.qoi.maximum_daily_peak_apr..kw",
    5: "out.qoi.maximum_daily_peak_may..kw",
    6: "out.qoi.maximum_daily_peak_jun..kw",
    7: "out.qoi.maximum_daily_peak_jul..kw",
    8: "out.qoi.maximum_daily_peak_aug..kw",
    9: "out.qoi.maximum_daily_peak_sep..kw",
    10: "out.qoi.maximum_daily_peak_oct..kw",
    11: "out.qoi.maximum_daily_peak_nov..kw",
    12: "out.qoi.maximum_daily_peak_dec..kw",
}

# print('get until here')
# sys.exit()

SORT_COM_BOOL = True
# SORT_COM_BOOL = False
if SORT_COM_BOOL:
    # 4. MATCH COMMERCIAL ROWS
    commercial_matches_list = []

    # Iterate each unique Source_File row from the pivot
    for _, row in df_matches_com_pivot_expanded.iterrows():
        source_file = row["Source_File"]
        this_state = row["State"]
        print('Finding matches for: ', source_file, this_state)

        # We’ll collect all building_ids that match
        matched_bldgs = []
        best_tolerance = None  # Store the first tolerance that worked

        # We will store matched buildings once we find them at a given tolerance
        final_matched_bldgs = []

        # Filter df_com to only buildings in that state
        df_com_filtered = df_com[df_com["State"] == this_state]

        # Try different tolerance levels (5%, 10%, 15%, ..., 50%)
        for tolerance in range(5, 55, 5):
            matched_bldgs = []  # Reset matches for each tolerance level

            for _, bldg_row in df_com_filtered.iterrows():
                all_months_match = True

                for m in range(1, 13):
                    col_name = f"Peak_{m}"
                    if pd.isna(row[col_name]):
                        continue  # Skip missing months

                    ref_peak = row[col_name]
                    building_peak = bldg_row[month_to_peak_col_com[m]]

                    # Check if the building peak is within the tolerance range
                    if not (abs(building_peak - ref_peak) <= (tolerance / 100) * ref_peak):
                        all_months_match = False
                        break  # Stop checking this building if any month fails

                if all_months_match:
                    matched_bldgs.append(bldg_row["bldg_id"])

            if matched_bldgs:
                final_matched_bldgs = matched_bldgs
                best_tolerance = tolerance
                break

        # After trying all tolerances, store the final result for this row
        commercial_matches_list.append({
            "Source_File": source_file,
            "State": this_state,
            "Matched_Buildings": final_matched_bldgs,
            "Tolerance": best_tolerance
        })

    df_com_matches_out = pd.DataFrame(commercial_matches_list)
    df_com_matches_out.to_csv("df_com_matches_out_" + STATE_STR + ".csv", index=False)

    # 1) Get all unique building IDs from df_com
    all_com_bldg_ids = set(df_com["bldg_id"].unique())
    total_com_buildings = len(all_com_bldg_ids)

    # 2) Flatten the "Matched_Buildings" lists from df_com_matches_out
    #    Each row has a list of building IDs, so we union them all into one set:
    matched_bldg_ids = set().union(*df_com_matches_out["Matched_Buildings"])
    total_matched = len(matched_bldg_ids)

    '''
    Below we just double "check total_matched" and "total_matched_set" are the same.
    '''
    matched_bldg_ids_retest = []
    for alists in df_com_matches_out["Matched_Buildings"].tolist():
        matched_bldg_ids_retest += alists
        # print('check what is going on')
        # sys.exit()
    matched_bldg_ids_set = list(set(matched_bldg_ids_retest))
    total_matched_set = len(matched_bldg_ids_set)

    # 3) Print a summary
    print(f"Number of unique building IDs in df_com: {total_com_buildings}")
    print(f"Number of unique matched building IDs: {total_matched}")
    print(f"That's {100.0 * total_matched / total_com_buildings:.2f}% of the commercial dataset.")

# 5. PREPARE THE REVIEW_PARQUET_MATCHES FOR RESIDENTIAL
df_matches_res = df_matches[df_matches["Type"] == "res"].copy()

# Pivot so each Source_File has up to 12 columns: Peak_1..Peak_12
df_matches_res_pivot = df_matches_res.pivot(
    index="Source_File",
    columns="Month",
    values="Monthly_Peak"
).reset_index()

df_matches_res_pivot.columns = [
    "Source_File" if col == "Source_File" else f"Peak_{col}"
    for col in df_matches_res_pivot.columns
]

# Expand by state (similar to commercial)
df_matches_res_pivot_states = []
for st in df_res_states:
    df_temp = df_matches_res_pivot.copy()
    df_temp["State"] = st
    df_matches_res_pivot_states.append(df_temp)

df_matches_res_pivot_expanded = pd.concat(df_matches_res_pivot_states, ignore_index=True)

# ---- RESIDENTIAL MATCHING ----
SORT_RES_BOOL = True
# SORT_RES_BOOL = False
if SORT_RES_BOOL:
    residential_matches_list = []

    for _, row in df_matches_res_pivot_expanded.iterrows():
        source_file = row["Source_File"]
        this_state = row["State"]
        print("Finding residential matches for:", source_file, this_state)

        df_res_filtered = df_res[df_res["State"] == this_state]

        best_tolerance = None
        final_matched_bldgs = []

        # Tolerances from 5% to 50%
        for tolerance in range(5, 100, 5):
            matched_bldgs = []

            for _, bldg_row in df_res_filtered.iterrows():
                # 1) Check winter (12,1,2)
                match_winter = True
                for m in [12, 1, 2]:
                    col_name = f"Peak_{m}"
                    if pd.isna(row[col_name]):
                        continue

                    ref_peak = row[col_name]
                    building_winter_peak = bldg_row["out.electricity.winter.peak.kw"]

                    if not (abs(building_winter_peak - ref_peak) <= (tolerance/100)*ref_peak):
                        match_winter = False
                        break

                # 2) Check summer (6,7,8)
                match_summer = True
                for m in [6, 7, 8]:
                    col_name = f"Peak_{m}"
                    if pd.isna(row[col_name]):
                        continue

                    ref_peak = row[col_name]
                    building_summer_peak = bldg_row["out.electricity.summer.peak.kw"]

                    if not (abs(building_summer_peak - ref_peak) <= (tolerance/100)*ref_peak):
                        match_summer = False
                        break

                # Only match if both winter & summer pass
                if match_winter and match_summer:
                    matched_bldgs.append(bldg_row["bldg_id"])

            if matched_bldgs:
                final_matched_bldgs = matched_bldgs
                best_tolerance = tolerance
                break

        residential_matches_list.append({
            "Source_File": source_file,
            "State": this_state,
            "Matched_Buildings": final_matched_bldgs,
            "Tolerance": best_tolerance
        })

    df_res_matches_out = pd.DataFrame(residential_matches_list)
    df_res_matches_out.to_csv("df_res_matches_out_" + STATE_STR + ".csv", index=False)

    # Summaries
    all_res_bldg_ids = set(df_res["bldg_id"].unique())
    total_res_buildings = len(all_res_bldg_ids)

    matched_bldg_ids_res = set().union(*df_res_matches_out["Matched_Buildings"])
    total_matched_res = len(matched_bldg_ids_res)

    matched_bldg_ids_res_retest = []
    for alists in df_res_matches_out["Matched_Buildings"].tolist():
        matched_bldg_ids_res_retest += alists
    matched_bldg_ids_res_set = list(set(matched_bldg_ids_res_retest))
    total_matched_res_set = len(matched_bldg_ids_res_set)

    print("=== Residential Matching Summary ===")
    print(f"Number of unique building IDs in df_res: {total_res_buildings}")
    print(f"Number of unique matched building IDs: {total_matched_res}")
    print(f"That's {100.0 * total_matched_res / total_res_buildings:.2f}% of the residential dataset.")
    print("====================================")

END_TIME = time.time()

# Calculate and print elapsed time
ELAPSED_TIME = END_TIME - START_TIME
print(f"Time taken: {ELAPSED_TIME} seconds")

