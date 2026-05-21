# -*- coding: utf-8 -*-
"""
Created on Sat Mar  8 13:46:25 2025

@author: luisfernando
"""

import os
import sys
import argparse
from pathlib import Path
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_config_path


parser = argparse.ArgumentParser()
parser.add_argument("--smartds-root", default=None, help="Override smart_ds_root from config")
parser.add_argument("--max-feeders", type=int, default=None, help="Limit feeder count")
parser.add_argument("--output", default="parsed_loads.csv", help="Output CSV path")
args = parser.parse_args()

cfg = load_config()
SMARTDS_ROOT = resolve_config_path(args.smartds_root or cfg.get("smart_ds_root", "../3_smartds"))

# Store extracted data
data = []

root = Path(SMARTDS_ROOT)

if not root.exists():
    sys.stderr.write(f"SMART-DS root not found: {root}\n")
    sys.exit(1)

candidates = [p for p in root.rglob("Loads.dss")]
feeder_dirs = sorted(set(p.parent for p in candidates), key=lambda p: p.as_posix().lower())

if args.max_feeders is not None:
    feeder_dirs = feeder_dirs[:args.max_feeders]

for feeder_dir in feeder_dirs:
    Substation = feeder_dir.parent.name
    Feeder = feeder_dir.name
    file_path = feeder_dir / "Loads.dss"
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.readlines()

    # Process each line
    seen_loads = set()
    for line in content:
        if line.strip():  # Skip empty lines
            parts = line.split()
            load_name = None
            phase = None
            kw = None
            kvar = None
            yearly = None

            for part in parts:
                if part.startswith("Load.load_"):
                    load_name = part.split(".")[-1].replace('_1', '')  # Extract Load.load_xxx
                    # base_load_name = "_".join(load_name.split("_")[:-1])  # Remove _1 or _2
                    #print('CATCH 1')

                elif part.startswith("Phases="):
                    phase = part.split("=")[1]
                    #print('CATCH 2')

                elif part.startswith("kW="):
                    kw = float(part.split("=")[1])
                    #print('CATCH 3')

                elif part.startswith("kvar="):
                    kvar = float(part.split("=")[1])
                    #print('CATCH 4')

                elif part.startswith("yearly="):
                    yearly = part.split("=")[1]
                    #print('CATCH 5')

            # Extract 'res' or 'com' and yearly reference number
            if yearly:
                yearly_type = yearly.split("_")[0]  # Extract res or com
                yearly_number = yearly.split("_")[2]  # Extract the number

            else:
                yearly_type = None
                yearly_number = None

            # Ensure we count unique loads only once (ignoring _1, _2 distinction)
            if load_name and load_name not in seen_loads:
                seen_loads.add(load_name)

                # Store extracted info
                data.append([Substation, Feeder, load_name, phase, kw, kvar, yearly_type, yearly_number])

            # print('arrived here')
            # sys.exit()

# Convert to DataFrame
df = pd.DataFrame(data, columns=["Substation", "Feeder", "Load_Name", "Phases", "kW", "kvar", "Yearly_Type", "Yearly_Number"])
df.to_csv(args.output, index=False, encoding="utf-8")
print(f"Scanned {len(feeder_dirs)} feeders, found {len(data)} unique loads")
print(f"Output: {args.output}")

#
