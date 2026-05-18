# -*- coding: utf-8 -*-
"""
Module Name: pfs_parsing_misc.py  (pfs stands for power flow support)
Description:
    This module contains utility functions to parse transformer, line, and load data
    for power flow simulations in OpenDSS. It's designed to support `power_flow_sim.py`
    by extracting necessary components from textual circuit descriptions, facilitating
    automated manipulation and analysis of power flow data.

Functions:
    - parse_transformers(file_content, lines): Parses transformers from a given textual input.
    - parse_lines(file_content): Parses lines from a given textual input.
    - parse_loads(file_content): Parses loads from a given textual input.

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


def parse_transformers(file_content, lines):
    """
    Parses transformer data from a given file content.

    Parameters:
    - file_content (str): The content of the file containing transformer definitions.
    - lines (dict): A dictionary containing line data, used to categorize lines connected to transformers.

    Returns:
    - dict: A dictionary where keys are transformer names and values are dictionaries containing details about phases, kVA rating, buses, and connected mid and low voltage lines.
    """
    transformers = {}
    for line in file_content.splitlines():
        if line.startswith("New Transformer."):
            parts = line.split()
            name = parts[1]
            phases = re.search(r'phases=(\d)', line).group(1)
            kva_rating = float(re.search(r'kva=(\d+\.?\d*)', line).group(1))

            # Extract buses, capturing only the part before the first dot
            buses = re.findall(r'bus=([^\s.]+)', line)

            transformers[name] = {
                'phases': phases,
                'kva_rating': kva_rating,
                'buses': buses,
                'mid_voltage_lines': [],
                'low_voltage_lines': []
            }

            # Categorize lines based on their connection to mid or low voltage buses
            mid_voltage_bus = buses[0]  # First bus is assumed to be mid voltage
            low_voltage_buses = buses[1:]  # Remaining buses are low voltage

            for line_name, line_data in lines.items():
                # Lowercase line name for case-insensitive comparison
                line_name_lower = line_name.lower()
            
                # Enhanced Rule 1: Exclude lines based on specific patterns
                exclusion_patterns = ["padswitch", "con", "disswitch", "_disconnect", "_cont"]
                if any(substring in line_name_lower for substring in exclusion_patterns):
                    continue
            
                # Rule 2: Identify low-voltage lines specifically with "lv)" or "lv-"
                if "lv)" in line_name_lower or "lv-" in line_name_lower:
                    for lv_bus in low_voltage_buses:
                        if line_data['bus1'].startswith(lv_bus) or line_data['bus2'].startswith(lv_bus):
                            transformers[name]['low_voltage_lines'].append(line_name)
                else:
                    # Rule 3: Classify remaining lines as mid-voltage
                    if line_data['bus1'].startswith(mid_voltage_bus) or line_data['bus2'].startswith(mid_voltage_bus):
                        transformers[name]['mid_voltage_lines'].append(line_name)

    return transformers


def parse_lines(file_content):
    """
    Parses line data from given file content.

    Parameters:
    - file_content (str): The content of the file containing line definitions.

    Returns:
    - dict: A dictionary where keys are line names and values are dictionaries containing details about bus1 and bus2 connected to the line.
    """
    lines = {}
    for line in file_content.splitlines():
        if line.startswith("New Line."):
            parts = line.split()
            name = parts[1]

            # Extract buses, capturing only the part before the first dot
            bus1 = re.search(r'bus1=([^\s.]+)', line).group(1)
            bus2 = re.search(r'bus2=([^\s.]+)', line).group(1)

            lines[name] = {'bus1': bus1, 'bus2': bus2}

        #if 'Line.l(r:p10udt1712-p10udt2247)' in line:
        #    print('worked?')
        #    print(name)
        #    sys.exit()

    return lines


def parse_loads(file_content):
    """
    Parses load data from given file content.

    Parameters:
    - file_content (str): The content of the file containing load definitions.

    Returns:
    - dict: A dictionary where keys are load names and values are dictionaries containing details such as connection type, bus, voltage level, min and max voltage in per unit, load model, kW, kvar, and phases.
    """
    loads = {}
    for line in file_content.splitlines():
        if line.startswith("New Load."):
            parts = line.split()
            name = parts[1]

            # Extracting parameters using regex
            conn = re.search(r'conn=([^\s]+)', line).group(1)
            bus1 = re.search(r'bus1=([^\s.]+)', line).group(1)
            kV = re.search(r'kV=([^\s]+)', line).group(1)
            Vminpu = re.search(r'Vminpu=([^\s]+)', line).group(1)
            Vmaxpu = re.search(r'Vmaxpu=([^\s]+)', line).group(1)
            model = re.search(r'model=([^\s]+)', line).group(1)
            kW = re.search(r'kW=([^\s]+)', line).group(1)
            kvar = re.search(r'kvar=([^\s]+)', line).group(1)
            phases = re.search(r'Phases=([^\s]+)', line).group(1)

            # Adding to the dictionary
            loads[name] = {
                'conn': conn, 'bus1': bus1, 'kV': kV, 
                'Vminpu': Vminpu, 'Vmaxpu': Vmaxpu, 
                'model': model, 'kW': kW, 'kvar': kvar, 
                'Phases': phases
            }

    return loads


# Function to check if more 1s can be added to the row
def can_add_more(row, target_sums):
    return np.sum(row) < sum(target_sums)


# Function to update target sums based on the current state of 'missing_ev_profiles'
def update_target_sums(profiles, target_sums):
    current_sums = np.sum(profiles, axis=0)
    return [max(0, ts - cs) for ts, cs in zip(target_sums, current_sums)]


# Function for simple linear interpolation
def linear_interpolate(start, end):
    return [start + (end - start) * i / 4 for i in range(1, 4)]

