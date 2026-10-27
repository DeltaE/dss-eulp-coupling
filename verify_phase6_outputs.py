#!/usr/bin/env python3
"""
verify_phase6_outputs.py - spot-check Phase 6 (kvar) artifacts.

Confirms, for a given case workspace:
  1. kvar_ratios.pkl exists, has sane structure, sampled ratio is length-96 and not all-zero
  2. every 5c_csv_conversion folder has a *_kvar_*.csv for each *_kw_*.csv (count parity)
  3. a sampled kvar CSV is 96 rows, numeric, and not degenerate (all-zero / NaN)

Runs read-only; touches nothing. Run from the repo root.

Usage:
    python verify_phase6_outputs.py
    python verify_phase6_outputs.py runs/NC_GSO_urban__NC/workspace
"""
import os
import sys
import pickle

import numpy as np
import pandas as pd

DEFAULT_WORK_ROOT = os.path.join("runs", "NC_GSO_urban__NC", "workspace")


def main():
    work_root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORK_ROOT
    work_root = os.path.abspath(work_root)
    csv_root = os.path.join(work_root, "5c_csv_conversion")
    ratios_pkl = os.path.join(work_root, "6_kvar_preparation", "kvar_ratios.pkl")

    print(f"work_root : {work_root}")
    print(f"csv_root  : {csv_root}")
    print(f"ratios    : {ratios_pkl}\n")

    problems = []

    # --- 1) kvar_ratios.pkl -------------------------------------------------
    if not os.path.exists(ratios_pkl):
        problems.append(f"MISSING {ratios_pkl}")
        kvar_ratios = {}
    else:
        with open(ratios_pkl, "rb") as f:
            kvar_ratios = pickle.load(f)
        n_parq = len(kvar_ratios)
        rfolders = set()
        for d in kvar_ratios.values():
            rfolders.update(d.keys())
        print(f"[ratios] {n_parq} parquets x {len(rfolders)} folders: {sorted(rfolders)}")
        any_parq = next(iter(kvar_ratios))
        any_folder = next(iter(kvar_ratios[any_parq]))
        arr = np.asarray(kvar_ratios[any_parq][any_folder], dtype=float)
        print(f"[ratios] sample {any_parq} / {any_folder}: len={len(arr)} "
              f"min={np.nanmin(arr):.4f} max={np.nanmax(arr):.4f} "
              f"nonzero={(np.abs(arr) > 1e-12).sum()}/{len(arr)}")
        if len(arr) != 96:
            problems.append(f"ratio array length {len(arr)} != 96")
        if not np.any(np.abs(arr) > 1e-12):
            problems.append("sampled ratio array is ALL ZERO")

    # --- 2) per-folder kw vs kvar parity ------------------------------------
    if not os.path.isdir(csv_root):
        problems.append(f"MISSING {csv_root}")
    else:
        folders = sorted(d for d in os.listdir(csv_root)
                         if os.path.isdir(os.path.join(csv_root, d)))
        print(f"\n[csv] {len(folders)} folders in 5c_csv_conversion")
        sample_pair = None
        for d in folders:
            fp = os.path.join(csv_root, d)
            files = os.listdir(fp)
            kw = sorted(f for f in files if "_kw_" in f and f.endswith(".csv"))
            kv = sorted(f for f in files if "_kvar_" in f and f.endswith(".csv"))
            flag = "" if len(kw) == len(kv) else "  <-- MISMATCH"
            print(f"  {d}: {len(kw)} kw / {len(kv)} kvar{flag}")
            if len(kw) != len(kv):
                problems.append(f"{d}: kw={len(kw)} kvar={len(kv)} parity mismatch")
            if sample_pair is None and kw:
                kv_name = kw[0].replace("_kw_", "_kvar_")
                if kv_name in kv:
                    sample_pair = (fp, kw[0], kv_name)

        # --- 3) sample value sanity ----------------------------------------
        if sample_pair:
            fp, kw_name, kv_name = sample_pair
            kw_vals = pd.read_csv(os.path.join(fp, kw_name), header=None).iloc[:, 0].to_numpy()
            kv_vals = pd.read_csv(os.path.join(fp, kv_name), header=None).iloc[:, 0].to_numpy()
            print(f"\n[sample] {os.path.basename(fp)}/{kw_name}  vs  {kv_name}")
            print(f"  kw   : len={len(kw_vals)} mean={np.nanmean(kw_vals):.4f}")
            print(f"  kvar : len={len(kv_vals)} mean={np.nanmean(kv_vals):.4f} "
                  f"nonzero={(np.abs(kv_vals) > 1e-12).sum()}/{len(kv_vals)} "
                  f"nan={int(np.isnan(kv_vals).sum())}")
            if len(kv_vals) != 96:
                problems.append(f"sample kvar length {len(kv_vals)} != 96")
            if np.isnan(kv_vals).any():
                problems.append("sample kvar has NaN")
            if not np.any(np.abs(kv_vals) > 1e-12):
                problems.append("sample kvar is ALL ZERO")
        else:
            problems.append("no kw/kvar pair found to sample")

    # --- verdict ------------------------------------------------------------
    print("\n" + "=" * 52)
    if problems:
        print("PHASE 6 CHECK: PROBLEMS FOUND")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("PHASE 6 CHECK: PASS - kvar CSVs present, parity holds, values sane")
    sys.exit(0)


if __name__ == "__main__":
    main()
