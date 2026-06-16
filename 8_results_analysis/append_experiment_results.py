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
from pipeline_utils import load_config, resolve_work_path

# --- Configuration ------------------------------------------------------------
cfg = load_config()
STATE = cfg['state']

# Resolve season: PIPELINE_SEASON env var (set by run_case.py per season loop)
# takes priority, then fall back to pipeline_config.yaml.  Never silently
# default to 'unknown' — that masks the very bug this fix addresses.
_env_season = os.environ.get("PIPELINE_SEASON", "").strip().lower()
_cfg_season = cfg.get("season", "").strip().lower()
SEASON = _env_season or _cfg_season
if not SEASON:
    raise RuntimeError(
        "Cannot resolve season: neither PIPELINE_SEASON env var nor "
        "pipeline_config.yaml 'season' key is set.  Fix your config."
    )
VALID_SEASONS = {"summer", "winter"}
if SEASON not in VALID_SEASONS:
    raise ValueError(
        f"Season '{SEASON}' not in {VALID_SEASONS}. "
        f"Check PIPELINE_SEASON env var or pipeline_config.yaml."
    )
print(f"[append] season = '{SEASON}'  (source: {'env PIPELINE_SEASON' if _env_season else 'pipeline_config.yaml'})")

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
            print(f"  ⚠️  Not found, skipping: {in_path}")
            continue

        df = pd.read_csv(in_path, low_memory=False)
        # Drop typical accidental index columns if present
        df = df.loc[:, ~df.columns.str.contains(r"^Unnamed:")].copy()

        df["season"] = SEASON
        df["design"] = STATE

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
        combine_and_save(Path("."), OUTPUT_DIR, FOLDERS, in_name, out_name)

    print("\nAll done.")
