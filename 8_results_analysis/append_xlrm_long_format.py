# -*- coding: utf-8 -*-
"""
Created on Wed Nov 12 18:42:20 2025

@author: luisfernando
"""

from pathlib import Path
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config

# --- Where to read from / write to -------------------------------------------------
cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "8_results_analysis"
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET_FILE = "mixes_compare_long.csv"
OUT_PATH = OUTPUT_DIR / "mixes_compare_long__code_xlrm_combined.csv"

# Folders to collect from (exact names)
WANTED = {"0_experimental_design"}

# --- Find matching folders (recursive, anywhere under BASE_DIR) --------------------
matching_dirs = []
for name in WANTED:
    for p in BASE_DIR.rglob(name):
        if p.is_dir():
            matching_dirs.append(p)

# If your folders are direct children of BASE_DIR, you can replace the above with:
# matching_dirs = [BASE_DIR / name for name in WANTED if (BASE_DIR / name).is_dir()]

# Deduplicate & sort for stable processing order
matching_dirs = sorted(set(matching_dirs), key=lambda p: str(p).lower())

print("\n=== Combining mixes_compare_long.csv from 0_experimental_design folders ===")
if not matching_dirs:
    print(f"  → No matching folders found under: {BASE_DIR}")

frames = []
for d in matching_dirs:
    csv_path = d / TARGET_FILE
    if not csv_path.exists():
        print(f"  ⚠️  Missing file, skipping: {csv_path}")
        continue

    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as e:
        print(f"  ⚠️  Failed reading {csv_path}: {e}")
        continue

    # Drop stray index columns if present
    df = df.loc[:, ~df.columns.str.contains(r"^Unnamed:")].copy()

    # Add the folder name
    df["source_folder"] = d.name  # or: str(d.relative_to(BASE_DIR)) for the relative path

    frames.append(df)
    print(f"  ✓ {d.name}: {len(df):,} rows")

# --- Write output ------------------------------------------------------------------
if frames:
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(OUT_PATH, index=False)
    print(f"  ✅ Wrote {len(combined):,} rows from {len(frames)} folders → {OUT_PATH}")
else:
    print("  → Nothing to write.")
