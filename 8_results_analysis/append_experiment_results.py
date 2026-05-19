# -*- coding: utf-8 -*-
"""
Created on Wed Nov 12 18:19:52 2025

@author: luisfernando
"""

# Minimal, procedural script for appending CSVs across run folders and tagging season/design.

from pathlib import Path
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config

# --- Configuration ------------------------------------------------------------
cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']

# Parent directory that contains the pipeline folders below.
BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIR = BASE_DIR / "8_results_analysis"
OUTPUT_DIR.mkdir(exist_ok=True)

# The folders of interest (exact names as you provided)
FOLDERS = [
    "7_circuit_instantiation"
]

# The input -> output filenames you want to combine
TARGET_FILES = [
    ("aggregate_m2.csv", "aggregate_m2_combined.csv"),
    ("circuit_summary.csv", "circuit_summary_combined.csv"),
    ("heating_assignment__FULL.csv", "heating_assignment__FULL_combined.csv"),
]

# --- Helpers ------------------------------------------------------------------
def parse_context(subdir_name: str):
    """
    Infer season and design from the folder name.
    Returns (season, design), e.g., ('winter', 'lhs_100').
    """
    name = subdir_name.lower()
    season = "summer" if "summer" in name else ("winter" if "winter" in name else "unknown")

    # Check specific designs; order matters because 'lhs' is a substring of 'lhs_100'
    design = STATE

    return season, design


def combine_and_save(base_dir: Path, output_dir: Path,
                     folders: list, input_filename: str, output_filename: str) -> pd.DataFrame:
    """
    Read `input_filename` from each folder in `folders`, add `season` and `design`,
    append all rows, and save as `output_filename` in `base_dir`.
    Returns the combined DataFrame (or empty if nothing found).
    """
    frames = []

    print(f"\n=== Combining: {input_filename} ===")
    for subdir in folders:
        season, design = parse_context(subdir)
        in_path = base_dir / subdir / input_filename

        if not in_path.exists():
            print(f"  ⚠️  Not found, skipping: {in_path}")
            continue

        df = pd.read_csv(in_path, low_memory=False)
        # Drop typical accidental index columns if present
        df = df.loc[:, ~df.columns.str.contains(r"^Unnamed:")].copy()

        df["season"] = season
        df["design"] = design

        frames.append(df)
        print(f"  ✓ Added {len(df):,} rows from {in_path}")

    if not frames:
        print(f"  → No files found for {input_filename}. Nothing written.")
        return pd.DataFrame()

    combined = pd.concat(frames, axis=0, ignore_index=True)
    out_path = output_dir / output_filename
    combined.to_csv(out_path, index=False)
    print(f"  ✅ Wrote {len(combined):,} rows → {out_path}")
    return combined


# --- Main ---------------------------------------------------------------------
if __name__ == "__main__":
    # If your script is not in the parent folder, uncomment and set an absolute path:
    # BASE_DIR = Path(r"C:\path\to\parent\folder")

    for in_name, out_name in TARGET_FILES:
        combine_and_save(BASE_DIR, OUTPUT_DIR, FOLDERS, in_name, out_name)

    print("\nAll done.")
