# -*- coding: utf-8 -*-
"""
bridge_phase5c_to_phase7.py
---------------------------
Phase 7a. Bridges Phase 5c/6 output to Phase 7 instantiation.

run_case.py runs it with the PIPELINE_* variables set.

What this script does:
  1. Builds profhp bridge directories (<STATE>_4_profhp, <STATE>_6_profhp_dm, <STATE>_7_profhp_un)
     by copying CSVs from 5c_csv_conversion into the structure Phase 7 expects.
  2. Copies the mixes file named by PIPELINE_MIXES_FILE (mixes_file in configs/defaults.yaml)
     byte for byte to <workspace>/7_circuit_instantiation/. Exits 1 if that file is missing.
  3. Checks for data_ev/ and warns if missing (cannot auto-generate).
  4. Prints a pre-flight summary.

Safe to run multiple times: it overwrites the profhp copies and the workspace mixes copy.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_utils import load_config, resolve_config_path, resolve_work_path

# ── CONFIG ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']

CSV_SOURCE = Path(resolve_work_path("5c_csv_conversion"))
PHASE7_DIR = REPO_ROOT / "7_circuit_instantiation"
# Workspace registry: PIPELINE_FEEDER_REGISTRY_PATH (set by run_case.py)
REGISTRY_PATH = resolve_config_path(cfg["feeder_registry_path"])

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

    profhp_root = Path(resolve_work_path("7_circuit_instantiation", SCENARIO_MAP[scenario_suffix]))
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
    for e in existing:
        print(f"Overwriting {e['dst']}")

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
    profhp_dir = Path(resolve_work_path("7_circuit_instantiation", profhp_name))
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

# ── STEP 2: COPY THE MIXES FILE ─────────────────────────────────────
header("STEP 2: Copy the mixes file")

MIXES_PATH = Path(cfg["mixes_file"])
if not MIXES_PATH.is_file():
    print(f"  FATAL: mixes file not found: {MIXES_PATH}", file=sys.stderr)
    sys.exit(1)

with MIXES_PATH.open("r", encoding="utf-8") as f:
    mixes = json.load(f)

# 7b reads the mixes from the workspace; copy the file byte for byte
WORK_MIXES_PATH = Path(resolve_work_path("7_circuit_instantiation", "mixes_lhs.json"))
WORK_MIXES_PATH.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(MIXES_PATH, WORK_MIXES_PATH)
print(f"  ✅ Copied {MIXES_PATH} → {WORK_MIXES_PATH}")

print(f"  Mixes defined: {list(mixes.keys())}")

# Show what the instantiation will produce
print(f"\n  Expected circuit folders after instantiation:")
try:
    reg_path = REGISTRY_PATH
    with reg_path.open("r") as f:
        reg = json.load(f)
    for entry in reg["feeders"]:
        sub = entry["substation"]
        cid = entry["circuit_id"]
        for mix_name in mixes:
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

# ── STEP 4: PRE-FLIGHT SUMMARY ─────────────────────────────────────
header("STEP 4: Pre-flight summary")

checks = {
    f"profhp bridge ({SCENARIO_MAP['']})":              (Path(resolve_work_path("7_circuit_instantiation", SCENARIO_MAP[""])) / "daily_csvs").is_dir(),
    f"profhp bridge ({SCENARIO_MAP['_dm']})":           (Path(resolve_work_path("7_circuit_instantiation", SCENARIO_MAP["_dm"])) / "daily_csvs").is_dir(),
    f"profhp bridge ({SCENARIO_MAP['_uncontrolled']})": (Path(resolve_work_path("7_circuit_instantiation", SCENARIO_MAP["_uncontrolled"])) / "daily_csvs").is_dir(),
    "mixes file":                     MIXES_PATH.is_file(),
    "feeder_registry.json":           REGISTRY_PATH.is_file(),
    "pipeline_config.yaml":           (REPO_ROOT / "pipeline_config.yaml").is_file(),
    "data_ev/":                        data_ev_target.is_dir(),
    "SMART-DS root":                   Path(os.environ.get("PIPELINE_SMART_DS_ROOT", "")).is_dir(),
}

all_ok = True
for label, ok in checks.items():
    status = "✅" if ok else "❌"
    if not ok:
        all_ok = False
    print(f"  {status} {label}")

if all_ok:
    print(f"\n  🎉 ALL CHECKS PASS — ready to run Phase 7!")
else:
    print(f"\n  ⚠️  Some checks failed — resolve before running Phase 7")
    if not data_ev_target.is_dir():
        print(f"    → data_ev: copy from another machine OR set ACTIVATE_EV=False")

print(f"\n{SEP}")
print(f"  Preparation complete: {datetime.now().isoformat()}")
print(SEP)
