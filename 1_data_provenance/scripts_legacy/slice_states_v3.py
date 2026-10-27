# -*- coding: utf-8 -*-
"""
Created on Fri Dec  5 14:08:53 2025

@author: luisfernando

Slice residential/commercial CSVs for Canadian province proxy states.
Adds 'State' column so downstream matching scripts work properly.

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

# Output file (single combined file for all target states)
RESIDENTIAL_OUTPUT = "residential_data_SELECT_STATES_MI_VT_WA_MT_MN.csv"
COMMERCIAL_OUTPUT = "commercial_data_SELECT_STATES_MI_VT_WA_MT_MN.csv"

print("Target states: ", TARGET_STATES)

#%% LOAD COMMERCIAL DATA

print("\n=== COMMERCIAL ===\n")

df_com = pd.read_csv(COMMERCIAL_INPUT)
print("Loaded " + str(len(df_com)) + " rows")

#%% ADD STATE COLUMN TO COMMERCIAL (copy from in.state)

df_com['State'] = df_com['in.state']

# Check unique states
unique_states_com = df_com['State'].unique().tolist()
unique_states_com.sort()
print("Unique states in commercial: ", unique_states_com)

#%% FILTER COMMERCIAL DATA

df_com_filtered = df_com[df_com['State'].isin(TARGET_STATES)].copy()
print("Filtered to " + str(len(df_com_filtered)) + " rows")

# Breakdown
print("\nBreakdown by state:")
for st in TARGET_STATES:
    count = len(df_com_filtered[df_com_filtered['State'] == st])
    print("  " + st + ": " + str(count) + " buildings")

#%% SAVE COMMERCIAL

# df_com_filtered.to_csv(COMMERCIAL_OUTPUT, index=False)
print("\nSaved: " + COMMERCIAL_OUTPUT)

#%% LOAD RESIDENTIAL DATA

print("\n=== RESIDENTIAL ===\n")

df_res = pd.read_csv(RESIDENTIAL_INPUT)
print("Loaded " + str(len(df_res)) + " rows")

#%% ADD STATE COLUMN TO RESIDENTIAL (extract from Folder_File)

# Folder_File format: "Metadata_AL_Residential_baseline.csv"
df_res['State'] = df_res['Folder_File'].apply(lambda x: x.split('_')[1])

# Check unique states
unique_states_res = df_res['State'].unique().tolist()
unique_states_res.sort()
print("Unique states in residential: ", unique_states_res)

#%% FILTER RESIDENTIAL DATA

df_res_filtered = df_res[df_res['State'].isin(TARGET_STATES)].copy()
print("Filtered to " + str(len(df_res_filtered)) + " rows")

# Breakdown
print("\nBreakdown by state:")
for st in TARGET_STATES:
    count = len(df_res_filtered[df_res_filtered['State'] == st])
    print("  " + st + ": " + str(count) + " buildings")

#%% SAVE RESIDENTIAL

# df_res_filtered.to_csv(RESIDENTIAL_OUTPUT, index=False)
print("\nSaved: " + RESIDENTIAL_OUTPUT)

#%% DONE

END_TIME = time.time()
ELAPSED_TIME = END_TIME - START_TIME

print("\n=== COMPLETE ===")
print("Time taken: " + str(round(ELAPSED_TIME, 2)) + " seconds")
print("\nOutput files (ready for matching scripts):")
print("  " + COMMERCIAL_OUTPUT)
print("  " + RESIDENTIAL_OUTPUT)
print("\nNext steps:")
print("  1. Run match_smartds_parquets_{STATE}.py for each state")
print("  2. Run clean_up_bldgs_{STATE}.py for each state")
