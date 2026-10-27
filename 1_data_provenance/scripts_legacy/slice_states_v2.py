# -*- coding: utf-8 -*-
"""
Created on Dec 2024

@author: luisfernando

Slice residential/commercial CSVs for Canadian province proxy states.

Province → State mapping:
  Ontario      → MI (Michigan)
  Quebec       → VT (Vermont)
  BC           → WA (Washington)
  Alberta      → MT (Montana)
  Manitoba     → MN (Minnesota)
"""

#%% IMPORTS AND CONFIG

import pandas as pd
import time

START_TIME = time.time()

# Target states (cold-climate proxies for Canadian provinces)
TARGET_STATES = ['MI', 'VT', 'WA', 'MT', 'MN']

# Input files
RESIDENTIAL_INPUT = "residential_data.csv"
COMMERCIAL_INPUT = "commercial_data.csv"

# Output files
states_suffix = "_".join(TARGET_STATES)
RESIDENTIAL_OUTPUT = "residential_data_SELECT_STATES_" + states_suffix + ".csv"
COMMERCIAL_OUTPUT = "commercial_data_SELECT_STATES_" + states_suffix + ".csv"

print("Target states: ", TARGET_STATES)

#%% LOAD AND FILTER COMMERCIAL DATA

print("\n=== COMMERCIAL ===\n")

df_com = pd.read_csv(COMMERCIAL_INPUT)
print("Loaded " + str(len(df_com)) + " rows")

# Commercial uses 'in.state' column directly
df_com_filtered = df_com[df_com['in.state'].isin(TARGET_STATES)].copy()
print("Filtered to " + str(len(df_com_filtered)) + " rows")

# Breakdown
print("\nBreakdown by state:")
for st in TARGET_STATES:
    count = len(df_com_filtered[df_com_filtered['in.state'] == st])
    print("  " + st + ": " + str(count) + " buildings")

#%% SAVE COMMERCIAL

df_com_filtered.to_csv(COMMERCIAL_OUTPUT, index=False)
print("\nSaved: " + COMMERCIAL_OUTPUT)

#%% LOAD RESIDENTIAL DATA

print("\n=== RESIDENTIAL ===\n")

df_res = pd.read_csv(RESIDENTIAL_INPUT)
print("Loaded " + str(len(df_res)) + " rows")

#%% EXTRACT STATE FROM FOLDER_FILE

# Folder_File format: "Metadata_AL_Residential_baseline.csv"
# Extract state code (2nd element after split by '_')

df_res['State'] = df_res['Folder_File'].apply(lambda x: x.split('_')[1])

# Check unique states
unique_states = df_res['State'].unique().tolist()
unique_states.sort()
print("Unique states found: ", unique_states)

#%% FILTER RESIDENTIAL DATA

df_res_filtered = df_res[df_res['State'].isin(TARGET_STATES)].copy()
print("Filtered to " + str(len(df_res_filtered)) + " rows")

# Breakdown
print("\nBreakdown by state:")
for st in TARGET_STATES:
    count = len(df_res_filtered[df_res_filtered['State'] == st])
    print("  " + st + ": " + str(count) + " buildings")

#%% SAVE RESIDENTIAL

df_res_filtered.to_csv(RESIDENTIAL_OUTPUT, index=False)
print("\nSaved: " + RESIDENTIAL_OUTPUT)

#%% DONE

END_TIME = time.time()
ELAPSED_TIME = END_TIME - START_TIME

print("\n=== COMPLETE ===")
print("Time taken: " + str(round(ELAPSED_TIME, 2)) + " seconds")
print("\nOutput files:")
print("  " + COMMERCIAL_OUTPUT)
print("  " + RESIDENTIAL_OUTPUT)
