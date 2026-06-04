# -*- coding: utf-8 -*-
"""
verify_phase7_readiness.py
--------------------------
Run from Anaconda Prompt on Machine 3:
    cd /d D:\github\dss-eulp-coupling
    python verify_phase7_readiness.py

Produces a single consolidated report of everything Claude needs
to know before writing the Phase 7/8 bridge script.

Paste the ENTIRE console output back into the chat.
"""

import os
import sys
import json
import glob
from pathlib import Path
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent
STATE = os.environ.get("PIPELINE_STATE", "TX")
SEASON = os.environ.get("PIPELINE_SEASON", "summer")

SEP = "=" * 72
SUBSEP = "-" * 60

def header(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def subheader(title):
    print(f"\n{SUBSEP}\n  {title}\n{SUBSEP}")

def check_path(label, path, show_contents=False, max_items=30, pattern=None):
    """Check if a path exists, optionally list contents."""
    p = Path(path)
    if p.is_file():
        size = p.stat().st_size
        print(f"  [EXISTS] {label}: {p}  ({size:,} bytes)")
        return True
    elif p.is_dir():
        try:
            items = sorted(p.iterdir())
            if pattern:
                items = [i for i in items if i.match(pattern)]
            print(f"  [EXISTS] {label}: {p}  ({len(items)} items)")
            if show_contents:
                for item in items[:max_items]:
                    tag = "DIR " if item.is_dir() else "FILE"
                    sz = ""
                    if item.is_file():
                        sz = f"  ({item.stat().st_size:,} B)"
                    print(f"           {tag}  {item.name}{sz}")
                if len(items) > max_items:
                    print(f"           ... and {len(items) - max_items} more")
        except PermissionError:
            print(f"  [EXISTS] {label}: {p}  (permission denied listing)")
        return True
    else:
        print(f"  [MISSING] {label}: {p}")
        return False

def count_csvs_in_dir(dirpath):
    """Count CSV files in a directory (non-recursive)."""
    d = Path(dirpath)
    if not d.is_dir():
        return 0
    return sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".csv")

def file_head(path, n=10):
    """Print first n lines of a text file."""
    p = Path(path)
    if not p.is_file():
        print(f"  (file not found: {p})")
        return
    try:
        with p.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= n:
                    print(f"  ... ({p.stat().st_size:,} bytes total)")
                    break
                print(f"  | {line.rstrip()}")
    except Exception as e:
        print(f"  (error reading: {e})")

# ── START REPORT ────────────────────────────────────────────────────
print(SEP)
print(f"  PHASE 7/8 FIRE TEST READINESS REPORT")
print(f"  Generated: {datetime.now().isoformat()}")
print(f"  Machine:   {os.environ.get('COMPUTERNAME', 'unknown')}")
print(f"  Repo root: {REPO_ROOT}")
print(f"  STATE={STATE}  SEASON={SEASON}")
print(SEP)

# ── 1. PHASE 7 SCRIPT LOCATION ─────────────────────────────────────
header("1. PHASE 7 SCRIPT LOCATION")

# Search for the main instantiation script
found_instantiate = list(REPO_ROOT.rglob("instantiate_circuits_and_runs_APPLYFILTER.py"))
if found_instantiate:
    for f in found_instantiate:
        print(f"  FOUND: {f}")
        print(f"         Parent dir: {f.parent.name}")
else:
    print("  NOT FOUND anywhere under repo root")

# Check expected directory names
for dirname in ["7_circuit_instantiation", "8_instantiate_circuits_FILTER", "7_opendss_deploy"]:
    d = REPO_ROOT / dirname
    if d.is_dir():
        print(f"  Directory exists: {dirname}/")
        items = sorted(d.iterdir())
        py_files = [i for i in items if i.suffix == ".py"]
        dirs = [i for i in items if i.is_dir()]
        print(f"    .py files: {len(py_files)}")
        for pf in py_files[:15]:
            print(f"      {pf.name}")
        print(f"    subdirs: {len(dirs)}")
        for sd in dirs[:10]:
            print(f"      {sd.name}/")

# ── 2. MIXES FILE ──────────────────────────────────────────────────
header("2. EXPERIMENTAL DESIGN / MIXES FILE")

exp_dir = REPO_ROOT / "0_experimental_design"
check_path("0_experimental_design", exp_dir, show_contents=True)

for mixes_name in ["mixes_lhs.json", "mixes_sobol.json"]:
    mpath = exp_dir / mixes_name
    if mpath.is_file():
        print(f"\n  Contents preview of {mixes_name}:")
        try:
            with mpath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"    Type: {type(data).__name__}")
            if isinstance(data, dict):
                keys = list(data.keys())
                print(f"    Top-level keys ({len(keys)}): {keys[:5]}{'...' if len(keys) > 5 else ''}")
                # Show first mix entry
                first_key = keys[0]
                first_val = data[first_key]
                print(f"    Sample entry [{first_key}]:")
                if isinstance(first_val, dict):
                    for k, v in list(first_val.items())[:10]:
                        print(f"      {k}: {v}")
            elif isinstance(data, list):
                print(f"    Length: {len(data)}")
                if data:
                    print(f"    First entry: {json.dumps(data[0], indent=4)[:300]}")
        except Exception as e:
            print(f"    (parse error: {e})")

# ── 3. FEEDER REGISTRY ─────────────────────────────────────────────
header("3. FEEDER REGISTRY")

reg_path = REPO_ROOT / "feeder_registry.json"
if check_path("feeder_registry.json", reg_path):
    try:
        with reg_path.open("r", encoding="utf-8") as f:
            reg = json.load(f)
        print(f"  Top-level keys: {list(reg.keys())}")
        if "feeders" in reg:
            feeders = reg["feeders"]
            print(f"  Number of feeders: {len(feeders)}")
            if feeders:
                print(f"  First feeder entry:")
                for k, v in feeders[0].items():
                    print(f"    {k}: {v}")
        if "circuit_name_map" in reg:
            cnm = reg["circuit_name_map"]
            print(f"  circuit_name_map entries: {len(cnm)}")
            for k, v in list(cnm.items())[:5]:
                print(f"    {k} -> {v}")
    except Exception as e:
        print(f"  (parse error: {e})")

# ── 4. PIPELINE CONFIG ─────────────────────────────────────────────
header("4. PIPELINE CONFIG (pipeline_config.yaml)")

cfg_path = REPO_ROOT / "pipeline_config.yaml"
if check_path("pipeline_config.yaml", cfg_path):
    print("  Full contents:")
    file_head(cfg_path, n=30)

# ── 5. data_ev DIRECTORY ───────────────────────────────────────────
header("5. EV BASE DATA (data_ev)")

# Search in multiple possible locations
for loc_name, loc in [
    ("7_circuit_instantiation/data_ev", REPO_ROOT / "7_circuit_instantiation" / "data_ev"),
    ("8_instantiate_circuits_FILTER/data_ev", REPO_ROOT / "8_instantiate_circuits_FILTER" / "data_ev"),
    ("repo root/data_ev", REPO_ROOT / "data_ev"),
]:
    check_path(loc_name, loc, show_contents=True)

# ── 6. deployer_modules ────────────────────────────────────────────
header("6. DEPLOYER MODULES")

for loc_name, loc in [
    ("deployer_modules (repo root)", REPO_ROOT / "deployer_modules"),
    ("7_circuit_instantiation/../deployer_modules", REPO_ROOT / "deployer_modules"),
]:
    check_path(loc_name, loc, show_contents=True, pattern="*.py")

# ── 7. PROFHP DIRECTORIES ──────────────────────────────────────────
header("7. PROFHP DIRECTORIES (heating pathway CSV trees)")

for prefix in ["NC", "TX"]:
    subheader(f"{prefix} profhp directories")
    for suffix, label in [
        ("_4_profhp", "baseline"),
        ("_6_profhp_dm", "demand mgmt"),
        ("_7_profhp_un", "uncontrolled"),
    ]:
        dirname = f"{prefix}{suffix}"
        dirpath = REPO_ROOT / dirname
        if check_path(f"{dirname} ({label})", dirpath):
            daily = dirpath / "daily_csvs"
            if daily.is_dir():
                buckets = sorted([d for d in daily.iterdir() if d.is_dir()])
                print(f"    daily_csvs/ has {len(buckets)} bucket(s):")
                for b in buckets[:10]:
                    n_csv = count_csvs_in_dir(b)
                    print(f"      {b.name}/  ({n_csv} CSVs)")
                if len(buckets) > 10:
                    print(f"      ... and {len(buckets) - 10} more")
            else:
                print(f"    daily_csvs/ NOT FOUND inside {dirname}")

# ── 8. 5c CSV CONVERSION OUTPUT ────────────────────────────────────
header("8. PHASE 5c CSV CONVERSION OUTPUT")

csv_dir = REPO_ROOT / "5c_csv_conversion"
if check_path("5c_csv_conversion", csv_dir):
    subdirs = sorted([d for d in csv_dir.iterdir() if d.is_dir()])
    print(f"\n  Subdirectories ({len(subdirs)}):")
    for sd in subdirs:
        n_kw = sum(1 for f in sd.iterdir() if f.is_file() and "_kw_" in f.name.lower())
        n_kvar = sum(1 for f in sd.iterdir() if f.is_file() and "_kvar_" in f.name.lower())
        n_total = count_csvs_in_dir(sd)
        print(f"    {sd.name}:  kw={n_kw}, kvar={n_kvar}, total_csv={n_total}")

# ── 9. SMART-DS ROOT ───────────────────────────────────────────────
header("9. SMART-DS ROOT")

smartds_candidates = [
    Path(r"D:\lvg\GSO\rural\base_timeseries\opendss"),
    REPO_ROOT / "3_smartds",
]
for sd in smartds_candidates:
    if check_path("SMART-DS candidate", sd):
        # Count substations
        subs = [d for d in sd.iterdir() if d.is_dir()]
        print(f"    Substations: {len(subs)}")
        for s in subs[:5]:
            feeders = [f for f in s.iterdir() if f.is_dir()]
            print(f"      {s.name}/ → {len(feeders)} feeder(s)")
            for fe in feeders[:3]:
                dss = [x for x in fe.iterdir() if x.suffix.lower() == ".dss"]
                print(f"        {fe.name}/ → {len(dss)} .dss files")

# ── 10. OPENDSS COM ────────────────────────────────────────────────
header("10. OPENDSS COM INTERFACE")

try:
    import comtypes.client
    dss = comtypes.client.CreateObject("OpenDSSEngine.DSS")
    print(f"  [OK] OpenDSS version: {dss.Version}")
except ImportError:
    print("  [MISSING] comtypes package not installed")
except Exception as e:
    print(f"  [FAIL] {e}")

# ── 11. PYTHON ENVIRONMENT ─────────────────────────────────────────
header("11. PYTHON ENVIRONMENT")

print(f"  Python: {sys.version}")
print(f"  Executable: {sys.executable}")
print(f"  CWD: {os.getcwd()}")

key_packages = ["yaml", "pandas", "numpy", "comtypes", "matplotlib"]
for pkg in key_packages:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, "__version__", "installed (no version attr)")
        print(f"  {pkg}: {ver}")
    except ImportError:
        print(f"  {pkg}: NOT INSTALLED")

# ── 12. ENV VARS ───────────────────────────────────────────────────
header("12. PIPELINE ENV VARS (current session)")

for var in [
    "PIPELINE_STATE", "PIPELINE_SEASON", "PIPELINE_SMART_DS_ROOT",
    "PIPELINE_SMART_DS_PARQUET_ROOT", "PIPELINE_PARQUET_ROOT",
    "PIPELINE_MAX_FEEDERS", "PIPELINE_FEEDER_REGISTRY_PATH",
]:
    val = os.environ.get(var, "(not set)")
    print(f"  {var} = {val}")

# ── 13. PHASE 8 SCRIPTS ────────────────────────────────────────────
header("13. PHASE 8 ANALYSIS SCRIPTS")

for dirname in ["8_results_analysis", "9_results_analysis"]:
    d = REPO_ROOT / dirname
    check_path(dirname, d, show_contents=True)

# ── 14. ADDITIONAL SEARCH: any *profhp* or *daily_csvs* anywhere ──
header("14. GLOBAL SEARCH: profhp / daily_csvs directories")

print("  Searching for *profhp* directories (may take a moment)...")
for d in REPO_ROOT.iterdir():
    if d.is_dir() and "profhp" in d.name.lower():
        daily = d / "daily_csvs"
        has_daily = daily.is_dir()
        n_buckets = len(list(daily.iterdir())) if has_daily else 0
        print(f"  {d.name}/  daily_csvs={'YES' if has_daily else 'NO'}  buckets={n_buckets}")

# ── DONE ────────────────────────────────────────────────────────────
header("REPORT COMPLETE")
print(f"  Paste everything above back into the Claude chat.")
print(f"  Total checks: 14 sections")
print(SEP)
