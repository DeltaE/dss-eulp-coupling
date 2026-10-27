"""
patch_season.py — one-shot fix for season='unknown' in the 2x2 workspace CSVs.
Run from repo root:  python patch_season.py
"""

from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent
SEASON = "summer"

CASES = [
    "NC_GSO_urban__NC",
    "NC_GSO_urban__TX",
    "TX_AUS_urban__TX",
    "TX_AUS_urban__NC",
]

# Every CSV in 8_results_analysis that carries a season column
TARGETS = [
    "aggregate_m2_combined.csv",
    "circuit_summary_combined.csv",
    "heating_assignment__FULL_combined.csv",
]

patched = 0
for case in CASES:
    out_dir = REPO / "runs" / case / "workspace" / "8_results_analysis"
    for fname in TARGETS:
        fpath = out_dir / fname
        if not fpath.exists():
            print(f"[SKIP] {fpath}")
            continue
        df = pd.read_csv(fpath, low_memory=False)
        if "season" not in df.columns:
            print(f"[SKIP] no season col: {fpath}")
            continue
        old = df["season"].unique()
        df["season"] = SEASON
        df.to_csv(fpath, index=False)
        patched += 1
        print(f"[OK] {case}/{fname}  {list(old)} -> '{SEASON}'  ({len(df)} rows)")

print(f"\nPatched {patched} files.")
