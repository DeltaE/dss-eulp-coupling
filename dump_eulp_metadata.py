#%%
"""
dump_eulp_metadata.py
---------------------
Round 2. Two jobs, both read-only:

  1. COLUMN DIFF: show exactly which columns the build dropped, by comparing the
     67-col historical residential file against the 62-col pipeline_state output.
  2. SOURCE DUMP: print the eulp_metadata package (build.py + siblings + any
     config files) so we can find WHERE the residential keep-list is defined.

Drop in repo root:  D:\github\dss-eulp-coupling\
Run:                python dump_eulp_metadata.py

Nothing is modified.
"""

from pathlib import Path
import sys

try:
    import pandas as pd
except ImportError:
    print("pandas not found. Run: pip install pandas")
    sys.exit(1)


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

# %% ------------------------------------------------------- 1. COLUMN DIFF
section("COLUMN DIFF — what build dropped (67-col historical vs 62-col output)")

ref_path = ROOT / "1_data_provenance" / "data_derived" / "historical" / "residential_data_SELECT_STATES.csv"
out_path = ROOT / "1_data_provenance" / "outputs" / "pipeline_state" / "residential_data_SELECT_STATES.csv"


def cols_of(p):
    return pd.read_csv(p, nrows=1).columns.tolist() if p.exists() else None


ref_cols = cols_of(ref_path)
out_cols = cols_of(out_path)

if ref_cols is None:
    print(f"  REF not found: {ref_path}")
if out_cols is None:
    print(f"  OUT not found: {out_path}")

if ref_cols and out_cols:
    dropped = [c for c in ref_cols if c not in out_cols]
    added = [c for c in out_cols if c not in ref_cols]
    print(f"  REF (historical): {len(ref_cols)} cols  ->  {ref_path}")
    print(f"  OUT (TX build):   {len(out_cols)} cols  ->  {out_path}")
    print(f"\n  DROPPED in build output ({len(dropped)}):")
    for c in dropped:
        flag = "   <-- NEEDED BY PHASE 4" if c in (
            "in.geometry_building_type_acs", "in.vacancy_status") else ""
        print(f"      - {c}{flag}")
    if added:
        print(f"\n  ADDED in build output ({len(added)}):")
        for c in added:
            print(f"      + {c}")

# %% ------------------------------------------------- 2. SOURCE DUMP
section("SOURCE DUMP — eulp_metadata package")

# Locate the package by finding build.py under a path that mentions eulp_metadata.
build_candidates = [p for p in ROOT.rglob("build.py") if "eulp_metadata" in str(p)]
if not build_candidates:
    print("  Could not locate eulp_metadata\\build.py — listing any build.py found:")
    for p in ROOT.rglob("build.py"):
        print(f"    {p}")
else:
    pkg_dir = build_candidates[0].parent
    print(f"  Package dir: {pkg_dir}\n")

    # Tree of the package dir
    print("  -- package tree --")
    for p in sorted(pkg_dir.rglob("*")):
        if p.is_file():
            print(f"    {p.relative_to(pkg_dir)}  ({p.stat().st_size} bytes)")

    # Dump source/config files in the package
    exts = {".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".txt"}
    for p in sorted(pkg_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            section(f"FILE: {p.relative_to(ROOT)}")
            try:
                print(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception as e:
                print(f"  [could not read: {e}]")

    # Also check 1_data_provenance root for a config that build.py might load
    section("CONFIG FILES at 1_data_provenance root (build.py may load these)")
    cfg_dir = ROOT / "1_data_provenance"
    for p in sorted(cfg_dir.glob("*")):
        if p.is_file() and p.suffix.lower() in {".yaml", ".yml", ".json", ".toml", ".cfg", ".ini"}:
            section(f"FILE: {p.relative_to(ROOT)}")
            try:
                print(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception as e:
                print(f"  [could not read: {e}]")

# %% ------------------------------------------------- 3. confirm Phase 4 script name
section("PHASE 4 SCRIPTS — does the non-NC name exist?")
for name in ["select_rep_family.py", "select_rep_family_NC.py",
             "clean_up_bldgs.py", "clean_up_bldgs_NC.py"]:
    found = list(ROOT.rglob(name))
    print(f"  {name:<28} {'FOUND: ' + str(found[0].relative_to(ROOT)) if found else 'NOT FOUND'}")

print("\nPaste the whole output back.")
