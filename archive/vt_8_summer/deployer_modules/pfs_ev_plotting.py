# -*- coding: utf-8 -*-
"""
Module Name: pfs_ev_plotting.py
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


def plot_calibration(total_intervals, average_demand, sessions, time_labels):
    """
    Generates and saves the calibration plot comparing target average demand
    with the generated average profile from sessions.

    Parameters:
    - total_intervals (int): Total number of intervals for the x-axis.
    - average_demand (list or ndarray): The target average demand over time.
    - sessions (ndarray): Session data used to compute the generated average profile.
    - time_labels (list): Labels for the x-axis representing time intervals.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    plt.figure(figsize=(12, 18))  # Adjusting the size for a vertical poster
    plt.plot(range(total_intervals), average_demand, label='Target Average Demand', color='red', linewidth=4)
    plt.plot(range(total_intervals), np.mean(sessions, axis=0), label='Generated Average Profile', color='blue', linestyle='--', linewidth=4)
    plt.title('EV Charging Profiles vs Target Average Demand', fontsize=32)
    plt.xlabel('Time (daily) [Hour: minute]', fontsize=28)
    plt.ylabel('Power [kW]', fontsize=28)
    plt.xticks(range(0, len(time_labels), 4), time_labels[::4], rotation=90, ha='right', fontsize=24)
    plt.yticks(fontsize=24)
    plt.legend(fontsize=28)
    plt.tight_layout()
    plt.savefig('p1_calibration_plot_vertical.png', dpi=300)
    plt.show()


def plot_sessions_heatmap(sessions, time_labels):
    """
    Generates and saves a heatmap of charging sessions.

    Parameters:
    - sessions (ndarray): Session data used for the heatmap.
    - time_labels (list): Labels for the x-axis representing time intervals.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    plt.figure(figsize=(18, 18))  # Adjusting the size for a vertical poster
    cax = plt.imshow(sessions, aspect='auto', interpolation='none', cmap='viridis_r')
    colorbar = plt.colorbar(cax, pad=0.01, fraction=0.02)
    colorbar.set_label('Power [kW]', fontsize=28)
    plt.xlabel('Time (daily) [Hour: minute]', fontsize=28)
    plt.ylabel('EV Index', fontsize=28)
    plt.xticks(range(0, len(time_labels), 4), time_labels[::4], rotation=90, ha='right', fontsize=24)
    plt.yticks(fontsize=24)
    plt.title('EV Charging Sessions', fontsize=32)
    plt.tight_layout()
    plt.savefig('p2_sessions_heatmap_vertical.png', dpi=300)
    plt.show()


def plot_combined_profile_sessions(time_intervals, average_demand, sessions, time_labels):
    """
    Generates and saves a plot of the combined target average demand and 
    generated average profile, with overlays of individual sessions.

    Parameters:
    - time_intervals (ndarray): Array of time intervals for the x-axis.
    - average_demand (list or ndarray): The target average demand over time.
    - sessions (ndarray): Session data used to compute the generated average profile and for overlay.
    - time_labels (list): Labels for the x-axis representing time intervals.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    plt.figure(figsize=(18, 18))  # Adjusting the size for a vertical poster
    plt.plot(time_intervals, average_demand, label='Target Average Demand', color='red', linewidth=4)
    plt.plot(time_intervals, np.mean(sessions, axis=0), label='Generated Average Profile', color='blue', linestyle='--', linewidth=4)
    for ev in range(sessions.shape[0]):
        plt.scatter(time_intervals, sessions[ev, :], alpha=0.3, c='orange', s=100)  # Increased visibility
    plt.xlabel('Time (daily) [Hour: minute]', fontsize=28)
    plt.ylabel('Power [kW]', fontsize=28)
    plt.xticks(range(0, len(time_labels), 4), time_labels[::4], rotation=90, ha='right', fontsize=24)
    plt.yticks(fontsize=24)
    plt.legend(fontsize=28)
    plt.title('EV Charging Profiles with Session Overlay', fontsize=32)
    plt.tight_layout()
    plt.savefig('p3_combined_profile_sessions_vertical.png', dpi=300)
    plt.show()


