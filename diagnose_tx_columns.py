#%%
"""
diagnose_tx_columns.py
----------------------
Pins down WHERE the two residential descriptor columns drop out of the TX build,
and WHERE the keep-list lives in code, so we know exactly what to fix.

Drop in repo root:  D:\github\dss-eulp-coupling\
Run:                python diagnose_tx_columns.py
(or just run the cells in Spyder)

It answers three questions:
  1. Does the UPSTREAM file (residential_data_SELECT_STATES.csv) have the columns?
     -> tells us if the fix goes in eulp_metadata.build or in the FILTERED step.
  2. Do the FILTERED TX residential files have them? (confirms the handoff finding)
  3. Where in the .py source are these columns / the keep-list referenced?

Nothing is modified. Read-only.
"""

import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("pandas not found in this env. Run: pip install pandas")
    sys.exit(1)

# The two columns Phase 4 residential quota assignment needs.
TARGET_COLS = ["in.geometry_building_type_acs", "in.vacancy_status"]

# Source-code terms worth locating.
GREP_TERMS = [
    "geometry_building_type_acs",
    "vacancy_status",
    "SELECT_STATES",
    "comstock_building_type",   # the commercial equiv that DOES survive — useful contrast
    "keep",                     # likely keep-list variable / arg
    "usecols",                  # pandas column filter
    "columns_to_keep",
]


def find_repo_root() -> Path:
    """Walk up from this file looking for a repo marker; fall back to cwd."""
    markers = {"pipeline_config.yaml", "feeder_registry.json", ".git"}
    here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    for d in [here, *here.parents]:
        if any((d / m).exists() for m in markers):
            return d
    return Path.cwd()


def report_csv(path: Path):
    """Print column count + presence of each TARGET_COL for one CSV."""
    try:
        cols = pd.read_csv(path, nrows=1).columns.tolist()
    except Exception as e:
        print(f"  [could not read] {path}  ({e})")
        return
    print(f"  {path}")
    print(f"      columns: {len(cols)}")
    for c in TARGET_COLS:
        print(f"      {c:<35} {'PRESENT' if c in cols else 'MISSING'}")


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# %% ---------------------------------------------------------------- locate repo
ROOT = find_repo_root()
print(f"Repo root resolved to: {ROOT}")

# %% ------------------------------------------------- Q1/Q2: column presence in CSVs
section("RESIDENTIAL CSVs — column presence")

res_csvs = sorted(ROOT.rglob("residential_data_SELECT_STATES*.csv"))
if not res_csvs:
    print("  No residential_data_SELECT_STATES*.csv found anywhere under repo root.")
    print("  (Did Phase 1 write to outputs\\pipeline_state\\ ? Check the path.)")
else:
    # Upstream file first (the one eulp_metadata.build + --validate look at),
    # then the FILTERED scenario files.
    upstream = [p for p in res_csvs if "FILTERED" not in p.name]
    filtered = [p for p in res_csvs if "FILTERED" in p.name]

    print("\n-- UPSTREAM (eulp_metadata.build output) --")
    for p in upstream:
        report_csv(p)

    print("\n-- FILTERED (downstream scenario files) --")
    if filtered:
        for p in filtered:
            report_csv(p)
    else:
        print("  none found yet (not generated, or different naming)")

# Commercial, for contrast — should have comstock_building_type and be fine.
section("COMMERCIAL CSVs — for contrast (expected fine)")
com_csvs = sorted(ROOT.rglob("commercial_data_SELECT_STATES*.csv"))
if not com_csvs:
    print("  none found")
for p in com_csvs:
    try:
        cols = pd.read_csv(p, nrows=1).columns.tolist()
        has = "in.comstock_building_type" in cols
        print(f"  {p}  ({len(cols)} cols)  comstock_building_type: "
              f"{'PRESENT' if has else 'MISSING'}")
    except Exception as e:
        print(f"  [could not read] {p}  ({e})")

# %% ------------------------------------ NC comparison (if any NC file is around)
section("NC COMPARISON (if an NC residential file exists on disk)")
nc_csvs = [p for p in ROOT.rglob("*residential*SELECT_STATES*.csv")
           if "NC" in p.name.upper()]
if not nc_csvs:
    print("  No NC residential SELECT_STATES file found by name.")
    print("  (Config is on TX. If NC files were overwritten/cleared, rely on the")
    print("   source grep below to see whether the keep-list is NC-hardcoded.)")
for p in nc_csvs:
    report_csv(p)

# %% --------------------------------------------- Q3: where in source code
section("SOURCE GREP — where columns / keep-list are referenced (.py only)")

py_files = [p for p in ROOT.rglob("*.py")
            if ".git" not in p.parts and p.name != Path(__file__).name
            if "__file__" in globals()]
if "__file__" not in globals():
    py_files = [p for p in ROOT.rglob("*.py") if ".git" not in p.parts]

hits = {term: [] for term in GREP_TERMS}
for f in py_files:
    try:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for term in GREP_TERMS:
                if term in line:
                    hits[term].append((f.relative_to(ROOT), i, line.strip()))
    except Exception:
        continue

for term in GREP_TERMS:
    print(f"\n--- '{term}' ---")
    if not hits[term]:
        print("    (no matches)")
    for relpath, lineno, text in hits[term][:40]:  # cap noise
        snippet = text if len(text) <= 120 else text[:117] + "..."
        print(f"    {relpath}:{lineno}: {snippet}")
    if len(hits[term]) > 40:
        print(f"    ... (+{len(hits[term]) - 40} more)")

# %% ------------------------------------------------------------------- verdict
section("READ THIS")
print("""
- If the UPSTREAM residential file shows both columns MISSING ->
    the fix goes in the eulp_metadata.build keep-list (columns never make it in).
- If UPSTREAM shows PRESENT but FILTERED shows MISSING ->
    the SELECT_STATES_FILTERED step is dropping them; fix there.
- The 'geometry_building_type_acs' / 'keep' / 'usecols' source hits above point
  at the exact keep-list to edit. Make it STATE-AGNOSTIC (not NC-only).

Paste this whole output back and I'll give you the exact edit.
""")
