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

# 1) Load the CSVs that indicate which Parquets we actually need
df_NC = pd.read_csv("../NC_parquet_and_bldgs.csv")
df_NC["STATE"] = "NC"

df_all = pd.concat([df_NC], ignore_index=True)

# Suppose the column "Parquet_Name" has something like "com_12774.parquet"
# or "res_500.parquet"
parquet_list = df_all["Parquet_Name"].unique().tolist()

# 2) Store them in a pickle for easy reference
needed_parquets_path = "needed_parquets.pkl"
with open(needed_parquets_path, "wb") as f:
    pickle.dump(parquet_list, f)

print(f"✅ Stored {len(parquet_list)} needed Parquet files in {needed_parquets_path}")
