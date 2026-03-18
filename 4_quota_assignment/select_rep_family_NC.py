# -*- coding: utf-8 -*-
"""
Created on Sun Mar 23 12:31:55 2025

@author: luisfernando
"""

import os
import ast
import pandas as pd
import os
import sys
import random
import numpy as np
import time
import ast
import os
import shutil

START_PROCESS = time.time()

FAMILY_STR = 'NC'
STATE_STR = 'NC'

# Set seed for reproducibility
random.seed(42)
np.random.seed(42)  # If you also use NumPy's random functions

# ------------------------------------------------------------
# 0) SETUP: Adjust scenario, data paths, etc.
# ------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))

# Example scenario for residential:
residential_scenario = "mid"  # or "mid" or "low"

# Priority lists of descriptor CSVs for residential, depending on scenario
if residential_scenario == "high":
    residential_priority = [
        "residential_data_SELECT_STATES_FILTERED_high_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_mid_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_low_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_not_available_" + FAMILY_STR + ".csv",
    ]
elif residential_scenario == "mid":
    residential_priority = [
        "residential_data_SELECT_STATES_FILTERED_mid_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_high_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_low_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_not_available_" + FAMILY_STR + ".csv",
    ]
else:  # "low" or any fallback
    residential_priority = [
        "residential_data_SELECT_STATES_FILTERED_low_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_mid_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_high_" + FAMILY_STR + ".csv",
        "residential_data_SELECT_STATES_FILTERED_not_available_" + FAMILY_STR + ".csv",
    ]

# Single commercial descriptor file:
commercial_descriptor_file = "commercial_data_SELECT_STATES_FILTERED_" + FAMILY_STR + ".csv"

# ------------------------------------------------------------
# 1) LOAD SOURCE MAPS & PARSE 'Unique_Source_Files'
# ------------------------------------------------------------
residential_map_path = os.path.join(current_dir, "residential_building_source_map_" + FAMILY_STR + ".csv")
commercial_map_path = os.path.join(current_dir, "commercial_building_source_map_" + FAMILY_STR + ".csv")

res_source_map = pd.read_csv(residential_map_path)
com_source_map = pd.read_csv(commercial_map_path)

# print('check the effectiveness up until here 0, finding unique parquets.')
# sys.exit()

# Convert string representations of lists into actual Python lists
res_source_map["Unique_Source_Files"] = res_source_map["Unique_Source_Files"].apply(ast.literal_eval)
com_source_map["Unique_Source_Files"] = com_source_map["Unique_Source_Files"].apply(ast.literal_eval)

# print('check the effectiveness up until here 1, finding unique parquets.')
# sys.exit()

# For a quick check, let's explode them to see how many unique parquets exist
res_exploded = res_source_map.explode("Unique_Source_Files").reset_index(drop=True)
com_exploded = com_source_map.explode("Unique_Source_Files").reset_index(drop=True)

# print('check the effectiveness up until here 2, finding unique parquets.')
# sys.exit()

unique_res_parquets = sorted(res_exploded["Unique_Source_Files"].unique())
unique_com_parquets = sorted(com_exploded["Unique_Source_Files"].unique())

print("Residential Source Map: # Parquet files =", len(unique_res_parquets))
# print(unique_res_parquets)
print()
print("Commercial Source Map: # Parquet files =", len(unique_com_parquets))
# print(unique_com_parquets)
print()

# We'll keep track of the bldg_ids that exist in the source maps
res_bldg_ids_set = set(res_source_map["bldg_id"].unique())
com_bldg_ids_set = set(com_source_map["bldg_id"].unique())

# print('check the effectiveness up until here 3, finding unique parquets.')
# sys.exit()
# ------------------------------------------------------------
# 2) READ COMMERCIAL DESCRIPTOR & FILTER
# ------------------------------------------------------------
com_descriptor_path = os.path.join(current_dir, commercial_descriptor_file)
commercial_df_raw = pd.read_csv(com_descriptor_path)

# No "vacancy" filter for commercial. We just keep everything that matches the map:
commercial_df = commercial_df_raw[commercial_df_raw["bldg_id"].isin(com_bldg_ids_set)]
commercial_df = commercial_df[commercial_df["State"] == STATE_STR]

# Group by building type
grouped_com = commercial_df.groupby("in.comstock_building_type")

# Define sampling fraction per building type
desired_buildings_per_type = {
   "Hospital": 3, #round(0.01*len(unique_com_parquets)),
   "LargeHotel": 14, # round(0.02*len(unique_com_parquets)),
   "SecondarySchool": 5, #round(0.03*len(unique_com_parquets)),
   "LargeOffice": 27, #round(0.04*len(unique_com_parquets)),
   "MediumOffice": 43, #round(0.05*len(unique_com_parquets)),
   "SmallHotel": 49, # round(0.05*len(unique_com_parquets)),
   "PrimarySchool": 5, #round(0.05*len(unique_com_parquets)),
   "QuickServiceRestaurant": 80, #round(0.10*len(unique_com_parquets)),
   "Outpatient": 50, #round(0.05*len(unique_com_parquets)),
   "FullServiceRestaurant": 50, #round(0.05*len(unique_com_parquets)),
   "RetailStandalone": 120, # round(0.15*len(unique_com_parquets)),
   "RetailStripmall": 81, #round(0.10*len(unique_com_parquets)),
   "SmallOffice": 165, #round(0.15*len(unique_com_parquets)),
   "Warehouse": 148 #round(0.15*len(unique_com_parquets)) + 2 # makes dictionary equal to the total
}

'''
NOTE:
There are limits to the number of building types that exist in the universe that can be sampled.
In that case we need to overwrite the desired building types so increase the number of assingations. I.e., a tweaking.
There are some building types that are likely more abundant than others, and thus should have a higher share of the total.

For example, disregarding the commented elements, we would get:

Buildings chosen per type (unique bldg_id) vs Required:
   in.comstock_building_type  Chosen  Required
0                   Hospital       3         9
1            SecondarySchool       5        26
2                 LargeHotel      14        18
3              PrimarySchool       5        44
4                LargeOffice      27        35
5                 SmallHotel      44        44
6               MediumOffice      44        44
7                 Outpatient      44        44
8           RetailStandalone     132       132
9      FullServiceRestaurant      44        44
10    QuickServiceRestaurant      88        88
11           RetailStripmall      82        88
12                 Warehouse     134       134
13               SmallOffice     132       132
14                     Total     798       882
used_parquets 798
missing_parquets 84

So we need to adjust the limits accordingly.
'''

total_buildings = sum(desired_buildings_per_type.values())
overall_target  =  len(unique_com_parquets) # 378  # must be the same as len(unique_com_parquets)

# print('stop here 1')
# sys.exit()

# We'll keep track of how many we actually pick
current_total = 0

# Track how many buildings we've used for each building type
assigned_count_per_type = {bt: 0 for bt in desired_buildings_per_type.keys()}

# Track which Parquets are already assigned
assigned_parquets = set()

# Store final selected rows here
selected_rows = []

# We'll make a dictionary mapping bldg_id -> set of parquets.
# This helps quickly see how many *new* parquets a building can cover.
bldg_to_parquets = (
    com_exploded.groupby("bldg_id")["Unique_Source_Files"]
    .apply(set)
    .to_dict()
)

# For convenience, create a dictionary mapping building type -> list of (bldg_id, row_of_commercial_df, set_of_parquets)
# This allows us to quickly find all possible building IDs in each type + their parquets.
building_type_dict = {}

for bldg_type, group in grouped_com:
    records_for_type = []
    for idx, row in group.iterrows():
        b_id = row["bldg_id"]
        parquet_set = bldg_to_parquets.get(b_id, set())
        records_for_type.append((b_id, row, parquet_set))
    building_type_dict[bldg_type] = records_for_type

print("\n1) How many buildings are available per building type:")
available_data = []  # will hold tuples of (bldg_type, num_available)
count_blg_id = 0
for bldg_type, records in building_type_dict.items():
    unique_bldg_ids = set(r[0] for r in records)  # r[0] is the bldg_id
    num_available = len(unique_bldg_ids)
    available_data.append((bldg_type, num_available))
    count_blg_id += 1
    print(f"   {count_blg_id} - {bldg_type}: {num_available} buildings total in this type")  # <- ADDED PRINT

# Sort by num_available in ascending order
available_data.sort(key=lambda x: x[1])

num_available_total = 0
print("\nSorted from lowest to highest number of available buildings:\n")
for idx, (bldg_type, num_available) in enumerate(available_data, start=1):
    print(f"{idx}. {bldg_type}: {num_available} buildings")
    num_available_total += num_available
print(f"Total buildings: {num_available_total} buildings")

print("\n2) The order of `for bldg_type, records in building_type_dict.items():` is now (lowest to highest):")
ordered_types = [b[0] for b in available_data]
for idx, bldg_type in enumerate(ordered_types, start=1):
    print(f"   {idx}. {bldg_type}")

print("\n")

# Define this to help ensure we have ONE BUILDING = ONE PARQUET FILE
used_parquets_globally = set()

# -------------------------------------------------------------------
# FOR EACH BUILDING TYPE, PICK BUILDINGS "PARQUET-FIRST"
# -------------------------------------------------------------------
custom_order = [
   "Hospital",
   "SecondarySchool",
   "LargeHotel",
   "PrimarySchool",
   "LargeOffice",
   "SmallHotel",
   "MediumOffice",
   "Outpatient",
   "RetailStandalone",
   "FullServiceRestaurant",
   "QuickServiceRestaurant",
   "RetailStripmall",
   "Warehouse",
   "SmallOffice"
]

for bldg_type in custom_order :
    records = building_type_dict[bldg_type]
    desired_count = desired_buildings_per_type.get(bldg_type, 0)
    if desired_count <= 0 or len(records) == 0:
        continue

    # If we've already hit the overall target, we can break if needed
    if current_total >= overall_target:
        break

    # 1) Identify all parquets covered by this building type
    parquets_for_this_type = set()
    for (b_id, row_data, p_set) in records:
        parquets_for_this_type |= p_set

    # Iterate over those parquets
    for parquet_file in parquets_for_this_type:  

        if bldg_type == 'Hospital':
            print('ENTERS 2?')
            # sys.exit()

        if parquet_file in assigned_parquets:
            continue  # Skip if this parquet was already assigned

        # Find all building candidates for this parquet
        candidates = [
            (b_id, row_data)
            for (b_id, row_data, p_set) in records
            if parquet_file in p_set
        ]

        if not candidates:
            # No candidates for this Parquet in this building type
            continue

        # Randomly choose one building for this parquet
        chosen_b_id, chosen_row_data = random.choice(candidates)

        # Check building type capacity before adding
        if assigned_count_per_type[bldg_type] < desired_count:

            if bldg_type == 'Hospital':
                print('ENTERS 3?')
                # if 'com_15017.parquet' == parquet_file:
                #    sys.exit()

            # Mark the Parquet as assigned
            assigned_parquets.add(parquet_file)

            # Add selected building to final output
            row_copy = chosen_row_data.copy()
            row_copy["Chosen_Parquet"] = parquet_file
            selected_rows.append(row_copy)

            # Track assigned counts
            assigned_count_per_type[bldg_type] += 1
            current_total += 1

            # Stop if we've hit the desired capacity for this type
            if assigned_count_per_type[bldg_type] >= desired_count:
                break  # Move to next building type

    print(f"Type={bldg_type} | Desired={desired_count} | Assigned={assigned_count_per_type[bldg_type]} "
          f"| Remaining overall capacity={overall_target - current_total}")

    if current_total >= overall_target:
        break

# -------------------------------------------------------------------
# BUILD FINAL DF & SUMMARIZE
# -------------------------------------------------------------------
# Note: If you want to avoid picking the same building multiple times
# across *all building types*, you could maintain a global "used_bldg_ids"
# set outside this loop. But for now, we only avoid duplicates *within the same* building type.

final_commercial = pd.DataFrame(selected_rows)  # IMPORTANT OUTPUT
final_count = len(final_commercial["bldg_id"].unique())

print("\nDone picking!")
print("Final building count (unique bldg_id):", final_count)
if final_count <= overall_target:
    print(f"Note: We asked for {overall_target} overall, but only got {final_count}.")

counts_per_type = final_commercial.groupby("in.comstock_building_type")["Chosen_Parquet"].nunique()
counts_per_type = counts_per_type.reindex(custom_order)
print("\nBuildings chosen per type (unique bldg_id):")
print(counts_per_type)

# Create a DataFrame counting how many unique bldg_ids we actually chose per type
counts_df = (
    final_commercial
    .groupby("in.comstock_building_type")["Chosen_Parquet"]
    .nunique()  # number of unique building IDs
    .reset_index(name="Chosen")
)

# Add a "Required" column by mapping from desired_buildings_per_type
# If a building type isn't in your dictionary, default to 0 or None
counts_df["Required"] = counts_df["in.comstock_building_type"].map(lambda x: desired_buildings_per_type.get(x, 0))
counts_df["in.comstock_building_type"] = pd.Categorical(
    counts_df["in.comstock_building_type"], categories=custom_order, ordered=True
)
# Ensure all building types from custom_order exist in counts_df
counts_df = counts_df.set_index("in.comstock_building_type").reindex(custom_order).reset_index()
# Add a Total Row
total_row = pd.DataFrame({
    "in.comstock_building_type": ["Total"],  # Label the total row
    "Chosen": [counts_df["Chosen"].sum()],
    "Required": [counts_df["Required"].sum()]
})

# Append the total row at the bottom
counts_df = pd.concat([counts_df, total_row], ignore_index=True)
#
print("\nBuildings chosen per type (unique bldg_id) vs Required:")
print(counts_df)

# print('check the effectiveness up until here 1, getting the final commercial dataframe.')
# sys.exit()

# -------------------------------------------------------------------
# ENSURE ALL PARQUETS IN unique_com_parquets ARE PRESENT
# -------------------------------------------------------------------
used_parquets_com = set(final_commercial["Chosen_Parquet"].unique())
missing_parquets_com = set(unique_com_parquets) - used_parquets_com

print('used_parquets', len(used_parquets_com))
print('missing_parquets', len(missing_parquets_com))

print('\n====================================================================')
print('ALL COMMERCIAL-RELATED WORK STOPS HERE')
print('====================================================================\n')

# print('check the effectiveness up until here 2, getting the final commercial dataframe.')
# sys.exit()

'''
----------------------------------------------------------------------------
'''
# ------------------------------------------------------------
# 3) READ RESIDENTIAL DESCRIPTOR(S) IN PRIORITY ORDER & FILTER
# ------------------------------------------------------------
residential_selected = []
residential_selected_vacant = []  # some buildings are vacant.

# Start with all Parquets as "unassigned"
unassigned_parquets_res = set(unique_res_parquets)
assigned_parquets_res = set()

for csv_name in residential_priority:
    path = os.path.join(current_dir, csv_name)
    if os.path.exists(path):
        temp_df = pd.read_csv(path)

        # Filter by Occupied
        temp_df_vac = temp_df[temp_df["in.vacancy_status"] != "Occupied"]
        temp_df = temp_df[temp_df["in.vacancy_status"] == "Occupied"]

        # Keep only building IDs in the source map
        temp_df = temp_df[temp_df["bldg_id"].isin(res_bldg_ids_set)]
        temp_df_vac = temp_df_vac[temp_df_vac["bldg_id"].isin(res_bldg_ids_set)]

        residential_selected.append(temp_df)
        residential_selected_vacant.append(temp_df_vac)
    else:
        print(f"Warning: {csv_name} not found. Skipping.")

# Combine all priority CSVs
if residential_selected:
    final_residential_raw = pd.concat(residential_selected, ignore_index=True)
    final_residential_raw_vacant = pd.concat(residential_selected_vacant, ignore_index=True)
else:
    final_residential_raw = pd.DataFrame()

print("Residential descriptor after initial filtering:")
print(final_residential_raw.head(), "\nTotal:", len(final_residential_raw), "\n")

# If there's nothing, no need to proceed
if final_residential_raw.empty:
    print("No residential buildings found after filtering. Stopping.")
    # Possibly sys.exit() here
    # or handle gracefully
    pass

# We want a dictionary: bldg_id -> set of Parquet files
bldg_to_parquets_res = (
    res_exploded.groupby("bldg_id")["Unique_Source_Files"]
    .apply(set)
    .to_dict()
)

# Now group final_residential_raw by 'in.geometry_building_type_acs'
grouped_residential = final_residential_raw.groupby("in.geometry_building_type_acs")

# Build a dictionary: building_type_dict_res[type] = list of (bldg_id, row, parquet_set)
building_type_dict_res = {}
for bldg_type, group in grouped_residential:
    print(bldg_type)
    records_for_type = []
    for idx, row_data in group.iterrows():
        b_id = row_data["bldg_id"]
        # find this building's parquets
        parquet_set = bldg_to_parquets_res.get(b_id, set())
        records_for_type.append((b_id, row_data, parquet_set))
    building_type_dict_res[bldg_type] = records_for_type

# ------------------------------------------
# SORT BUILDING TYPES BY AVAILABILITY OR USE A CUSTOM ORDER
# ------------------------------------------
availability_data = []
for bldg_type, records in building_type_dict_res.items():
    unique_bldg_ids = set(r[0] for r in records)
    availability_data.append((bldg_type, len(unique_bldg_ids)))

# Sort ascending by the # of buildings
availability_data.sort(key=lambda x: x[1])
ordered_types_res = [x[0] for x in availability_data]

print("\nResidential building types from fewest to most buildings:")
for i, (bt, count) in enumerate(availability_data, start=1):
    print(f" {i}. {bt} has {count} buildings.")

# ------------------------------------------
# DEFINE HOW MANY BUILDINGS PER TYPE (if desired)
# ------------------------------------------
'''
ordered_types_res_scenario = [
    "Single-Family Detached",
    "Single-Family Attached",
    "50 or more Unit",
    "20 to 49 Unit",
    "10 to 19 Unit",
    "5 to 9 Unit",
    "3 or 4 Unit",
    "2 Unit",
    "Mobile Home"
]
'''

'''
ordered_types_res_scenario = [
    "Mobile Home",
    "2 Unit",
    "3 or 4 Unit",
    "5 to 9 Unit",
    "10 to 19 Unit",
    "20 to 49 Unit",
    "50 or more Unit",
    "Single-Family Attached",
    "Single-Family Detached"
]
'''

ordered_types_res_scenario = [
    "Mobile Home",
    "2 Unit",
    "3 or 4 Unit",
    "Single-Family Attached",
    "Single-Family Detached",
    "5 to 9 Unit",
    "10 to 19 Unit",
    "20 to 49 Unit",
    "50 or more Unit",
]

res_desired_buildings_per_type = {
    "Single-Family Detached": 312, # round(0.55*len(unique_res_parquets)),
    "Single-Family Attached": round(0.25*len(unique_res_parquets)),
    "50 or more Unit": 8, #round(0.05*len(unique_res_parquets)),
    "20 to 49 Unit": 3, #round(0.03*len(unique_res_parquets)),
    "10 to 19 Unit": 10, # round(0.03*len(unique_res_parquets)),
    "5 to 9 Unit": 9, # round(0.03*len(unique_res_parquets)),
    "3 or 4 Unit": round(0.03*len(unique_res_parquets)),
    "2 Unit": round(0.05*len(unique_res_parquets)),
    "Mobile Home": round(0.01*len(unique_res_parquets)) # adjusted to match the overall_target_res
}

'''
NOTE:
There are limits to the number of building types that exist in the universe that can be sampled.
In that case we need to overwrite the desired building types so increase the number of assingations. I.e., a tweaking.
There are some building types that are likely more abundant than others, and thus should have a higher share of the total.

For example, disregarding the commented elements, we would get:
    
Residential building type assignment vs. required:
  in.geometry_building_type_acs  Chosen  Required
0                   Mobile Home       4         4
1                        2 Unit      26        26
2                   3 or 4 Unit      16        16
3        Single-Family Attached     114       114
4        Single-Family Detached     285       285
5                   5 to 9 Unit       9        16
6                 10 to 19 Unit      10        16
7                 20 to 49 Unit       3        16
8               50 or more Unit       8        26
9                         Total     475       519

So we need to adjust the limits accordingly.

'''

total_residential_sum = sum(res_desired_buildings_per_type.values())
overall_target_res = len(unique_res_parquets)  # e.g. want 1 building per parquet (?)

# print('stop here 2')
# sys.exit()


# Track how many we assigned so far, and which parquets
assigned_count_res = {bt: 0 for bt in res_desired_buildings_per_type}
assigned_parquets_res = set()

selected_rows_res = []

current_total_res = 0

parquet_file_dict = {}
parquet_file_dict_csv_level = {}

# ------------------------------------------
# LOOP OVER BUILDING TYPES (lowest->highest) AND ASSIGN PARQUETS
#    *Similar logic to your commercial code*
# ------------------------------------------
for csv_name in residential_priority:
    if not unassigned_parquets_res:
        print("\nAll Parquets are already assigned! Breaking early.")
        break

    path = os.path.join(current_dir, csv_name)
    if not os.path.exists(path):
        print(f"Warning: {csv_name} not found. Skipping.")
        continue

    print(f"\n>>> Processing scenario CSV: {csv_name}")
    temp_df = pd.read_csv(path)

    # 1) Filter by Occupied + bldg_id in res_bldg_ids_set
    # temp_df = temp_df[temp_df["in.vacancy_status"] == "Occupied"]
    temp_df = temp_df[temp_df["State"] == STATE_STR]
    # temp_df = temp_df[temp_df["bldg_id"].isin(res_bldg_ids_set)]

    BOOL_CHECK_BLDG_IDS = True
    if BOOL_CHECK_BLDG_IDS:
        # Iterate through each unique Parquet in `res_exploded`
        for parquet_file in res_exploded["Unique_Source_Files"].unique():

            # Get all bldg_id associated with this Parquet
            bldgs_for_parquet = res_exploded[res_exploded["Unique_Source_Files"] == parquet_file]["bldg_id"].unique()

            # Find which of these bldg_ids exist in `temp_df`
            existing_bldgs = set(bldgs_for_parquet).intersection(set(temp_df["bldg_id"].unique()))

            # Find missing bldg_id(s) (that are in res_exploded but NOT in temp_df)
            missing_bldgs = set(bldgs_for_parquet) - existing_bldgs

            if parquet_file not in parquet_file_dict or not parquet_file_dict[parquet_file]:
                parquet_file_dict.update({parquet_file:existing_bldgs})
                parquet_file_dict_csv_level.update({parquet_file:csv_name})

            # if not parquet_file_dict[parquet_file] and parquet_file not in parquet_file_dict_csv_level:
            #    parquet_file_dict_csv_level.update({parquet_file:csv_name})

    # print('stop temp_df here')
    # sys.exit()

    # res_exploded

    if temp_df.empty:
        print(f"No buildings after filtering in {csv_name}. Skipping scenario.")
        continue

    print(f"  # of buildings in scenario after filtering: {len(temp_df)}")

    # 2) Create a scenario-based bldg_to_parquets & building_type_dict
    scenario_bldg_ids = set(temp_df["bldg_id"].unique())
    scenario_exploded = res_exploded[res_exploded["bldg_id"].isin(scenario_bldg_ids)]

    # Build dictionary: bldg_id -> building type
    # bldg_id_to_type = {row["bldg_id"]: row["in.geometry_building_type_acs"] for _, row in temp_df.iterrows()}

    bldg_to_parquets_scenario = (
        scenario_exploded.groupby("bldg_id")["Unique_Source_Files"]
        .apply(set)
        .to_dict()
    )

    # Group by building type in this scenario
    grouped_scenario = temp_df.groupby("in.geometry_building_type_acs")

    building_type_dict_scenario = {}
    for bldg_type, group in grouped_scenario:
        records_for_type = []
        for _, row_data in group.iterrows():
            b_id = row_data["bldg_id"]
            parquet_set = bldg_to_parquets_scenario.get(b_id, set())
            records_for_type.append((b_id, row_data, parquet_set))
        building_type_dict_scenario[bldg_type] = records_for_type

    # (Optional) Sort building types from fewest to most building availability
    availability_data = []
    for b_type, recs in building_type_dict_scenario.items():
        unique_bldg_ids = set(r[0] for r in recs)
        availability_data.append((b_type, len(unique_bldg_ids)))
    # ascending
    availability_data.sort(key=lambda x: x[1], reverse=True)
    # ordered_types_res_scenario = [x[0] for x in availability_data]

    # print('stop this please')
    # sys.exit()

    print("  Building types in scenario (fewest->most):")
    for bt, count_ in availability_data:
        print(f"    {bt}: {count_} buildings")

    # 3) Assign unassigned Parquets for each building type in scenario
    for bldg_type in ordered_types_res_scenario:
        recs = building_type_dict_scenario[bldg_type]
        if not recs:
            continue

        # How many we want for this building type
        desired_count = res_desired_buildings_per_type.get(bldg_type, 0)

        # gather all parquets for this type
        parquets_for_this_type = set()
        for (b_id, row_data, p_set) in recs:
            parquets_for_this_type |= p_set

        # only pick from unassigned
        # parquets_for_this_type = parquets_for_this_type.intersection(unassigned_parquets_res) ! ESTO NO AYUDA

        if 'res_140.parquet' in parquets_for_this_type:
            print('STOP THIS HERE AND SEE INICIO res_140')

        for parquet_file in parquets_for_this_type:
            # if type is already at capacity, break
            ### if assigned_count_res[bldg_type] >= desired_count:
            ###    print('happens? 1')
            ###    # sys.exit()
            ###    break
            if current_total_res >= overall_target_res:
                print('happens? 2')
                # sys.exit()
                break

            # gather candidates
            candidates = [(b_id, row_data)
                          for (b_id, row_data, p_set) in recs
                          if parquet_file in p_set]

            # print('break this')
            # sys.exit()

            if not candidates:
                print('happens? 3')
                sys.exit()
                continue

            # random pick
            chosen_b_id, chosen_row_data = random.choice(candidates)

            # final check
            if assigned_count_res[bldg_type] < desired_count and parquet_file in unassigned_parquets_res:
                # assign
                row_copy = chosen_row_data.copy()
                row_copy["Chosen_Parquet"] = parquet_file
                selected_rows_res.append(row_copy)

                assigned_count_res[bldg_type] += 1
                current_total_res += 1

                # remove from unassigned
                unassigned_parquets_res.remove(parquet_file)

        print(f"    Type={bldg_type}: Desired={desired_count}, "
              f"Assigned={assigned_count_res[bldg_type]}, Running total={current_total_res}")

        if 'res_140.parquet' in parquets_for_this_type:
            print('STOP THIS HERE AND SEE FIN res_140')

    print(f"  Remaining unassigned parquets after {csv_name}: {len(unassigned_parquets_res)}")
    if not unassigned_parquets_res:
        print("  All parquets assigned!")
        break  # no more to do

# End of scenario loop
print("\n=== Done with all scenario CSVs. ===")
final_residential = pd.DataFrame(selected_rows_res)
print(f"Final assigned buildings: {len(final_residential)} rows, covering "
      f"{final_residential['Chosen_Parquet'].nunique()} parquets.")

# ------------------------------------------
# DIAGNOSTICS: missing parquets, counts, etc.
# ------------------------------------------
counts_per_type_res = final_residential.groupby("in.geometry_building_type_acs")["Chosen_Parquet"].nunique()
counts_per_type_res = counts_per_type_res.reindex(ordered_types_res_scenario)
print("\nBuildings chosen per residential type (unique assigned parquets):")
print(counts_per_type_res)

# Optionally build a DataFrame, add total row, etc.
res_counts_df = counts_per_type_res.reset_index(name="Chosen")
res_counts_df["Required"] = res_counts_df["in.geometry_building_type_acs"].map(lambda x: res_desired_buildings_per_type.get(x, 0))
res_counts_df["in.geometry_building_type_acs"] = pd.Categorical(
    res_counts_df["in.geometry_building_type_acs"], categories=ordered_types_res_scenario, ordered=True
)
# Summation row
summary_row = {
    "in.geometry_building_type_acs": "Total",
    "Chosen": res_counts_df["Chosen"].sum(),
    "Required": res_counts_df["Required"].sum()
}
res_counts_df = pd.concat([res_counts_df, pd.DataFrame([summary_row])], ignore_index=True)

print("\nResidential building type assignment vs. required:")
print(res_counts_df)

# -------------------------------------------------------------------
# ENSURE ALL PARQUETS IN unique_res_parquets ARE PRESENT
# ----------------------------------------------------------------

used_parquets_res = set(final_residential["Chosen_Parquet"].unique())
missing_parquets_res = set(unique_res_parquets) - used_parquets_res

print('used_parquets', len(used_parquets_res))
print('missing_parquets', len(missing_parquets_res))

print('\n====================================================================')
print('ALL RESIDENTIAL-RELATED WORK STOPS HERE')
print('====================================================================\n')

# print('stop tests until here')
# sys.exit()

# ------------------------------------------------------------
# TROUBLESHOOT MISSING PARQUETS
# Try to assign a building ID from `temp_df` to any unassigned Parquets
# ------------------------------------------------------------
# BOOL_ALLOW_MISSING_PARQUETS = False
BOOL_ALLOW_MISSING_PARQUETS = True
if missing_parquets_res and BOOL_ALLOW_MISSING_PARQUETS:
    print("\n=== Final Attempt to Assign Missing Parquets ===")

    # Reverse lookup: Map Parquet -> Possible bldg_ids from `res_exploded`
    parquet_to_bldg_ids = (
        res_exploded[res_exploded["Unique_Source_Files"].isin(missing_parquets_res)]
        .groupby("Unique_Source_Files")["bldg_id"]
        .apply(set)
        .to_dict()
    )

    for parquet_file in missing_parquets_res:
        possible_bldg_ids = parquet_to_bldg_ids.get(parquet_file, set())

        # Find a matching building in `final_residential_raw` (our processed temp_df)
        match_candidates = final_residential_raw[final_residential_raw["bldg_id"].isin(possible_bldg_ids)]
        match_candidates_vacant = final_residential_raw_vacant[final_residential_raw_vacant["bldg_id"].isin(possible_bldg_ids)]

        if not match_candidates.empty:
            # Pick a random one
            chosen_row_data = match_candidates.sample(n=1, random_state=42).iloc[0].copy()
            chosen_row_data["Chosen_Parquet"] = parquet_file
            selected_rows_res.append(chosen_row_data)

            # Remove from missing list
            unassigned_parquets_res.discard(parquet_file)

            print(f"✅ Assigned {parquet_file} -> bldg_id {chosen_row_data['bldg_id']} ({chosen_row_data['in.geometry_building_type_acs']})")

        elif not match_candidates_vacant.empty:
            # Pick a random one
            chosen_row_data = match_candidates_vacant.sample(n=1, random_state=42).iloc[0].copy()
            chosen_row_data["Chosen_Parquet"] = parquet_file
            selected_rows_res.append(chosen_row_data)

            # Remove from missing list
            unassigned_parquets_res.discard(parquet_file)

            print(f"(FROM VACANT) ✅ Assigned {parquet_file} -> bldg_id {chosen_row_data['bldg_id']} ({chosen_row_data['in.geometry_building_type_acs']})")

        else:
            print('Mismatch persists for {parquet_file}!')
            sys.exit()

    print(f"\nAfter troubleshooting, remaining unassigned Parquets: {len(unassigned_parquets_res)}")


# print('stop tests until here x2')
# sys.exit()

'''
----------------------------------------------------------------------------
'''
# ------------------------------------------------------------
# 4) COPY THE FILES
# ------------------------------------------------------------
# Function to copy selected Parquet files
def copy_selected_parquets(source_folder, target_folder, selected_bldg_ids):
    for file in os.listdir(source_folder):
        if file.endswith("-0.parquet"):
            bldg_id = file.split("-")[0]  # Extract building ID
            if bldg_id in selected_bldg_ids:
                shutil.copy2(os.path.join(source_folder, file), os.path.join(target_folder, file))

# Define paths
COPY_FILE_BOOL = False
# COPY_FILE_BOOL = True
if COPY_FILE_BOOL:
    commercial_source_folder = "parquet_commercial_20250330_comm_" + STATE_STR
    residential_source_folder = "parquet_residential_short_20250330_" + STATE_STR

    commercial_target_folder = "NC_parquet_commercial_20250330_comm_" + STATE_STR
    residential_target_folder = "NC_parquet_residential_20250330_" + STATE_STR

    # Ensure target folders exist
    os.makedirs(commercial_target_folder, exist_ok=True)
    os.makedirs(residential_target_folder, exist_ok=True)

    # Extract unique bldg_ids as strings
    selected_commercial_bldg_ids = set(final_commercial["bldg_id"].astype(str).unique())
    selected_residential_bldg_ids = set(final_residential["bldg_id"].astype(str).unique())

    # Copy files
    copy_selected_parquets(residential_source_folder, residential_target_folder, selected_residential_bldg_ids)
    copy_selected_parquets(commercial_source_folder, commercial_target_folder, selected_commercial_bldg_ids)

    # List all available Parquet files in the residential source folder
    available_residential_files = os.listdir("parquet_residential_short_20250330_" + STATE_STR)

    # Extract the bldg_id part from filenames that follow the "-0.parquet" pattern
    available_residential_bldg_ids = set(
        file.split("-")[0] for file in available_residential_files if file.endswith("-0.parquet")
    )

    # Identify missing building IDs
    missing_residential_bldg_ids = selected_residential_bldg_ids - available_residential_bldg_ids
    print("Copying complete.")

# Define file paths
final_commercial_csv = FAMILY_STR + '_' + "final_commercial.csv"
final_residential_csv = FAMILY_STR + '_' + "final_residential.csv"

# Save DataFrames to CSV
final_commercial.to_csv(final_commercial_csv, index=False)
final_residential.to_csv(final_residential_csv, index=False)

print(f"Saved final_commercial to {final_commercial_csv}")
print(f"Saved final_residential to {final_residential_csv}")

END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')

