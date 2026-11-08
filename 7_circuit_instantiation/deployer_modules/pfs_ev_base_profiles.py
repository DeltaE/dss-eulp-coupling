# -*- coding: utf-8 -*-
"""
Module Name: pfs_ev_base_profiles.py
Description:
    EV base charging profile for the Phase 7 deploy script.

    Returns the 96 fifteen-minute means of one EV charging profile in
    <circuit>/data_ev/without_daily_plug_in_factor/, the check curve named in
    data_ev_cars/ev_inputs.yaml. Each profile file has 1,440 one-minute values
    (an unnamed index column and one value column). The files are Team-Nando
    EV-Demand-Profiles; the source is in ev_inputs.yaml.

Functions:
    - process_vehicle_data: returns the curve.

Usage:
    This module is intended to be imported and used by
    `power_flow_sim_daily_EV_STO_DG_deploy.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/21
Version: 0.1
"""

import os
import pandas as pd

def process_vehicle_data(CURRENT_DIR, profile_folder, profile_file):
    """
    Return the EV curve: the 96 fifteen-minute means of profile_file in
    profile_folder under CURRENT_DIR. Each mean is sum(values[i:i+15]) / 15
    for i = 0, 15, ..., 1425, over the file's value column.

    Parameters:
    - CURRENT_DIR (str): the folder that holds data_ev/ (the circuit folder).
    - profile_folder, profile_file (str): the folder (relative to CURRENT_DIR)
      and file of the curve; ev_cars session_rows passes the check curve of
      ev_inputs.yaml.

    Returns:
    - list_vals_use_ev_15 (list): the 96 means.

    Stops:
    - FileNotFoundError if data_ev/ or the profile file is missing.
    """
    list_vals_use_ev_15 = []

    l_ev_use = pd.read_csv(os.path.join(CURRENT_DIR, profile_folder, profile_file))
    l_ev_use.columns.values[1] = 'Values'
    list_vals_use = l_ev_use['Values'].tolist()
    # Calculate the 15-minute averages
    for i in range(0, len(list_vals_use), 15):
        avg_chunk = sum(list_vals_use[i:i+15]) / 15
        list_vals_use_ev_15.append(avg_chunk)

    # Return the list of 15-minute averages
    return list_vals_use_ev_15
