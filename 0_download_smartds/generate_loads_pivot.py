# -*- coding: utf-8 -*-
"""
Generate the load summary CSV used by downstream scaling scripts.
"""

import argparse

import pandas as pd


parser = argparse.ArgumentParser()
parser.add_argument("--input", default="parsed_loads.csv", help="Input CSV from scan_feeders.py")
parser.add_argument("--output", default="parsed_loads_SUMMARY.csv", help="Output summary CSV")
args = parser.parse_args()

input_path = args.input
output_path = args.output

df = pd.read_csv(input_path)

# Group and count
grouped = df.groupby(
    ["Feeder", "Phases", "Yearly_Type", "Yearly_Number"]
)["Load_Name"].count().reset_index()
grouped.rename(columns={"Load_Name": "Count_of_Load_Name"}, inplace=True)

phase_numbers = pd.to_numeric(grouped["Phases"], errors="coerce")

# REAL_LOAD_COUNT: halve single-phase counts (SMART-DS duplicates them)
grouped["REAL_LOAD_COUNT"] = grouped.apply(
    lambda row: row["Count_of_Load_Name"] / 2 if int(phase_numbers.loc[row.name]) == 1
    else row["Count_of_Load_Name"],
    axis=1
).astype(int)

# Pre-compute the parquet name (used downstream by scale_feeder_curves.py)
grouped["Parquet_Name"] = grouped["Yearly_Type"] + "_" + grouped["Yearly_Number"].astype(str) + ".parquet"

columns = [
    "Feeder",
    "Phases",
    "Yearly_Type",
    "Yearly_Number",
    "Count_of_Load_Name",
    "REAL_LOAD_COUNT",
    "Parquet_Name",
]
grouped = grouped[columns]

grouped.to_csv(output_path, index=False, encoding="utf-8")

print(f"Feeders: {grouped['Feeder'].nunique()}")
print(f"Total load count: {grouped['Count_of_Load_Name'].sum()}")
print(f"Output: {output_path}")
