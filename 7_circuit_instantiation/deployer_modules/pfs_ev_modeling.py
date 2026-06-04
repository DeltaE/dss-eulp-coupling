# -*- coding: utf-8 -*-
"""
Module Name: pfs_ev_modeling.py
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

# Function to generate initial random charging sessions
def generate_initial_charging_sessions(N, total_intervals, nominal_power, min_power, max_charging_events, average_demand):
    np.random.seed(555)
    sessions = np.zeros((N, total_intervals))
    demand_per_ev = average_demand / N  # Divide the average demand evenly across all EVs
    for i in range(N):
        # Ensure at least one charging event per EV
        start_interval = np.random.randint(0, total_intervals - 1)
        end_interval = np.random.randint(start_interval + 1, total_intervals)
        power_assigned = np.random.uniform(min_power, nominal_power)
        sessions[i, start_interval:end_interval] = power_assigned
        remaining_power = power_assigned - (end_interval - start_interval) * power_assigned

        # Additional charging events if needed
        for _ in range(1, max_charging_events):
            potential_starts = np.where(remaining_power > min_power)[0]
            if potential_starts.size > 0:
                start_interval = np.random.choice(potential_starts)
                end_interval = np.random.randint(start_interval + 1, min(start_interval + 4, total_intervals))
                power_assigned = np.random.uniform(min_power, min(nominal_power, remaining_power[start_interval]))
                sessions[i, start_interval:end_interval] = power_assigned
                remaining_power[start_interval:end_interval] -= power_assigned
                if end_interval < total_intervals:
                    sessions[i, start_interval:end_interval] = np.maximum.accumulate(sessions[i, start_interval:end_interval])
            else:
                break  # No more power needed in the remaining intervals
    return sessions


def adjust_charging_sessions(sessions, average_demand, N, nominal_power, total_intervals, error_tolerance):
    np.random.seed(555)
    # Target ranges from 90% to 100% of average_demand
    lower_bound = 0.9 * average_demand
    upper_bound = average_demand

    for interval in range(total_intervals):
        # Calculate the average load for the current interval
        current_load = np.mean(sessions[:, interval])

        # If the load is above the upper bound, zero out some charging sessions
        if current_load > upper_bound[interval]:
            # Find sessions to zero out
            overcharging_evs = np.where(sessions[:, interval] > 0)[0]
            for ev in overcharging_evs:
                # Zero out the session for this interval
                sessions[ev, interval] = 0
                current_load = np.mean(sessions[:, interval])
                if current_load <= upper_bound[interval]:
                    break

        # If the load is below the lower bound, increase power for some sessions
        elif current_load < lower_bound[interval]:
            # Find sessions to increase
            undercharging_evs = np.where(sessions[:, interval] < nominal_power)[0]
            for ev in undercharging_evs:
                # Increase the session to nominal power for this interval
                sessions[ev, interval] = nominal_power
                current_load = np.mean(sessions[:, interval])
                if current_load >= lower_bound[interval]:
                    break

        # After adjustments, check if we are within the error tolerance
        if not (lower_bound[interval] <= current_load <= upper_bound[interval] + error_tolerance):
            # If not, we need a more refined adjustment, which may include redistributing power from other intervals
            # Implement refined adjustment logic here...
            pass

    return sessions


def balance_demand_with_zero_sessions(sessions, average_demand, N, nominal_power, total_intervals, min_power):
    np.random.seed(555)
    zero_event_sessions = np.where(np.all(sessions == 0, axis=1))[0]

    for ev in zero_event_sessions:
        for interval in range(total_intervals):
            current_load = np.mean(sessions[:, interval])
            demand_gap = average_demand[interval] - current_load

            if demand_gap > 0 and sessions[ev, interval] == 0:
                additional_power = nominal_power
                sessions[ev, interval] = additional_power

                # After assigning power, recheck the demand gap
                current_load = np.mean(sessions[:, interval])
                demand_gap = average_demand[interval] - current_load
                if demand_gap <= 0:
                    break

    return sessions


def adjust_charging_sessions_2(sessions, average_demand, N, nominal_power, total_intervals, error_tolerance, max_charging_events, min_power):
    np.random.seed(555)
    
    lower_bound = 0.9 * average_demand
    upper_bound = average_demand

    # First Pass: Adjust sessions for average demand
    for interval in range(total_intervals):
        current_load = np.mean(sessions[:, interval])

        if current_load > upper_bound[interval]:
            overcharging_evs = np.where(sessions[:, interval] > 0)[0]
            for ev in overcharging_evs:
                sessions[ev, interval] = 0
                current_load = np.mean(sessions[:, interval])
                if current_load <= upper_bound[interval]:
                    break

        elif current_load < lower_bound[interval]:
            undercharging_evs = np.where(sessions[:, interval] < nominal_power)[0]
            for ev in undercharging_evs:
                sessions[ev, interval] = nominal_power
                current_load = np.mean(sessions[:, interval])
                if current_load >= lower_bound[interval]:
                    break

    # Second Pass: Eliminate zero-event sessions
    for i in range(N):
        if np.all(sessions[i, :] == 0):
            # Introduce charging events while trying to maintain average demand
            added_events = 0
            while added_events < max_charging_events + 1 and np.all(sessions[i, :] == 0):
                interval = np.random.randint(total_intervals)
                if sessions[i, interval] == 0:
                    sessions[i, interval] = np.random.uniform(min_power, nominal_power)
                    added_events += 1

                # Check if the adjustment is still within the average demand bounds
                current_load = np.mean(sessions[:, interval])
                if current_load > upper_bound[interval]:
                    sessions[i, interval] = 0  # Revert if it exceeds the upper bound

    return sessions


def count_charging_cycles(sessions):
    cycles_count = np.zeros(sessions.shape[0])
    for i in range(sessions.shape[0]):
        if sessions[i, 0] > 0:
            # Start with a count of one if the first item is non-zero
            cycles_count[i] = 1
        else:
            # Otherwise, start with a count of zero
            cycles_count[i] = 0

        # Count transitions from zero to non-zero
        zero_to_non_zero = np.diff((sessions[i, :] > 0).astype(int)) == 1
        cycles_count[i] += np.sum(zero_to_non_zero)

    return cycles_count

