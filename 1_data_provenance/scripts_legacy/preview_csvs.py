# -*- coding: utf-8 -*-
"""
Created on Fri Dec  5 13:49:07 2025

@author: luisfernando
"""

#%% IMPORTS

import pandas as pd

#%% CONFIG - EDIT FILENAMES HERE

RESIDENTIAL_INPUT = "residential_data.csv"
COMMERCIAL_INPUT = "commercial_data.csv"

N_ROWS = 5  # Number of rows to preview

#%% PREVIEW RESIDENTIAL

print("\n=== RESIDENTIAL DATA ===\n")

df_res = pd.read_csv(RESIDENTIAL_INPUT, nrows=N_ROWS)

print("Columns:")
print(df_res.columns.tolist())

print("\nFirst " + str(N_ROWS) + " rows:")
print(df_res)

#%% PREVIEW COMMERCIAL

print("\n=== COMMERCIAL DATA ===\n")

df_com = pd.read_csv(COMMERCIAL_INPUT, nrows=N_ROWS)

print("Columns:")
print(df_com.columns.tolist())

print("\nFirst " + str(N_ROWS) + " rows:")
print(df_com)

#%% CHECK STATE COLUMNS

print("\n=== STATE COLUMNS ===\n")

res_state_cols = [c for c in df_res.columns ] #if 'state' in c.lower()]
com_state_cols = [c for c in df_com.columns ] #if 'state' in c.lower()]

print("Residential state columns: ", res_state_cols)
print("Commercial state columns: ", com_state_cols)

#%% DONE

print("\n=== DONE ===")
