#%%
"""
dump_workflow_and_sources.py
----------------------------
Round 3. Read-only. Three jobs:

  1. Dump config/workflow.yaml (the real keep-list + cluster + paths config).
  2. Show columns of the historical INPUT residential_data.csv (the 62-col culprit
     that historical_slice copies wholesale) + presence of the 5 dropped columns.
  3. Probe data_raw residential metadata CSVs to confirm the 5 columns still exist
     at source -> so the keep-list edit can actually pull them back.

Also flags which workflow cluster writes residential_data.csv (what to rebuild).

Drop in repo root:  D:\github\dss-eulp-coupling\
Run:                python dump_workflow_and_sources.py
"""

from pathlib import Path
import sys

try:
    import pandas as pd
except ImportError:
    print("pandas not found. Run: pip install pandas")
    sys.exit(1)

TARGET_COLS = [
    "in.representative_income", "in.battery", "in.bedrooms",
    "in.geometry_building_type_acs", "in.vacancy_status",
]
CRITICAL = {"in.geometry_building_type_acs", "in.vacancy_status"}


def find_repo_root() -> Path:
    markers = {"pipeline_config.yaml", "feeder_registry.json", ".git"}
    here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    for d in [here, *here.parents]:
        if any((d / m).exists() for m in markers):
            return d
    return Path.cwd()


def section(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


ROOT = find_repo_root()
print(f"Repo root: {ROOT}")

# %% --------------------------------------------------- 1. workflow.yaml
section("workflow.yaml")
wf_candidates = list(ROOT.rglob("workflow.yaml"))
if not wf_candidates:
    print("  workflow.yaml NOT FOUND under repo root.")
else:
    wf = wf_candidates[0]
    print(f"  Path: {wf}\n")
    text = wf.read_text(encoding="utf-8", errors="ignore")
    print(text)

    # Quick pointer: which lines mention residential_data.csv (producer cluster)
    section("workflow.yaml — lines mentioning 'residential_data.csv'")
    for i, line in enumerate(text.splitlines(), 1):
        if "residential_data.csv" in line:
            print(f"  {i}: {line.strip()}")

# %% --------------------------------------------- 2. residential_data.csv columns
section("HISTORICAL INPUT — residential_data.csv (what historical_slice copies)")
inputs = [p for p in ROOT.rglob("residential_data.csv")]
if not inputs:
    print("  residential_data.csv NOT FOUND.")
for p in inputs:
    try:
        cols = pd.read_csv(p, nrows=1).columns.tolist()
    except Exception as e:
        print(f"  [could not read] {p}  ({e})")
        continue
    print(f"\n  {p}")
    print(f"      columns: {len(cols)}")
    for c in TARGET_COLS:
        tag = "  (CRITICAL)" if c in CRITICAL else ""
        print(f"      {c:<35} {'PRESENT' if c in cols else 'MISSING'}{tag}")

# %% --------------------------------------------- 3. raw data probe
section("RAW DATA PROBE — do data_raw residential CSVs still have the columns?")
raw_dir = ROOT / "1_data_provenance" / "data_raw"
if not raw_dir.exists():
    print(f"  {raw_dir} not found.")
else:
    found_any = False
    scanned = 0
    for p in raw_dir.rglob("*.csv"):
        scanned += 1
        if scanned > 400:
            print("  (stopped after scanning 400 raw CSVs)")
            break
        try:
            cols = pd.read_csv(p, nrows=0).columns.tolist()
        except Exception:
            continue
        present = [c for c in TARGET_COLS if c in cols]
        if present:
            found_any = True
            rel = p.relative_to(ROOT)
            miss = [c for c in TARGET_COLS if c not in cols]
            print(f"  {rel}")
            print(f"      has: {present}")
            if miss:
                print(f"      missing: {miss}")
    if not found_any:
        print("  No raw CSV with any of the target columns found in first 400 scanned.")
        print("  (May mean raw residential metadata lives elsewhere, or under a")
        print("   different name — check folder_groups / data_raw path in workflow.yaml above.)")

print("\nPaste the whole output back.")
