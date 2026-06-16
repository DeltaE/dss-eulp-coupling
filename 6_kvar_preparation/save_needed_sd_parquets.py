# -*- coding: utf-8 -*-
"""
Created on Sat Apr  5 16:47:43 2025

@author: luisfernando
"""

# -*- coding: utf-8 -*-
"""
Script 2a: Identify needed original Parquet files (with KW+KVAR).
Store them in a 'needed_parquets.pkl' for next steps.
"""

import os
import pickle
import pandas as pd
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_work_path

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']

# 1) Load the CSVs that indicate which Parquets we actually need
script_dir = os.path.dirname(os.path.abspath(__file__))
mapping_path = resolve_work_path("5b_profile_generation", f"{STATE}_parquet_and_bldgs.csv")
if not os.path.exists(mapping_path):
    mapping_path = resolve_work_path(f"{STATE}_parquet_and_bldgs.csv")
df_state = pd.read_csv(mapping_path)
df_state["STATE"] = STATE

df_all = pd.concat([df_state], ignore_index=True)

# Suppose the column "Parquet_Name" has something like "com_12774.parquet"
# or "res_500.parquet"
parquet_list = df_all["Parquet_Name"].unique().tolist()

# 2) Store them in a pickle for easy reference
needed_parquets_path = resolve_work_path("6_kvar_preparation", "needed_parquets.pkl")
with open(needed_parquets_path, "wb") as f:
    pickle.dump(parquet_list, f)

print(f"✅ Stored {len(parquet_list)} needed Parquet files in {needed_parquets_path}")
