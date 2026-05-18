# -*- coding: utf-8 -*-
"""
Module Name: pfs_file_processing.py
Description:
    

Functions:
    - modify_master_file: Adjusts timeframes and comments out badly connected PV systems
    - modify_dss_files: Adjusts load data based on scenarios
    

Usage:
    This module is intended to be imported and used by 
    `power_flow_sim.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/21
Version: 0.1
"""

# Import general packages
import comtypes.client as cc
import os 
import datetime
import pandas as pd
import numpy as np
import matplotlib.dates as mdates 
from matplotlib import pyplot as plt
import shutil
import sys
import re
import time
from copy import deepcopy
import csv
from datetime import datetime, timedelta
import random
import math
import cmath


def modify_master_file(master_file_path, timestep, irradiance_zero):
    """
    Modifies the master DSS file to adjust the simulation's timeframe and potentially
    comment out PV systems based on irradiance.

    This function reads the original master file, adjusts references to include timestep
    information, and conditions PV system lines based on the irradiance being zero.
    
    Parameters:
    - master_file_path (str): The path to the master .dss file to be modified.
    - timestep (int): The current timestep for which the file is being adjusted.
    - irradiance_zero (bool): Flag indicating whether the irradiance is zero, 
                              used to decide if PVSystems should be commented out.

    Returns:
    - None
    """
    with open(master_file_path, 'r') as file:
        lines = file.readlines()

    new_lines = []
    for line in lines:
        if 'Redirect' in line and '.dss' in line:
            command, file_name = line.strip().split(maxsplit=1)
            
            # Remove previous timestep if it exists and the unnecessary repetition of extension
            file_name = re.sub(r'(_[0-9]+)?\.dss', '.dss', file_name)

            # Create the new file name with the current timestep
            new_file_name = file_name.replace('.dss', f'_{timestep}.dss')

            comment = '! ' if 'PVSystems.dss' in line and irradiance_zero else ''
            new_line = f"{comment}{command} {new_file_name}\n"
            new_lines.append(new_line)
        elif 'Buscoords' in line:
            command, file_name = line.strip().split()
            
            # Remove previous timestep if it exists
            file_name = re.sub(r'_[0-9]+\.dss', '.dss', file_name)

            # Create the new file name with the current timestep
            new_file_name = file_name.replace('.dss', f'_{timestep}.dss')

            new_line = f"{command} {new_file_name}\n"
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    # Write the new lines back to the master file
    with open(master_file_path, 'w') as file:
        file.writelines(new_lines)


def modify_dss_files(file_path, timestep, profiles, BASE_MULTIPLIER,
                     HP_RESI_LIMIT, dfs_hp_profile, df_hp_compare, CASE_SIMUL,
                     array_ev_profiles):
    """
    Modifies .dss files to update load and PV system parameters based on profile data
    and adds additional loads for heat pumps and EVs according to specified profiles.

    This function dynamically adjusts load parameters and PV system irradiance within
    DSS files based on pre-defined profiles for each timestep. It also handles the 
    inclusion of heat pump and EV profiles by modifying or adding new load definitions
    according to the simulation timestep.
    
    Parameters:
    - file_path (str): The path to the .dss file to be modified.
    - timestep (int): The current timestep used for fetching profile data.
    - profiles (dict): A dictionary of load profiles where keys are load names, and 
                       values are data frames containing profile data.
    - array_heatpump_profiles (numpy.ndarray): An array containing heat pump profiles.
    - array_ev_profiles (numpy.ndarray): An array containing electric vehicle profiles.

    Returns:
    - tuple: A tuple containing three elements:
        - irr_zero (bool): Indicates whether irradiance was set to zero (True) or not (False).
        - load_names (list): A list of load names processed.
        - load_names_all (list): A list of all load names, including those not directly processed.
    """
    with open(file_path, 'r') as file:
        lines = file.readlines()

    count_loads = 0
    load_names = []
    load_names_resi = []
    load_names_all = []
    load_names_all_full = []
    for line in lines:
        if len(line.split('.')) >= 2:
            substr1 = line.split('.')[1]
            substr2 = substr1.split('_')[1]
            if 'New Load.' in line and '=res_kw' in line and '0.12' in line:
                if '_2 conn' not in line:
                    load_names_resi.append(substr2)
            if 'New Load.' in line and '_2 conn' not in line and '0.12' in line:
                count_loads += 1
                load_names.append(substr2)
                load_names_all.append(substr2)
                load_names_all_full.append(line)
            elif '0.12' in line:
                load_names_all.append(substr2)
                load_names_all_full.append(line)
    print('In this circuit, the number of lines that exist are: ', count_loads)

    # print(load_names == load_names_all)
    # print(len(load_names), len(load_names_all))
    # print(load_names)
    # print(load_names_all)
    print('The number of residential loads are: ', len(load_names_resi))

    rand_counter = 0
    rand_count_clean = 0

    np.random.seed(555)

    new_lines = []
    irr_zero = False

    ev_lim = array_ev_profiles.shape[0]
    hp_lim = HP_RESI_LIMIT
    ev_forw_count = 0
    hp_forw_count = 0

    count_loads_resi = len(load_names_resi)

    ev_apply_list = np.random.choice(range(count_loads_resi-1), ev_lim, replace=False)
    ev_apply_list.sort()
    
    # print(count_loads_resi, range(count_loads_resi-1), hp_lim)
    
    hp_apply_list = np.random.choice(range(count_loads_resi-1), hp_lim, replace=False)
    hp_apply_list.sort()

    ''' Assignation of heat pump profiles '''
    # Generate unique profiles and shuffle them to ensure random assignment
    unique_profiles = df_hp_compare['Profile'].unique()
    np.random.shuffle(unique_profiles)

    # Repeat profiles to match the length of hp_apply_list
    assigned_profiles_hp = np.tile(unique_profiles, (len(hp_apply_list) // len(unique_profiles) + 1))[:len(hp_apply_list)]

    # Sort `hp_apply_list` to match with assigned profiles in the correct order
    hp_apply_list.sort()

    # Map each load in `hp_apply_list` to a unique profile from `assigned_profiles_hp`
    profile_assignment_hp = dict(zip(hp_apply_list, assigned_profiles_hp))

    '''
    print('\n')
    print(load_names_resi)

    print('\n')
    print(hp_apply_list)

    print('\n')
    print(profile_assignment_hp)

    print('check')
    sys.exit()
    '''

    # print('list 1', len(ev_apply_list))
    # print(ev_apply_list)
    
    # print('list 2', len(hp_apply_list))
    # print(hp_apply_list)

    for line in lines:
        if 'New Load.' in line:
         
            load_name = re.search(r'yearly=(.*?)$', line).group(1).strip()
            load_name = load_name.replace('.csv', '')  # Remove .csv if present
            kw = float(re.search(r'kW=(.*?) ', line).group(1))
            kvar = float(re.search(r'kvar=(.*?) ', line).group(1))

            substr1 = line.split('.')[1]
            substr2 = substr1.split('_')[1]
            
            # print(rand_counter, substr2)
            
            if '0.12' in line:
                load_name_idxable = substr2
                
                # print(load_name_idxable)
                
                load_name_idx = load_names.index(load_name_idxable)

            else:
                load_name_idxable = ''
                load_name_idx = 0
            
            # print(load_name_idxable, rand_counter, load_name_idx)
            # print('review load name')
            # sys.exit()

            print_load = False
            if print_load:
                print(f"Matching Load: {load_name}")  # Print the matched load name
                print(load_name in profiles)
                if load_name in profiles:
                    pass
                else:
                    print(list(profiles.keys()))
                sys.exit()

            # if rand_count_clean <= ev_lim:  # GRAB THE EV PROFILE
            if load_name_idx in ev_apply_list and '0.12' in line:
                # print(load_name_idx, ev_forw_count, '*')
                ev_ind_kw = array_ev_profiles[ev_forw_count, timestep-1]
                if '_2 ' in line:
                    ev_forw_count += 1
            else:
                ev_ind_kw = 0

            # if rand_count_clean <= hp_lim:  # GRAB THE Heat Pump PROFILE
            if load_name_idx in hp_apply_list and '0.12' in line:
                # print(load_name_idx, hp_forw_count, '**')
                profile_name = profile_assignment_hp[load_name_idx]  # Use the assigned random profile

                # This logic implements the addition of electric backup for the heat pumps:
                closest_row_index = (df_hp_compare['All_Elec_Base'] - kw).abs().idxmin()
                closest_profile_value = df_hp_compare.loc[closest_row_index, 'Profile']

                # print(kw, closest_profile_value, 'check this please')

                dfs_hp_profile_filtered_0 = dfs_hp_profile[
                    (dfs_hp_profile['Upgrade_ID'] == 0) & 
                    (dfs_hp_profile['filename'] == profile_name)
                ]

                dfs_hp_profile_filtered_1 = dfs_hp_profile[
                    (dfs_hp_profile['Upgrade_ID'] == 1) & 
                    (dfs_hp_profile['filename'] == profile_name)
                ]

                # print('LEN_0', len(dfs_hp_profile_filtered_0))
                # print('LEN_1', len(dfs_hp_profile_filtered_1))

                # Verification step: check if each filtered DataFrame has 96 rows
                assert len(dfs_hp_profile_filtered_0) == 96, "Upgrade 0 filtered data does not have 96 rows."
                assert len(dfs_hp_profile_filtered_1) == 96, "Upgrade 1 filtered data does not have 96 rows."

                # Extract columns into lists for Upgrade == 0
                heating_hp_bkup_energy_0 = dfs_hp_profile_filtered_0['out.electricity.heating_hp_bkup.energy_consumption'].tolist()
                heating_energy_0 = dfs_hp_profile_filtered_0['out.electricity.heating.energy_consumption'].tolist()

                # Extract columns into lists for Upgrade == 1
                heating_hp_bkup_energy_1 = dfs_hp_profile_filtered_1['out.electricity.heating_hp_bkup.energy_consumption'].tolist()
                heating_energy_1 = dfs_hp_profile_filtered_1['out.electricity.heating.energy_consumption'].tolist()

                # array_heatpump_profiles

                if CASE_SIMUL == 'NON_MOD':
                    hp_ind_kw_add_hp = 0
                    hp_ind_kw_add_backup = 0

                if CASE_SIMUL == 'BASELINE':
                    hp_ind_kw_add_hp = heating_energy_0[timestep-1]
                    hp_ind_kw_add_backup = heating_hp_bkup_energy_0[timestep-1]

                if CASE_SIMUL == 'HP_ELE_BACKUP':
                    hp_ind_kw_add_hp = heating_energy_1[timestep-1]
                    hp_ind_kw_add_backup = heating_hp_bkup_energy_1[timestep-1]

                if CASE_SIMUL == 'HP_GAS_BACKUP':
                    hp_ind_kw_add_hp = heating_energy_1[timestep-1]
                    hp_ind_kw_add_backup = 0

                hp_ind_kw_net = hp_ind_kw_add_hp + hp_ind_kw_add_backup

                if '_2 ' in line:
                    hp_forw_count += 1

            else:
                hp_ind_kw_net = 0

            if '0.12' in line:
                phase_mult = 0.5
            else:
                phase_mult = 1

            multiplier = profiles[load_name].iloc[timestep-1][0]
            new_kw = (kw * multiplier)*BASE_MULTIPLIER + (ev_ind_kw * phase_mult) + (hp_ind_kw_net * phase_mult)

            if new_kw < 0:
                print('A negative case occurred ', timestep)
                sys.exit()
                
                'with backup addition after subtraction, 20% become negative'
                'without backup, more than 50%'
                'hence, the load shaping is off and needs to be matched better'

                hp_ind_kw_net = hp_ind_kw_add_hp + hp_ind_kw_add_backup
                new_kw = (kw * multiplier)*BASE_MULTIPLIER + (ev_ind_kw * phase_mult) + (hp_ind_kw_net * phase_mult)

                if new_kw < 0:
                    print('A negative case occurred AFTER FIX', timestep)
                    # print(new_kw, kw, hp_ind_kw_subtract_base, hp_ind_kw_add_hp, hp_ind_kw_add_backup, 'check this please 2')
                    sys.exit()

            new_kvar = kvar * multiplier * BASE_MULTIPLIER

            #if rand_counter >= 1:
            #    if load_names_all[rand_counter] == load_names_all[rand_counter-1]:
            #        pass
            #    else:
            #        rand_count_clean += 1

            rand_counter += 1
            
            # print('/n')
            # print(load_name)
            # print[kW]
            # print(multiplier)
            # print(ev_ind_kw)
            # print(kvar)
            
            # print('review the load definition')
            # sys.exit()
            
            line = re.sub(r'kW=(.*?) ', f'kW={new_kw} ', line)
            line = re.sub(r'kvar=(.*?) ', f'kvar={new_kvar} ', line)
            line = line.replace('yearly', '!yearly')
        elif 'New PVSystem.' in line:
            pv_name = re.search(r'!yearly=(.*?)$', line).group(1).strip()
            pv_name = pv_name.replace('.csv', '')  # Remove .csv if present

            print_pv = False
            if print_pv:
                print(f"Matching PV: {pv_name}")  # Print the matched load name
                print(pv_name in profiles)
                if pv_name in profiles:
                    pass
                else:
                    print(list(profiles.keys()))

                irradiance = profiles[pv_name].iloc[timestep-1][0]
                print(irradiance)
                print(deepcopy(line))
            
                line = re.sub(r'irradiance=(.*?) ', f'irradiance={irradiance} ', line)
            
                print(deepcopy(line))

                sys.exit()

            irradiance = profiles[pv_name].iloc[timestep-1][0]   
            if float(irradiance) == 0.0:
                irr_zero = True
            line = re.sub(r'irradiance=(.*?) ', f'irradiance={irradiance} ', line)
        
        new_lines.append(line)
    
    with open(file_path, 'w') as file:
        file.writelines(new_lines)

    return irr_zero, load_names, load_names_all

