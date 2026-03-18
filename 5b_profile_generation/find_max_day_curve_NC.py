# -*- coding: utf-8 -*-
"""
Created on Mon Mar 24 07:23:39 2025

@author: luisfernando
"""

import os
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pandas as pd
from datetime import timedelta
import sys
import time
from pathlib import Path

START_PROCESS = time.time()

STR_STATE = 'NC'
STR_TITLE = STR_STATE

EXTERNAL_FOLDER_STR = '3c_eulp_downloads'

# 🔹 NEW: Store df_curve per feeder
df_curve_per_feeder = {}  # 🔹 NEW

# Load required parquet summary
df_summary_result = pd.read_csv(STR_STATE + "_required_parquets_per_feeder.csv")

# Dictionary to store peak daily curves per month per feeder
peak_load_curves = {}

# Dictionary to store max loads per month per feeder
max_load_per_month = {}

# Iterate per substation (Feeder)
for feeder in df_summary_result["Feeder"].unique():
    print(f"Processing feeder: {feeder}")

    # Filter data for current feeder
    df_feeder = df_summary_result[df_summary_result["Feeder"] == feeder]

    # Initialize total load curve (empty array to accumulate)
    total_curve = None

    # Iterate through each load profile in the feeder
    for _, row in df_feeder.iterrows():
        # parquet_path = './' + row["Parquet_Folder"] + '/' + row["Parquet_File"]
        parquet_path = Path('..') / EXTERNAL_FOLDER_STR / row['Parquet_Folder'] / row['Parquet_File']

        # print('Check path')
        # sys.exit()

        try:
            # Read parquet file
            table = pq.read_table(parquet_path)
            # print("FOUND")
            '''
            USE THIS WHEN WANTING TO ADD MORE COLUMNS
            
            df = table.to_pandas()
            x = df.columns.tolist()
            '''
        except Exception as e:
            print(f"Error reading {parquet_path}: {e}")
            table = 'Nothing'
            continue

        if table != 'Nothing':
            # Extract "total demand" column (UPDATE this with correct column name)
            energy_consumption = table["out.electricity.total.energy_consumption"].to_numpy()

            # This is needed if we assume the above is power times 0.25
            power_demand = energy_consumption * 4

            # print('FIND IF WE REACHED HERE PLEASE')
            # sys.exit()

            # Scale demand curve by REAL_LOAD_COUNT
            scaled_demand = power_demand * row["REAL_LOAD_COUNT"]

            # Accumulate demand curve
            if total_curve is None:
                total_curve = scaled_demand
            else:
                total_curve += scaled_demand



    # Once all loads are accumulated for this feeder, compute peak daily curves
    if total_curve is not None:
        # print('ENTERS?')
        
        # Create a time index assuming first point is Jan 1st 00:00 and 15-min intervals
        start_time = pd.Timestamp("2025-01-01 00:00:00")
        time_index = [start_time + timedelta(minutes=15 * i) for i in range(len(total_curve))]

        # Create DataFrame for easier time-based aggregation
        df_curve = pd.DataFrame({"time": time_index, "demand": total_curve})

        # Extract month & day
        df_curve["month"] = df_curve["time"].dt.month
        df_curve["day"] = df_curve["time"].dt.date

        # ✅ FIXED: Find the day with the highest total demand per month
        daily_max_peaks = df_curve.groupby(["month", "day"])["demand"].max()  # Max point each day
        peak_days = daily_max_peaks.groupby("month").idxmax()  # Day with the highest peak in the month

        # Store full 24-hour load curve for each peak day
        peak_curves = {}
        for month, peak_day in peak_days.items():
            peak_day_date = peak_day[1]  # Extract only the date part
            df_curve["day"] = df_curve["time"].dt.date  # Extract date properly
            daily_curve = df_curve[df_curve["day"] == peak_day_date].copy()

            # print('matched?')
            # sys.exit()

            # Ensure exactly 96 points (24 hours at 15-min intervals)
            if len(daily_curve) != 96:
                print(f"⚠️ Incomplete daily curve for {feeder} month {month}, skipping...")
                continue
    
            peak_curves[month] = {
                "date": peak_day,
                "curve": daily_curve["demand"].to_numpy()
            }

        # Store results for the feeder
        peak_load_curves[feeder] = peak_curves

    # Inside your main feeder loop (after df_curve is created)
    df_curve_per_feeder[feeder] = df_curve.copy()  # 🔹 NEW

# Convert results into structured DataFrame
records = []
for feeder, months in peak_load_curves.items():
    for month, data in months.items():
        records.append([feeder, month, data["date"], *data["curve"]])

columns = ["Feeder", "Month", "Peak Day"] + [f"Point_{i}" for i in range(96)]
df_peak_daily = pd.DataFrame(records, columns=columns)

import matplotlib.pyplot as plt

# Define month names for better readability
month_names = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

# 🔹 NEW: Loop through each feeder for plotting
for feeder, df_curve in df_curve_per_feeder.items():  #
    # Create subplots (3x4 grid for 12 months)
    fig, axes = plt.subplots(3, 4, figsize=(20, 12), sharex=True, sharey=True)
    axes = axes.flatten()

    # Time labels (15-min intervals over 24 hours)
    time_labels = [f"{h}:00" for h in range(0, 24)]

    # Generate 12 spaghetti plots, one per month
    for i, month in enumerate(range(1, 13)):
        ax = axes[i]

        # Filter all daily curves for the current month from `df_curve`
        df_month = df_curve[df_curve["month"] == month]

        # Plot all daily curves (background)
        for day in df_month["day"].unique():
            daily_curve = df_month[df_month["day"] == day]["demand"].to_numpy()
            if len(daily_curve) == 96:  # Ensure correct shape
                ax.plot(range(96), daily_curve, alpha=0.2, color="gray")  # Light gray for all curves

        # Filter data for the current month
        df_peak_month  = df_peak_daily[(df_peak_daily["Month"] == month) & (df_peak_daily["Feeder"] == feeder)]  # 🔹 NEW

        # Plot the maximum peak curve in bold for distinction
        if not df_peak_month.empty:
            max_peak_row = df_peak_month.loc[df_peak_month["Peak Day"].idxmax()]
            max_peak_curve = max_peak_row[3:].to_numpy()
            ax.plot(range(96), max_peak_curve, alpha=1.0, color="red", linewidth=2, label="Max Peak")

        # Formatting
        ax.set_xticks(range(0, 96, 8))
        ax.set_xticklabels(time_labels[::2], rotation=45)
        ax.set_title(f"{month_names[month]}")
        ax.set_ylabel("Demand (kW)")
        ax.grid(True, linestyle="--", alpha=0.5)

    # Overall figure adjustments
    fig.suptitle(f"Peak Daily Curves per Month (Spaghetti Plots) – Feeder: {feeder}", fontsize=16)
    fig.tight_layout()
    plt.show()

# Display results
# import ace_tools as tools
# tools.display_dataframe_to_user(name="Max Load per Month per Feeder", dataframe=df_max_loads)

# 🔹 NEW: Identify winter and summer peak days per feeder
print("\n🔍 Peak Days Summary (Winter & Summer):\n")  # 🔹 NEW
for feeder in df_peak_daily["Feeder"].unique():  # 🔹 NEW
    df_feeder = df_peak_daily[df_peak_daily["Feeder"] == feeder]  # 🔹 NEW

    # Winter months
    df_winter = df_feeder[df_feeder["Month"].isin([1, 2, 12])]
    if not df_winter.empty:
        winter_peak = df_winter.loc[df_winter["Peak Day"].idxmax()]  # Highest single point in winter
        winter_peak_value = max(winter_peak[3:])  # 🔹 NEW: Get max kW in curve
        print(f"Feeder {feeder} - ❄️ Winter Peak Day: {winter_peak['Peak Day']} (Month {winter_peak['Month']}) – Peak Value: {winter_peak_value:.2f} kW")  # 🔹 NEW

    # Summer months
    df_summer = df_feeder[df_feeder["Month"].isin([6, 7, 8])]
    if not df_summer.empty:
        summer_peak = df_summer.loc[df_summer["Peak Day"].idxmax()]
        summer_peak_value = max(summer_peak[3:])  # 🔹 NEW: Get max kW in curve
        print(f"Feeder {feeder} - ☀️ Summer Peak Day: {summer_peak['Peak Day']} (Month {summer_peak['Month']}) – Peak Value: {summer_peak_value:.2f} kW")  # 🔹 NEW

# 🔁 Slicing and saving only winter/summer peak day parquets
BOOL_SAVE_SLICES = True
if BOOL_SAVE_SLICES:
    for feeder in df_peak_daily["Feeder"].unique():
        df_feeder_peaks = df_peak_daily[df_peak_daily["Feeder"] == feeder]

        # Get WINTER peak day
        df_winter = df_feeder_peaks[df_feeder_peaks["Month"].isin([1, 2, 12])]
        if not df_winter.empty:
            winter_peak = df_winter.loc[df_winter["Peak Day"].idxmax()]
            winter_peak_date = winter_peak["Peak Day"]

            season = "winter"
            output_dir = f"./daily_parquets/{STR_STATE}_{feeder.replace('--', '_')}_{season}"
            os.makedirs(output_dir, exist_ok=True)

            df_feeder_rows = df_summary_result[df_summary_result["Feeder"] == feeder]
            for _, row in df_feeder_rows.iterrows():
                # parquet_path = './' + row["Parquet_Folder"] + '/' + row["Parquet_File"]
                parquet_path = Path('..') / EXTERNAL_FOLDER_STR / row['Parquet_Folder'] / row['Parquet_File']
                try:
                    table = pq.read_table(parquet_path)
                    df_full = table.to_pandas()
                    df_full["timestamp"] = pd.to_datetime(df_full["timestamp"])

                    # Extract target day/month from peak date (ignore year)
                    target_date = winter_peak_date[1]
                    target_month = target_date.month
                    target_day = target_date.day

                    # Filter by month and day only (ignore year)
                    df_day = df_full[(df_full["timestamp"].dt.month == target_month) &
                                    (df_full["timestamp"].dt.day == target_day)]

                    if not df_day.empty:
                        out_path = f"{output_dir}/{row['Parquet_File']}"
                        df_day.to_parquet(out_path, index=False)
                        # print(f"✅ Saved WINTER day for {feeder} to {out_path}")
                    else:
                        print(f"⚠️ Emptiness for WINTER day for {feeder} to {out_path}")
                        sys.exit(1)
                except Exception as e:
                    print(f"⚠️ Winter error reading {parquet_path}: {e}")
                    sys.exit(2)

        # Get SUMMER peak day
        df_summer = df_feeder_peaks[df_feeder_peaks["Month"].isin([6, 7, 8])]
        if not df_summer.empty:
            summer_peak = df_summer.loc[df_summer["Peak Day"].idxmax()]
            summer_peak_date = summer_peak["Peak Day"]

            season = "summer"
            output_dir = f"./daily_parquets/{STR_STATE}_{feeder.replace('--', '_')}_{season}"
            os.makedirs(output_dir, exist_ok=True)

            df_feeder_rows = df_summary_result[df_summary_result["Feeder"] == feeder]
            for _, row in df_feeder_rows.iterrows():
                # parquet_path = './' + row["Parquet_Folder"] + '/' + row["Parquet_File"]
                parquet_path = Path('..') / EXTERNAL_FOLDER_STR / row['Parquet_Folder'] / row['Parquet_File']
                try:
                    table = pq.read_table(parquet_path)
                    df_full = table.to_pandas()
                    df_full["timestamp"] = pd.to_datetime(df_full["timestamp"])

                    # Extract target day/month from peak date (ignore year)
                    target_date = summer_peak_date[1]
                    target_month = target_date.month
                    target_day = target_date.day

                    # Filter by month and day only (ignore year)
                    df_day = df_full[(df_full["timestamp"].dt.month == target_month) &
                                    (df_full["timestamp"].dt.day == target_day)]

                    if not df_day.empty:
                        out_path = f"{output_dir}/{row['Parquet_File']}"
                        df_day.to_parquet(out_path, index=False)
                        # print(f"✅ Saved SUMMER day for {feeder} to {out_path}")
                    else:
                        print(f"⚠️ Emptiness for SUMMER day for {feeder} to {out_path}")
                        sys.exit(3)
                except Exception as e:
                    print(f"⚠️ Summer error reading {parquet_path}: {e}")
                    sys.exit(4)


END_PROCESS = time.time()
TIME_ELAPSED = -START_PROCESS + END_PROCESS
print(str(TIME_ELAPSED) + ' seconds /', str(TIME_ELAPSED/60) + ' minutes.')

