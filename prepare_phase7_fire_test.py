# -*- coding: utf-8 -*-
"""
prepare_phase7_fire_test.py
---------------------------
Creates everything needed to bridge Phase 5c/6 output → Phase 7 instantiation.

Run from Anaconda Prompt on Machine 3:
    cd /d D:\github\dss-eulp-coupling
    set PIPELINE_STATE=TX
    set PIPELINE_SEASON=summer
    python prepare_phase7_fire_test.py

What this script does:
  1. Builds profhp bridge directories (TX_4_profhp, TX_6_profhp_dm, TX_7_profhp_un)
     by copying CSVs from 5c_csv_conversion into the structure Phase 7 expects.
  2. Generates a minimal mixes_lhs.json in 0_experimental_design/ for fire testing.
  3. Checks for data_ev/ and warns if missing (cannot auto-generate).
  4. Writes a summary of what was done.

Safe to run multiple times — uses overwrite protection with confirmation.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
STATE = os.environ.get("PIPELINE_STATE", "TX")
SEASON = os.environ.get("PIPELINE_SEASON", "summer")

CSV_SOURCE = REPO_ROOT / "5c_csv_conversion"
PHASE7_DIR = REPO_ROOT / "7_circuit_instantiation"
MIXES_DIR  = REPO_ROOT / "0_experimental_design"

# profhp directory mapping:
#   scenario suffix in 5c folder name  →  profhp root directory name
SCENARIO_MAP = {
    "":              f"{STATE}_4_profhp",       # baseline (no suffix)
    "_dm":           f"{STATE}_6_profhp_dm",    # demand management
    "_uncontrolled": f"{STATE}_7_profhp_un",    # uncontrolled
}

SEP = "=" * 60

def header(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ── STEP 1: BUILD PROFHP BRIDGE DIRECTORIES ────────────────────────
header("STEP 1: Build profhp bridge directories")

if not CSV_SOURCE.is_dir():
    print(f"  FATAL: 5c_csv_conversion not found at {CSV_SOURCE}")
    sys.exit(1)

# Discover all 5c subdirectories
all_5c_dirs = sorted([d for d in CSV_SOURCE.iterdir() if d.is_dir()])
print(f"  Found {len(all_5c_dirs)} folders in 5c_csv_conversion/")

# Parse 5c folder names to extract (circuit, season, scenario_suffix)
# Format: TX_circuit_N_season[_dm|_uncontrolled]
def parse_5c_folder(name):
    """
    Parse folder name like 'TX_circuit_1_summer_dm' into components.
    Returns (bucket_base, scenario_suffix) or (None, None) if no match.
    bucket_base = 'TX_circuit_1_summer' (used as profhp bucket name)
    scenario_suffix = '' | '_dm' | '_uncontrolled'
    """
    for suffix in sorted(SCENARIO_MAP.keys(), key=len, reverse=True):
        # Check longest suffixes first to avoid partial matches
        if suffix and name.endswith(suffix):
            bucket_base = name[:-len(suffix)]
            return bucket_base, suffix
    # No suffix match → baseline
    return name, ""

# Build copy plan
copy_plan = []  # list of (src_dir, dst_dir, bucket_name, scenario, n_files)

for src_dir in all_5c_dirs:
    bucket_base, scenario_suffix = parse_5c_folder(src_dir.name)

    if scenario_suffix not in SCENARIO_MAP:
        print(f"  SKIP: {src_dir.name} (unrecognized scenario suffix)")
        continue

    profhp_root = REPO_ROOT / SCENARIO_MAP[scenario_suffix]
    dst_dir = profhp_root / "daily_csvs" / bucket_base

    csv_files = [f for f in src_dir.iterdir() if f.is_file() and f.suffix.lower() == ".csv"]

    copy_plan.append({
        "src": src_dir,
        "dst": dst_dir,
        "profhp_root": profhp_root.name,
        "bucket": bucket_base,
        "scenario": scenario_suffix or "(baseline)",
        "n_files": len(csv_files),
    })

# Show plan
print(f"\n  Copy plan ({len(copy_plan)} operations):")
print(f"  {'Source folder':<45} → {'Profhp root':<22} / {'Bucket':<25} Files")
print(f"  {'-'*45}   {'-'*22}   {'-'*25} {'-'*5}")
for entry in copy_plan:
    print(f"  {entry['src'].name:<45} → {entry['profhp_root']:<22} / {entry['bucket']:<25} {entry['n_files']}")

total_files = sum(e["n_files"] for e in copy_plan)
print(f"\n  Total files to copy: {total_files:,}")

# Check for existing directories
existing = [e for e in copy_plan if e["dst"].exists()]
if existing:
    print(f"\n  WARNING: {len(existing)} destination(s) already exist:")
    for e in existing:
        n_existing = sum(1 for f in e["dst"].iterdir() if f.is_file())
        print(f"    {e['dst']} ({n_existing} files)")
    resp = input("\n  Overwrite existing? [y/N]: ").strip().lower()
    if resp != "y":
        print("  Skipping profhp bridge creation.")
        copy_plan = []

# Execute copies
copied_total = 0
for entry in copy_plan:
    dst = entry["dst"]
    src = entry["src"]

    # Create destination directory tree
    dst.mkdir(parents=True, exist_ok=True)

    # Copy all CSV files
    n_copied = 0
    for csv_file in sorted(src.iterdir()):
        if csv_file.is_file() and csv_file.suffix.lower() == ".csv":
            shutil.copy2(csv_file, dst / csv_file.name)
            n_copied += 1

    copied_total += n_copied
    print(f"  ✓ {src.name} → {entry['profhp_root']}/daily_csvs/{entry['bucket']}/  ({n_copied} files)")

if copy_plan:
    print(f"\n  ✅ Copied {copied_total:,} CSV files into profhp bridge directories")

# Verify
header("STEP 1 VERIFY: profhp directory structure")
for suffix, profhp_name in SCENARIO_MAP.items():
    profhp_dir = REPO_ROOT / profhp_name
    daily = profhp_dir / "daily_csvs"
    if daily.is_dir():
        buckets = sorted([d for d in daily.iterdir() if d.is_dir()])
        print(f"  {profhp_name}/daily_csvs/ → {len(buckets)} bucket(s)")
        for b in buckets:
            n_kw = sum(1 for f in b.iterdir() if "_kw_" in f.name.lower())
            n_kvar = sum(1 for f in b.iterdir() if "_kvar_" in f.name.lower())
            print(f"    {b.name}: kw={n_kw}, kvar={n_kvar}")
    else:
        print(f"  {profhp_name}/daily_csvs/ → NOT FOUND")

# ── STEP 2: GENERATE MINIMAL MIXES FILE ────────────────────────────
header("STEP 2: Generate fire test mixes_lhs.json")

MIXES_PATH = MIXES_DIR / "mixes_lhs.json"

# Fire test mixes: 3 scenarios to test different heating share combinations
# and DER penetration levels. Minimal but covers key code paths.
fire_test_mixes = {
    "fire_baseline": {
        "shares": {"baseline": 1.0, "dm": 0.0, "un": 0.0},
        "heating_seed": 555,
        "ev_perc": 0.10,
        "ev_lvl2_perc": 0.80,
        "ev_seed": 555,
        "storage_perc_3ph": 0.05,
        "storage_seed": 555,
        "pv_perc_3ph": 0.05,
        "pv_seed": 555,
        "disjoint_sets": True,
        "ev_split": {"controlled": 0.50, "uncontrolled": 0.50}
    },
    "fire_mixed": {
        "shares": {"baseline": 0.50, "dm": 0.30, "un": 0.20},
        "heating_seed": 556,
        "ev_perc": 0.20,
        "ev_lvl2_perc": 0.80,
        "ev_seed": 556,
        "storage_perc_3ph": 0.10,
        "storage_seed": 556,
        "pv_perc_3ph": 0.10,
        "pv_seed": 556,
        "disjoint_sets": True,
        "ev_split": {"controlled": 0.60, "uncontrolled": 0.40}
    },
    "fire_stress": {
        "shares": {"baseline": 0.20, "dm": 0.20, "un": 0.60},
        "heating_seed": 557,
        "ev_perc": 0.30,
        "ev_lvl2_perc": 0.90,
        "ev_seed": 557,
        "storage_perc_3ph": 0.15,
        "storage_seed": 557,
        "pv_perc_3ph": 0.15,
        "pv_seed": 557,
        "disjoint_sets": False,
        "ev_split": {"controlled": 0.40, "uncontrolled": 0.60}
    },
}

if MIXES_PATH.exists():
    print(f"  WARNING: {MIXES_PATH} already exists!")
    resp = input("  Overwrite? [y/N]: ").strip().lower()
    if resp != "y":
        print("  Skipping mixes generation.")
    else:
        MIXES_DIR.mkdir(parents=True, exist_ok=True)
        with MIXES_PATH.open("w", encoding="utf-8") as f:
            json.dump(fire_test_mixes, f, indent=2)
        print(f"  ✅ Wrote {MIXES_PATH}")
else:
    MIXES_DIR.mkdir(parents=True, exist_ok=True)
    with MIXES_PATH.open("w", encoding="utf-8") as f:
        json.dump(fire_test_mixes, f, indent=2)
    print(f"  ✅ Wrote {MIXES_PATH}")

print(f"  Mixes defined: {list(fire_test_mixes.keys())}")
print(f"  → {len(fire_test_mixes)} mixes × 2 feeders = {len(fire_test_mixes) * 2} circuit folders expected")

# Show what the instantiation will produce
print(f"\n  Expected circuit folders after instantiation:")
try:
    reg_path = REPO_ROOT / "feeder_registry.json"
    with reg_path.open("r") as f:
        reg = json.load(f)
    for entry in reg["feeders"]:
        sub = entry["substation"]
        cid = entry["circuit_id"]
        for mix_name in fire_test_mixes:
            folder = f"{sub}_circuit_{cid}_{mix_name}"
            print(f"    {folder}/")
except Exception:
    print("    (could not read feeder_registry.json for preview)")

# ── STEP 3: CHECK data_ev ──────────────────────────────────────────
header("STEP 3: Check data_ev (EV base profiles)")

data_ev_target = PHASE7_DIR / "data_ev"
if data_ev_target.is_dir():
    n_items = sum(1 for _ in data_ev_target.rglob("*") if _.is_file())
    print(f"  ✅ data_ev/ exists at {data_ev_target} ({n_items} files)")
else:
    print(f"  ❌ data_ev/ NOT FOUND at {data_ev_target}")
    print()
    print("  This directory contains state-independent NREL EV charging profiles.")
    print("  You need to copy it from Machine 1 or Machine 2 (from NC runs).")
    print()
    print("  EXPECTED STRUCTURE:")
    print("    7_circuit_instantiation/data_ev/")
    print("      without_daily_plug_in_factor/")
    print("        *.csv  (EV charging profile CSVs)")
    print("      with_daily_plug_in_factor_70/")
    print("        *.csv  (EV charging profile CSVs)")
    print()
    print("  WORKAROUND (if you can't locate them right now):")
    print("    Edit power_flow_sim_daily_EV_STO_DG_deploy.py line 41:")
    print("    Change: ACTIVATE_EV = True")
    print("    To:     ACTIVATE_EV = False")
    print("    This skips EV generation. Everything else runs normally.")
    print("    You can re-enable once you bring the files over.")
    print()

    # Also search globally for data_ev
    print("  Searching for data_ev anywhere under D:\\github\\...")
    found_any = False
    search_root = Path(r"D:\github")
    if search_root.is_dir():
        for d in search_root.rglob("data_ev"):
            if d.is_dir() and (d / "without_daily_plug_in_factor").is_dir():
                n_items = sum(1 for _ in d.rglob("*") if _.is_file())
                print(f"  FOUND: {d} ({n_items} files)")
                found_any = True
    if not found_any:
        print("  Not found under D:\\github\\")

    # Search Dropbox too
    for dropbox_root in [Path(r"C:\Users\lfv1\Dropbox"), Path(r"D:\Dropbox")]:
        if dropbox_root.is_dir():
            print(f"  Searching {dropbox_root} (top-level only)...")
            for d in dropbox_root.iterdir():
                if d.is_dir() and d.name == "data_ev":
                    print(f"  FOUND: {d}")
                    found_any = True

# ── STEP 4: PRE-FLIGHT SUMMARY ─────────────────────────────────────
header("STEP 4: Pre-flight summary")

checks = {
    "profhp bridge (TX_4_profhp)":   (REPO_ROOT / f"{STATE}_4_profhp" / "daily_csvs").is_dir(),
    "profhp bridge (TX_6_profhp_dm)": (REPO_ROOT / f"{STATE}_6_profhp_dm" / "daily_csvs").is_dir(),
    "profhp bridge (TX_7_profhp_un)": (REPO_ROOT / f"{STATE}_7_profhp_un" / "daily_csvs").is_dir(),
    "mixes_lhs.json":                 MIXES_PATH.is_file(),
    "feeder_registry.json":           (REPO_ROOT / "feeder_registry.json").is_file(),
    "pipeline_config.yaml":           (REPO_ROOT / "pipeline_config.yaml").is_file(),
    "data_ev/":                        data_ev_target.is_dir(),
    "SMART-DS root":                   Path(os.environ.get("PIPELINE_SMART_DS_ROOT", "")).is_dir(),
    "OpenDSS COM":                     True,  # already verified
}

all_ok = True
for label, ok in checks.items():
    status = "✅" if ok else "❌"
    if not ok:
        all_ok = False
    print(f"  {status} {label}")

if all_ok:
    print(f"\n  🎉 ALL CHECKS PASS — ready to run Phase 7!")
    print(f"\n  Next commands:")
    print(f"    cd /d {PHASE7_DIR}")
    print(f"    set PIPELINE_STATE={STATE}")
    print(f"    set PIPELINE_SEASON={SEASON}")
    print(f"    set PIPELINE_SMART_DS_ROOT=D:\\lvg\\GSO\\rural\\base_timeseries\\opendss")
    print(f"    set PIPELINE_MAX_FEEDERS=2")
    print(f"    python instantiate_circuits_and_runs_APPLYFILTER.py")
else:
    print(f"\n  ⚠️  Some checks failed — resolve before running Phase 7")
    if not data_ev_target.is_dir():
        print(f"    → data_ev: copy from another machine OR set ACTIVATE_EV=False")

print(f"\n{SEP}")
print(f"  Preparation complete: {datetime.now().isoformat()}")
print(SEP)
