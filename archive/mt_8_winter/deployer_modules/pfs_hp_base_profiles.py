# -*- coding: utf-8 -*-
"""
Module Name: pfs_hp_base_profiles.py
Description:
    

Functions:
    - 
    

Usage:
    This module is intended to be imported and used by 
    `power_flow_sim.py`. It is not designed to be executed directly.

Author: Luis F. Victor Gallardo
Date: 2024/03/23
Version: 0.1
"""

# Import general packages
import os
import sys
import pandas as pd
import numpy as np


def linear_interpolate(start_val, end_val, num_intervals=4):
    """
    Linearly interpolate between two values.

    Parameters:
    - start_val: The starting value.
    - end_val: The ending value.
    - num_intervals: The number of intervals to interpolate over, default is 4 for 15-minute intervals over an hour.

    Returns:
    - A list of interpolated values.
    """
    return [start_val + (end_val - start_val) * (i / num_intervals) for i in range(1, num_intervals)]


def generate_heatpump_profiles(LOAD_NUMBER, HP_PERC, MONTH, DAY, TEMP_RANGE_MIN, TEMP_RANGE_MAX, DF_HP_CSV_PATH):
    """
    Generates heat pump profiles based on the specified parameters.

    Parameters:
    - LOAD_NUMBER: The load number to calculate the number of heat pumps.
    - HP_PERC: The percentage of heat pumps.
    - MONTH: The month for filtering the data.
    - DAY: The day for filtering the data.
    - TEMP_RANGE_MIN: The minimum temperature range for filtering.
    - TEMP_RANGE_MAX: The maximum temperature range for filtering.

    Returns:
    - A tuple containing the profiles matrix and the list of selected heat pumps.
    """
    # Assuming 'linear_interpolate' is defined or imported elsewhere
    # from yourmodule import linear_interpolate

    # Path to the CSV file
    heatpump_data = pd.read_csv(DF_HP_CSV_PATH)

    # Calculate the number of Heatpumps
    HP_NUM = int(LOAD_NUMBER * HP_PERC)

    # Filter the DataFrame for the specific MONTH and DAY
    df_filtered = heatpump_data[(heatpump_data['Month of Timestamp'] == MONTH) &
                                (heatpump_data['Day of Timestamp'] == DAY) &
                                (heatpump_data['Avg. Temperature:Total'].between(TEMP_RANGE_MIN, TEMP_RANGE_MAX))]
    df_filtered_times = list(set(df_filtered['Hour of Timestamp'].tolist()))
    df_filtered_times.sort()
    if df_filtered_times != [i for i in range(0, 24)]:
        print('Error exists in selection of temperature ranges')
        sys.exit()

    # Group by 'Heat Pump' and filter
    filtered_groups = df_filtered.groupby('Heat Pump').filter(
        lambda x: set(df_filtered_times).issubset(set(x['Hour of Timestamp'].unique()))
    )

    # Check if the resulting DataFrame is empty
    if filtered_groups.empty:
        print('No rows found with all required hours for each Heat Pump value')
        sys.exit()

    # Set the random seed for reproducibility
    initial_seed = 42

    num_profiles = HP_NUM  # Number of profiles
    time_hours = 24
    profiles_matrix_hr = np.zeros((num_profiles, time_hours))

    time_intervals = 96  # Number of 15-minute intervals in a DAY
    profiles_matrix = np.zeros((num_profiles, time_intervals))

    list_selected_heat_pump = []

    # Fill each profile in the matrix
    for i in range(num_profiles):
        # Increment the seed for each profile to get different random samples
        random_seed = initial_seed + i

        # Randomly select one 'Heat Pump' value from filtered_groups
        selected_heat_pump = filtered_groups['Heat Pump'].sample(n=1, random_state=np.random.RandomState(random_seed)).values[0]
        list_selected_heat_pump.append(selected_heat_pump)
        filtered_groups_hp_chosen = filtered_groups[(filtered_groups['Heat Pump'] == selected_heat_pump)]

        # Sort the DataFrame by 'Hour of Timestamp'
        df_local_sorted = filtered_groups_hp_chosen.sort_values(by='Hour of Timestamp')

        # Extract the values from 'AVG((P Tot))/1000'
        avg_p_tot_values = df_local_sorted['AVG((P Tot))/1000'].values

        # Fill the profile row with these values
        profiles_matrix_hr[i, :] = avg_p_tot_values

        # Interpolation loop
        new_index = 0
        for j in range(time_hours):
            # Original value
            profiles_matrix[i, new_index] = profiles_matrix_hr[i, j]
            new_index += 1

            # Determine the next value for interpolation
            next_value = profiles_matrix_hr[i, (j + 1) % time_hours]

            # Interpolated values
            interpolated_values = linear_interpolate(profiles_matrix_hr[i, j], next_value)
            for val in interpolated_values:
                profiles_matrix[i, new_index] = val
                new_index += 1

    return profiles_matrix, list_selected_heat_pump

