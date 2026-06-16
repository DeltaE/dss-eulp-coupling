"""
gather_m2_cases.py  (v2 — per-season workspace layout)

Stack per-case per-season aggregate_m2_combined.csv files into ONE tidy CSV.

New layout (after per-season workspace fix):
    runs/{case}/{season}/workspace/8_results_analysis/aggregate_m2_combined.csv

Drop this in the repo root and run:
    python gather_m2_cases.py
"""

import sys
from pathlib import Path
import pandas as pd

# %% config -----------------------------------------------------------------

CASES = [
    "NC_GSO_urban__NC",
    "NC_GSO_urban__TX",
    "TX_AUS_urban__TX",
    "TX_AUS_urban__NC",
]

SEASONS = ["summer", "winter"]

REPO_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
RUNS_DIR = REPO_ROOT / "runs"
REL_CSV = Path("workspace") / "8_results_analysis" / "aggregate_m2_combined.csv"

OUT_PATH = REPO_ROOT / "m2_all_cases_all_seasons.csv"

# %% gather ------------------------------------------------------------------

frames = []
col_sets = {}

for case in CASES:
    for season in SEASONS:
        csv_path = RUNS_DIR / case / season / REL_CSV
        if not csv_path.exists():
            print(f"[SKIP] {case} x {season}: {csv_path}")
            continue

        df = pd.read_csv(csv_path, low_memory=False)
        key = f"{case}__{season}"
        col_sets[key] = list(df.columns)

        topology, donor = case.split("__")
        df.insert(0, "donor", donor)
        df.insert(0, "topology", topology)
        df.insert(0, "case", case)

        frames.append(df)
        print(f"[OK] {case:20s} {season:6s} {len(df):>5d} rows")

if not frames:
    print("[ERROR] No result files found. Did the pipeline finish?")
    sys.exit(1)

# Column-parity check
base_key = list(col_sets.keys())[0]
base_cols = col_sets[base_key]
for key, cols in col_sets.items():
    if cols != base_cols:
        print(f"[WARN] {key} columns differ from {base_key}:")
        print(f"       only in {key}:       {set(cols) - set(base_cols)}")
        print(f"       only in {base_key}:  {set(base_cols) - set(cols)}")

combined = pd.concat(frames, ignore_index=True)
combined.to_csv(OUT_PATH, index=False)

print("-" * 60)
print(f"[DONE] {len(combined)} rows  ->  {OUT_PATH}")
print(combined.groupby(["case", "season"]).size().to_string())
