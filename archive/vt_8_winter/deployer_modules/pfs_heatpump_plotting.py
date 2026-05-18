# -*- coding: utf-8 -*-
"""
Module Name: pfs_heatpump_plotting.py
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


def plot_combined_heatpump_sessions(array_heatpump_profiles, time_labels):
    """
    Generates and saves a plot of the average heat pump profile combined with individual heat pump sessions.
    Also, highlights the 4 kW cutoff with a horizontal line.

    Parameters:
    - array_heatpump_profiles (ndarray): Array containing heat pump profiles for multiple sessions.
    - time_labels (list): Labels for the x-axis representing time intervals.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    time_intervals = np.arange(array_heatpump_profiles.shape[1])  # Assuming time intervals match the second dimension of the array
    average_heatpump_profile = np.mean(array_heatpump_profiles, axis=0)

    plt.figure(figsize=(18, 18))  # Adjusting the size for a vertical poster
    plt.plot(time_intervals, average_heatpump_profile, label='Average Heat Pump Profile', color='red', linewidth=4)

    # Overlay the heat pump sessions with larger, more visible dots
    for hp in range(array_heatpump_profiles.shape[0]):
        plt.scatter(time_intervals, array_heatpump_profiles[hp, :], alpha=0.3, c='orange', s=100)

    # Add a horizontal line at 4 kW
    plt.axhline(y=4, color='black', linestyle='-', linewidth=2)

    # Add a label for the 4 kW line
    plt.text(x=time_intervals[-1], y=4, s=' 4 kW cutoff', verticalalignment='bottom', horizontalalignment='right', fontsize=24, color='black')

    plt.xlabel('Time (daily) [Hour: minute]', fontsize=28)
    plt.ylabel('Heat Pump / Heating Rod Power [kW]', fontsize=28)
    plt.xticks(range(0, len(time_labels), 4), time_labels[::4], rotation=90, ha='right', fontsize=24)  # Adjust the step as needed
    plt.yticks(fontsize=24)
    plt.legend(fontsize=28)
    plt.title('Heat Pump Profiles', fontsize=32)
    plt.tight_layout()
    plt.savefig('p5_combined_heatpump_profile_sessions_vertical.png', dpi=300)
    plt.show()
