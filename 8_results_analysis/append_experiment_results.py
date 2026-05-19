# -*- coding: utf-8 -*-
"""
Created on Wed Nov 12 18:19:52 2025

@author: luisfernando
"""

# Minimal, procedural script for appending CSVs across run folders and tagging season/design.

from pathlib import Path
import pandas as pd

# --- Configuration ------------------------------------------------------------
# Parent directory that contains the four subfolders below.
# In Spyder, Path.cwd() is fine if you set the working directory to the parent folder.
BASE_DIR = Path.cwd().parent

OUTPUT_DIR = BASE_DIR / "9_results_analysis"

# The folders of interest (exact names as you provided)
FOLDERS = [
    "ab_8_summer",
    "ab_8_winter",
    "bc_8_summer",
    "bc_8_winter",
    "on_8_summer",
    "on_8_winter",
    "qc_8_summer",
    "qc_8_winter"
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
    if "ab" in name:
        design = "ab"
    elif "bc" in name:
        design = "bc"
    elif "on" in name:
        design = "on"
    elif "qc" in name:
        design = "qc"
    else:
        design = "unknown"

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
