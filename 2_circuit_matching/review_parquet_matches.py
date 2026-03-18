# -*- coding: utf-8 -*-
"""
Created on Sun Mar  9 18:37:46 2025

@author: luisfernando
"""

import os
import pandas as pd
import sys
import pickle
from copy import deepcopy
import time

START_TIME = time.time()

# Define the folder path
folder_path = './parquet_data'
all_monthly_stats = []

# List all parquet files in the folder
all_files = [f for f in os.listdir(folder_path) if f.endswith('.parquet')]

# User-defined list to filter the parquet files
# filter_list = ["com_12774.parquet"]  # Modify this list as needed
filter_list_long = []

flex_path = \
    './circuits_plain_format'
go_back_checker = [i for i in os.listdir(flex_path) if '.' not in i]
#print(go_back_checker)
#print('Check now')
#sys.exit()
test_folders = [i for i in go_back_checker]
for tf in test_folders:
    tf_path = flex_path + '/' + tf
    pkl_files = [i for i in os.listdir(tf_path) if '.pkl' in i]
    pkl_path = tf_path + '/' + pkl_files[0]
    with open(pkl_path, "rb") as f:
        daily_list_set_list = pickle.load(f)
    filter_list_long += deepcopy(daily_list_set_list)
    # print('Check TF')
    # sys.exit()

# filter_list_raw = list(set(daily_list_set_list))
filter_list_raw = list(set(filter_list_long))
filter_list_raw.sort()
filter_list = list(dict.fromkeys(s.replace('_kw', '').replace('_pu', '') + ".parquet" for s in filter_list_raw))

# Filter the list based on user-defined criteria
filtered_files = [f for f in all_files if f in filter_list]

if len(filtered_files) == len(filter_list):
    print('Sanity checked has passed')

# print('check if filtered data worked')
# sys.exit()

# Open the first filtered parquet file and check column names if any files match
for n in range(len(filtered_files)):
    print(filtered_files[n])
    file_path = os.path.join(folder_path, filtered_files[n])
    df_orig = pd.read_parquet(file_path)
    #print("Column names:", df.columns.tolist())

    # Keep only necessary columns and clean memory
    df = df_orig[['Time', 'total_site_electricity_kw']]
    df = df.astype({'total_site_electricity_kw': 'float32'})

    # Convert Time to datetime with error handling
    # df['Time'] = pd.to_datetime(df['Time'], errors='coerce', format='%Y-%m-%d %H:%M:%S')

    # Convert Time to datetime and extract month
    # df['Time'] = pd.to_datetime(df['Time'])

    if 'com' in filtered_files[n]:
        str_type = 'com'
        # Clean up Time column format before conversion
        df['Time'] = df['Time'].astype(str).str.replace(r':\d{2}$', '', regex=True)
        df['Time'] = pd.to_datetime(df['Time'], errors='coerce', format='%Y-%m-%d %H:%M:%S')
    elif 'res' in filtered_files[n]:
        str_type = 'res'
        # print('what happened')
        # sys.exit()
    else:
        print('Not found')

    df['Month'] = df['Time'].dt.month
    
    # Calculate monthly average, peak, and valley
    monthly_stats = df.groupby('Month')['total_site_electricity_kw'].agg(
        Monthly_Average='mean',
        Monthly_Peak='max',
        Monthly_Valley='min',
        Monthly_75th_Percentile=lambda x: x.quantile(0.75),
        Monthly_25th_Percentile=lambda x: x.quantile(0.25)
    ).reset_index()

    # print('stop here')
    # sys.exit()

    # Add a column for the source file
    monthly_stats['Source_File'] = filtered_files[n]
    monthly_stats['Type'] = str_type

    # Append to the list
    all_monthly_stats.append(monthly_stats)

# Consolidate all monthly stats into a single DataFrame
consolidated_df = pd.concat(all_monthly_stats, ignore_index=True)

# Save the consolidated DataFrame to CSV
consolidated_df.to_csv('review_parquet_matches.csv', index=False)

print("Saved consolidated monthly statistics to review_parquet_matches.csv")

END_TIME = time.time()

# Calculate and print elapsed time
ELAPSED_TIME = END_TIME - START_TIME
print(f"Time taken: {ELAPSED_TIME} seconds")

