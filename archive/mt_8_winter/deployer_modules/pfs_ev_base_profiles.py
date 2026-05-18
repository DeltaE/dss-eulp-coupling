# -*- coding: utf-8 -*-
"""
Module Name: pfs_ev_base_profiles.py
Description:
    

Functions:
    - 
    

Usage:
    This module is intended to be imported and used by 
    `power_flow_sim.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/21
Version: 0.1
"""

import os
import pandas as pd

def process_vehicle_data(CURRENT_DIR, ev_profile_version='without_pif', test_compare_ev_input_profiles=True):
    """
    Processes electric vehicle (EV) data by reading data files based on the EV profile version,
    optionally comparing EV input profiles, and saving the processed data to a CSV file. For files
    that match specific criteria related to 'Level 2', '75th percentile of 100 EVs', and 'Weekday',
    the function calculates and returns 15-minute averages of the 'Values' column.

    Parameters:
    - CURRENT_DIR (str): The directory where the data files are located.
    - ev_profile_version (str, optional): The EV profile version to be used for processing the data.
    - test_compare_ev_input_profiles (bool, optional): Flag to indicate comparison of EV input profiles.

    Returns:
    - list_vals_use_ev_15 (list): 15-minute averages of the 'Values' for specific files, empty if no files match.

    Outputs:
    - A CSV file named 'df_enatd.csv' within the 'data_ev' directory in CURRENT_DIR with the processed data.
    """
    list_file_path_ev = []
    list_vals_use_ev_15 = []

    # Check for profile version and list files accordingly
    if ev_profile_version == 'with_pif_70':
        print('happens 1')
        list_file_path_ev = os.listdir(os.path.join(CURRENT_DIR, 'data_ev/with_daily_plug_in_factor_70'))
    elif ev_profile_version == 'without_pif':
        print('happens 2')
        list_file_path_ev = os.listdir(os.path.join(CURRENT_DIR, 'data_ev/without_daily_plug_in_factor'))

    li_append = []

    if test_compare_ev_input_profiles and list_file_path_ev:
        dir_ev_pif = os.path.join(CURRENT_DIR, 'data_ev/with_daily_plug_in_factor_70')
        list_file_path_ev_pif = os.listdir(dir_ev_pif)
        dir_ev_wopif = os.path.join(CURRENT_DIR, 'data_ev/without_daily_plug_in_factor')
        list_file_path_ev_wopif = os.listdir(dir_ev_wopif)

        # Iterate across names to compare files
        for l in list_file_path_ev_pif:
            l_ev_pif = pd.read_csv(os.path.join(dir_ev_pif, l))
            l_ev_wopif = pd.read_csv(os.path.join(dir_ev_wopif, l))

            # Standardize column names and add differentiators
            l_ev_pif.columns.values[1] = 'Values'
            l_ev_wopif.columns.values[1] = 'Values'
            l_ev_pif['Differentiator'] = l + '_pif'
            l_ev_wopif['Differentiator'] = l + '_wopif'

            li_append.extend([l_ev_pif, l_ev_wopif])

            # Additional processing for specific files
            if 'Level 2' in l and '(75th percentile) of 100 EVs' in l and 'Weekday' in l:
                list_vals_use = l_ev_pif['Values'].tolist()
                # Calculate the 15-minute averages
                for i in range(0, len(list_vals_use), 15):
                    avg_chunk = sum(list_vals_use[i:i+15]) / 15
                    list_vals_use_ev_15.append(avg_chunk)

        # Concatenate all processed DataFrames
        df_enatd = pd.concat(li_append, axis=0, ignore_index=True)
        # Save the concatenated DataFrame to a CSV file
        df_enatd.to_csv(os.path.join(CURRENT_DIR, 'data_ev/df_enatd.csv'), index=False)

    # Return the list of 15-minute averages for the specific files
    return list_vals_use_ev_15
