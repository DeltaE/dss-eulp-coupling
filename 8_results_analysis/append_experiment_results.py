# -*- coding: utf-8 -*-
"""
Created on Wed Nov 12 18:19:52 2025

@author: luisfernando
"""

# Minimal, procedural script for appending CSVs across run folders and tagging season/design.

from pathlib import Path
import os
import re
import sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_work_path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '7_circuit_instantiation', 'deployer_modules'))
from load_voltage import circuit_summary

# --- Configuration ------------------------------------------------------------
cfg = load_config()
STATE = cfg['state']

# Season: PIPELINE_SEASON, set by run_case.py for each season. load_config exits 1
# when it is unset.
SEASON = cfg['season'].strip().lower()
VALID_SEASONS = {"summer", "winter"}
if SEASON not in VALID_SEASONS:
    raise ValueError(
        f"Season '{SEASON}' not in {VALID_SEASONS}. "
        f"Check PIPELINE_SEASON."
    )
print(f"[append] season = '{SEASON}'  (source: env PIPELINE_SEASON)")

OUTPUT_DIR = Path(resolve_work_path("8_results_analysis"))
OUTPUT_DIR.mkdir(exist_ok=True)

# The folders of interest (exact names as you provided)
FOLDERS = [
    resolve_work_path("7_circuit_instantiation")
]

# The input -> output filenames you want to combine
TARGET_FILES = [
    ("aggregate_m2.csv", "aggregate_m2_combined.csv"),
    ("circuit_summary.csv", "circuit_summary_combined.csv"),
    ("heating_assignment__FULL.csv", "heating_assignment__FULL_combined.csv"),
]


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
        in_path = base_dir / subdir / input_filename

        if not in_path.exists():
            print(f"  ❌ Missing input file {input_filename} at {in_path}")
            sys.exit(1)

        df = pd.read_csv(in_path, low_memory=False)
        # Drop typical accidental index columns if present
        df = df.loc[:, ~df.columns.str.contains(r"^Unnamed:")].copy()

        df["season"] = SEASON
        df["design"] = STATE

        frames.append(df)
        print(f"  ✓ Added {len(df):,} rows from {in_path}")

    if not frames:
        print(f"  ❌ No input file {input_filename} found in {folders}")
        sys.exit(1)

    combined = pd.concat(frames, axis=0, ignore_index=True)
    out_path = output_dir / output_filename
    combined.to_csv(out_path, index=False)
    print(f"  ✅ Wrote {len(combined):,} rows → {out_path}")
    return combined


def load_voltage_summary(circuits_dir: Path, output_dir: Path) -> pd.DataFrame:
    """
    One row per circuit folder (<substation>_circuit_<n>_<scenario>) of circuits_dir,
    from its ModifiedCircuitData/load_voltage_loads.csv, over customer loads only
    (ev_leg False, see circuit_summary): lowest and highest load v_pu of the day, loads
    ever below and above voltage_band, and load-steps outside it.
    Saves load_voltage_summary.csv in output_dir. Stops if a circuit has no file.
    """
    band = cfg.get("voltage_band") or {}
    low, high = float(band["low_pu"]), float(band["high_pu"])
    rows = []
    print("\n=== Load voltage summary ===")
    for circuit_dir in sorted(circuits_dir.iterdir(), key=lambda p: p.name.lower()):
        if not (circuit_dir.is_dir() and re.match(r"^(.+)_(circuit_\d+)_(.+)$", circuit_dir.name, re.IGNORECASE)):
            continue
        in_path = circuit_dir / "ModifiedCircuitData" / "load_voltage_loads.csv"
        if not in_path.exists():
            print(f"  Missing input file {in_path}")
            sys.exit(1)
        rows.append({"circuit_folder": circuit_dir.name,
                     **circuit_summary(pd.read_csv(in_path), low, high)})
    out_path = output_dir / "load_voltage_summary.csv"
    summary = pd.DataFrame(rows)
    summary.to_csv(out_path, index=False)
    print(f"  Wrote {len(summary):,} rows -> {out_path}")
    return summary


# --- Main ---------------------------------------------------------------------
if __name__ == "__main__":
    # If your script is not in the parent folder, uncomment and set an absolute path:
    # BASE_DIR = Path(r"C:\path\to\parent\folder")

    for in_name, out_name in TARGET_FILES:
        combine_and_save(Path("."), OUTPUT_DIR, FOLDERS, in_name, out_name)

    load_voltage_summary(Path(resolve_work_path("7_circuit_instantiation")), OUTPUT_DIR)

    print("\nAll done.")
