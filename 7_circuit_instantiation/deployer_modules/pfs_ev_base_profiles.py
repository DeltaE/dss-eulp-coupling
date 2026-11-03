# -*- coding: utf-8 -*-
"""
Module Name: pfs_ev_base_profiles.py
Description:
    EV base charging profile for the Phase 7 deploy script.

    Returns the 96 fifteen-minute means of one EV charging profile in
    <circuit>/data_ev/:
        with_daily_plug_in_factor_70/
            Weekday - Level 2 - Diversified (75th percentile) of 100 EVs.csv
    Each profile file has 1,440 one-minute values (an unnamed index column and
    one value column). The 12 files in with_daily_plug_in_factor_70/ hold 0.70
    times the values of the files with the same names in
    without_daily_plug_in_factor/. The origin of the data_ev files is not
    recorded in the repository.

Functions:
    - process_vehicle_data: returns the base curve and writes data_ev/df_enatd.csv.

Usage:
    This module is intended to be imported and used by
    `power_flow_sim_daily_EV_STO_DG_deploy.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/21
Version: 0.1
"""

import os
import pandas as pd

EV_PROFILE_FOLDER = 'data_ev/with_daily_plug_in_factor_70'
EV_PROFILE_FILE = 'Weekday - Level 2 - Diversified (75th percentile) of 100 EVs.csv'


def process_vehicle_data(CURRENT_DIR, write_comparison_csv=True):
    """
    Return the EV base curve: the 96 fifteen-minute means of EV_PROFILE_FILE in
    EV_PROFILE_FOLDER under CURRENT_DIR. Each mean is sum(values[i:i+15]) / 15
    for i = 0, 15, ..., 1425, over the file's value column.

    Parameters:
    - CURRENT_DIR (str): the folder that holds data_ev/ (the circuit folder).
    - write_comparison_csv (bool, optional): if True, also read every file of
      data_ev/with_daily_plug_in_factor_70/ and the file of the same name in
      data_ev/without_daily_plug_in_factor/, rename the value column to
      'Values', add a 'Differentiator' column (<file>_pif or <file>_wopif), and
      write all 24 frames stacked to CURRENT_DIR/data_ev/df_enatd.csv
      (columns 'Unnamed: 0', 'Values', 'Differentiator'), replacing any
      existing file. The returned values are the same either way.

    Returns:
    - list_vals_use_ev_15 (list): the 96 means.

    Stops:
    - FileNotFoundError if data_ev/ or EV_PROFILE_FILE is missing, or, with
      write_comparison_csv, if a file has no counterpart in the second folder.
    """
    list_vals_use_ev_15 = []

    # The base curve is the 70 % plug-in factor file
    l_ev_use = pd.read_csv(os.path.join(CURRENT_DIR, EV_PROFILE_FOLDER, EV_PROFILE_FILE))
    l_ev_use.columns.values[1] = 'Values'
    list_vals_use = l_ev_use['Values'].tolist()
    # Calculate the 15-minute averages
    for i in range(0, len(list_vals_use), 15):
        avg_chunk = sum(list_vals_use[i:i+15]) / 15
        list_vals_use_ev_15.append(avg_chunk)

    li_append = []

    if write_comparison_csv:
        dir_ev_pif = os.path.join(CURRENT_DIR, 'data_ev/with_daily_plug_in_factor_70')
        list_file_path_ev_pif = os.listdir(dir_ev_pif)
        dir_ev_wopif = os.path.join(CURRENT_DIR, 'data_ev/without_daily_plug_in_factor')

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

        # Concatenate all processed DataFrames
        df_enatd = pd.concat(li_append, axis=0, ignore_index=True)
        # Save the concatenated DataFrame to a CSV file
        df_enatd.to_csv(os.path.join(CURRENT_DIR, 'data_ev/df_enatd.csv'), index=False)

    # Return the list of 15-minute averages
    return list_vals_use_ev_15
