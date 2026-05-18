#!/usr/bin/env python3
"""
Build the dss-eulp-coupling-staged/ repo from source scripts.
Run with: python build_staging.py
"""

import os
import shutil
import re

# ── PATHS ──────────────────────────────────────────────────────────────
DIST = r"C:\Users\luisfernando\Dropbox\1_RESEARCH\1_FOCUS_PhD\Conferences\Conference_EMH_2025_Ottawa\dist"
STAGING = r"C:\Users\luisfernando\GitHub\dss-eulp-coupling-staged"

# ── STEP 3a: Create staging folder structure ───────────────────────────
phase_dirs = [
    "src/phase2_extraction",
    "src/phase3_matching",
    "src/phase4_assignment",
    "src/phase5_profiles",
    "src/phase6_kvar",
    "src/phase7a_circuit_build",
    "src/utils",
]

for d in phase_dirs:
    os.makedirs(os.path.join(STAGING, d), exist_ok=True)
print("[OK] Created staging folder structure")

# ── STEP 3b: Copy IN scripts ──────────────────────────────────────────
# (source_relative_to_DIST, dest_relative_to_STAGING)
COPY_MAP = [
    # Phase 2 — extraction
    ("ab_3b/circuit_make_daily_list_sets.py",           "src/phase2_extraction/circuit_make_daily_list_sets.py"),
    ("ab_3b/review_parquet_matches.py",                 "src/phase2_extraction/review_parquet_matches.py"),

    # Phase 3 — matching
    ("ab_3b/match_smartds_parquets_MT.py",              "src/phase3_matching/match_smartds_parquets.py"),

    # Phase 4 — assignment
    ("ab_3b/clean_up_bldgs_MT.py",                      "src/phase4_assignment/clean_up_bldgs.py"),
    ("ab_3b/select_rep_family_MT.py",                   "src/phase4_assignment/select_rep_family.py"),
    ("ab_4_profhp/scale_feeder_curves_MT.py",           "src/phase4_assignment/scale_feeder_curves.py"),

    # Phase 5 — profiles
    ("ab_4_profhp/find_max_day_curve_MT.py",            "src/phase5_profiles/find_max_day_curve.py"),
    ("ab_6_profhp_dm/find_max_day_curve_MT_dm.py",      "src/phase5_profiles/find_max_day_curve_dm.py"),
    ("ab_7_profhp_un/find_max_day_curve_MT_uncontrolled.py", "src/phase5_profiles/find_max_day_curve_uncontrolled.py"),
    ("ab_4_profhp/daily_csvs/parquet_to_csv.py",        "src/phase5_profiles/parquet_to_csv.py"),
    ("ab_4_profhp/daily_csvs/save_needed_sd_parquets.py","src/phase5_profiles/save_needed_sd_parquets.py"),
    ("ab_4_profhp/get_scenario_csv_controls.py",        "src/phase5_profiles/get_scenario_csv_controls.py"),
    ("ab_4_profhp/plot_parquet_differences.py",         "src/phase5_profiles/plot_parquet_differences.py"),

    # Phase 6 — kVAr
    ("ab_5_kvar/rev_spec_kvar_kw_ratio.py",             "src/phase6_kvar/rev_spec_kvar_kw_ratio.py"),
    ("ab_4_profhp/daily_csvs/generate_kvar_csvs.py",    "src/phase6_kvar/generate_kvar_csvs.py"),

    # Phase 7a — circuit build
    ("ab_8_summer/instantiate_circuits_and_runs_APPLYFILTER.py", "src/phase7a_circuit_build/instantiate_circuits_and_runs.py"),
]

MAX_SIZE = 500 * 1024  # 500 KB
copied = []
skipped_size = []

for src_rel, dst_rel in COPY_MAP:
    src = os.path.join(DIST, src_rel)
    dst = os.path.join(STAGING, dst_rel)
    if not os.path.exists(src):
        print(f"[WARN] Source not found: {src}")
        continue
    fsize = os.path.getsize(src)
    if fsize > MAX_SIZE:
        skipped_size.append((src_rel, fsize))
        print(f"[SKIP] {src_rel} is {fsize/1024:.1f} KB (>500 KB)")
        continue
    shutil.copy2(src, dst)
    copied.append((dst_rel, fsize))
    print(f"[COPY] {src_rel} -> {dst_rel}  ({fsize/1024:.1f} KB)")

print(f"\n[OK] Copied {len(copied)} files")
if skipped_size:
    print(f"[WARN] Skipped {len(skipped_size)} files for size")

# ── STEP 4a: setup_workspace.py ──────────────────────────────────────
setup_workspace = r'''#!/usr/bin/env python3
"""
setup_workspace.py — Creates the folder structure a user needs
to run the SMART-DS x EULP coupling pipeline.
"""

import os

WORKSPACE = "workspace"

folders = {
    "smartds_feeders": (
        "Download Greensboro NC (or your target region) SMART-DS feeders from:\n"
        "  https://data.openei.org/search?q=SMART-DS\n"
        "Extract substation folders (e.g., uhs0_1247/) into this directory."
    ),
    "eulp_residential": (
        "Download ResStock end-use load profile data for your target state from:\n"
        "  https://data.openei.org/search?q=end-use-load-profiles\n"
        "Place the annual Parquet files (e.g., res_*.parquet) here."
    ),
    "eulp_commercial": (
        "Download ComStock end-use load profile data for your target state from:\n"
        "  https://data.openei.org/search?q=end-use-load-profiles\n"
        "Place the annual Parquet files (e.g., com_*.parquet) here."
    ),
    "eulp_metadata": (
        "Download metadata CSVs from OEDI for your target state:\n"
        "  - residential_data_SELECT_STATES.csv\n"
        "  - commercial_data_SELECT_STATES.csv\n"
        "These contain building descriptors (peak loads, income, etc.)."
    ),
    "output_matched": "Matching results will be stored here.",
    "output_profiles": "Daily peak-day profiles (CSV loadshapes) will be stored here.",
    "output_circuits": "Modified OpenDSS circuit folders will be stored here.",
}

print("=" * 60)
print("SMART-DS x EULP Coupling Pipeline  —  Workspace Setup")
print("=" * 60)

for folder, description in folders.items():
    path = os.path.join(WORKSPACE, folder)
    os.makedirs(path, exist_ok=True)
    print(f"\n[CREATED] {path}/")
    for line in description.strip().split("\n"):
        print(f"          {line}")

print("\n" + "=" * 60)
print("Workspace ready!  Next steps:")
print("  1. Download data into the folders above")
print("  2. Update config_example.yaml with your paths")
print("  3. Run phases 2 through 7a in order")
print("=" * 60)
'''

with open(os.path.join(STAGING, "setup_workspace.py"), "w", encoding="utf-8") as f:
    f.write(setup_workspace)
print("[OK] Wrote setup_workspace.py")

# ── STEP 4b: config_example.yaml ─────────────────────────────────────
config_yaml = r'''# config_example.yaml — SMART-DS x EULP Coupling Pipeline
# Copy to config.yaml and adjust for your environment.

# ── Paths (relative to workspace/) ──
paths:
  smartds_feeders: workspace/smartds_feeders
  eulp_residential: workspace/eulp_residential
  eulp_commercial: workspace/eulp_commercial
  eulp_metadata: workspace/eulp_metadata
  output_matched: workspace/output_matched
  output_profiles: workspace/output_profiles
  output_circuits: workspace/output_circuits

# ── Target state ──
# Use the two-letter US state abbreviation that most closely maps
# to your study region (SMART-DS feeders are from Greensboro, NC).
target_state: "MT"

# ── Tolerance-escalation parameters (Phase 3) ──
matching:
  tolerance_start: 0.05    # 5 %
  tolerance_stop: 0.50     # 50 %
  tolerance_step: 0.05     # 5 % increments
  # Residential matching also checks winter (Dec-Jan-Feb) and
  # summer (Jun-Jul-Aug) peak separately.

# ── Income-group scenario (Phase 4) ──
residential_scenario: "mid"   # Options: "high", "mid", "low"

# ── Season selection (Phase 5 / 7a) ──
seasons:
  - winter
  - summer

# ── Peak-day profile settings ──
profiles:
  npts: 96           # 15-min intervals per day
  interval_h: 0.25   # hours per interval

# ── Random seeds (Phase 4 — representative family selection) ──
random_seeds:
  python_random: 42
  numpy_random: 42

# ── Circuits to skip (Phase 7a — known problematic circuits) ──
skip_circuits: [12, 13, 36]
'''

with open(os.path.join(STAGING, "config_example.yaml"), "w", encoding="utf-8") as f:
    f.write(config_yaml)
print("[OK] Wrote config_example.yaml")

# ── STEP 4c: README.md ───────────────────────────────────────────────
readme = r'''# SMART-DS x EULP Coupling Pipeline

A reproducible pipeline for coupling [SMART-DS](https://data.openei.org/search?q=SMART-DS)
synthetic distribution feeders with [NREL End-Use Load Profiles (EULP)](https://www.nrel.gov/buildings/end-use-load-profiles.html)
building demand data, producing simulation-ready OpenDSS circuit models with
realistic, temporally-resolved residential and commercial load profiles.

## Pipeline Overview

| Phase | Name | Description |
|-------|------|-------------|
| 2 | **Extraction** | Parse OpenDSS `Loads.dss` files to identify load-shape names; compute monthly peak statistics from EULP Parquet data. |
| 3 | **Matching** | Tolerance-escalation algorithm (5 %–50 %) to match each SMART-DS load to EULP buildings with similar monthly peaks. |
| 4 | **Assignment** | Filter matched buildings by income group, assign representative building families to each feeder, and scale curves. |
| 5 | **Profiles** | Slice peak-day (winter/summer) 15-min load curves from annual Parquet files; export as CSV loadshapes. |
| 6 | **kVAr** | Extract real/reactive power ratios from the original EULP Parquets and generate companion kVAr CSV profiles. |
| 7a | **Circuit Build** | Copy SMART-DS feeder files, rewrite `LoadShapes.dss` and `Loads.dss` to inject the EULP-derived daily profiles. |

## Prerequisites

- Python >= 3.9
- Install dependencies: `pip install -r requirements.txt`

## Quickstart

```bash
# 1. Create the workspace and see download instructions
python setup_workspace.py

# 2. Download SMART-DS feeders and EULP data into workspace/

# 3. Run each phase in order
cd src/phase2_extraction
python circuit_make_daily_list_sets.py
python review_parquet_matches.py

cd ../phase3_matching
python match_smartds_parquets.py

cd ../phase4_assignment
python clean_up_bldgs.py
python select_rep_family.py
python scale_feeder_curves.py

cd ../phase5_profiles
python find_max_day_curve.py
python parquet_to_csv.py
python save_needed_sd_parquets.py

cd ../phase6_kvar
python rev_spec_kvar_kw_ratio.py
python generate_kvar_csvs.py

cd ../phase7a_circuit_build
python instantiate_circuits_and_runs.py
```

## Input Data

| Dataset | Source |
|---------|--------|
| SMART-DS synthetic feeders | [OEDI — SMART-DS](https://data.openei.org/search?q=SMART-DS) |
| EULP ResStock profiles | [OEDI — End-Use Load Profiles](https://data.openei.org/search?q=end-use-load-profiles) |
| EULP ComStock profiles | [OEDI — End-Use Load Profiles](https://data.openei.org/search?q=end-use-load-profiles) |

## Output

Simulation-ready OpenDSS circuit folders with:
- Modified `LoadShapes.dss` pointing to EULP-derived CSV profiles
- Normalized `Loads.dss` with `daily=` references and per-unit scaling
- kW and kVAr CSV loadshape files (96 points per day, 15-min resolution)

## Citation

If you use this pipeline, please cite:

```bibtex
@article{victor_gallardo_2025_methodsx,
  author  = {V{\'\i}ctor-Gallardo, Luis and [co-authors]},
  title   = {A Coupling Pipeline for Integrating {NREL} End-Use Load
             Profiles into {SMART-DS} Synthetic Distribution Feeders},
  journal = {MethodsX},
  year    = {2025},
  note    = {Manuscript submitted / in press}
}
```

## License

MIT License — see [LICENSE](LICENSE).
'''

with open(os.path.join(STAGING, "README.md"), "w", encoding="utf-8") as f:
    f.write(readme)
print("[OK] Wrote README.md")

# ── STEP 4d: LICENSE ──────────────────────────────────────────────────
mit_license = '''MIT License

Copyright (c) 2025 Luis Victor-Gallardo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

with open(os.path.join(STAGING, "LICENSE"), "w", encoding="utf-8") as f:
    f.write(mit_license)
print("[OK] Wrote LICENSE")

# ── STEP 4e: requirements.txt ────────────────────────────────────────
requirements = '''numpy>=1.24
pandas>=2.0
pyarrow>=12.0
openpyxl>=3.1
'''

with open(os.path.join(STAGING, "requirements.txt"), "w", encoding="utf-8") as f:
    f.write(requirements)
print("[OK] Wrote requirements.txt")

# ── STEP 4f: .gitignore ──────────────────────────────────────────────
gitignore = '''# Data files — never commit
*.parquet
*.csv
*.pkl
*.json
*.xlsx
data/
workspace/
output*/

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.eggs/

# OS
.DS_Store
Thumbs.db
'''

with open(os.path.join(STAGING, ".gitignore"), "w", encoding="utf-8") as f:
    f.write(gitignore)
print("[OK] Wrote .gitignore")

# ── STEP 5: Hardcoded path scan ──────────────────────────────────────
PATTERNS = [
    re.compile(r'[A-Za-z]:\\\\', re.IGNORECASE),    # C:\\ style
    re.compile(r'[A-Za-z]:\\[^\\]', re.IGNORECASE),  # C:\Users style
    re.compile(r'/home/', re.IGNORECASE),
    re.compile(r'luisfernando', re.IGNORECASE),
    re.compile(r'Dropbox', re.IGNORECASE),
]

hardcoded_hits = []
src_dir = os.path.join(STAGING, "src")
for dirpath, dirnames, filenames in os.walk(src_dir):
    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(dirpath, fname)
        rel_path = os.path.relpath(fpath, STAGING)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                for pat in PATTERNS:
                    if pat.search(line):
                        hardcoded_hits.append((rel_path, lineno, line.strip()))
                        break  # one hit per line is enough

print(f"\n[SCAN] Found {len(hardcoded_hits)} hardcoded path occurrences")
for rel, ln, txt in hardcoded_hits:
    print(f"  {rel}:{ln}  ->  {txt[:100]}")

# ── STEP 6: Final inventory ──────────────────────────────────────────
total_size = 0
file_counts = {}
all_files = []
for dirpath, dirnames, filenames in os.walk(STAGING):
    for fname in filenames:
        fpath = os.path.join(dirpath, fname)
        fsize = os.path.getsize(fpath)
        total_size += fsize
        ext = os.path.splitext(fname)[1] or "(no ext)"
        file_counts[ext] = file_counts.get(ext, 0) + 1
        all_files.append((os.path.relpath(fpath, STAGING), fsize))

print(f"\n{'='*60}")
print("FINAL INVENTORY")
print(f"{'='*60}")
print(f"Total staging folder size: {total_size / 1024:.1f} KB")
if total_size > 5 * 1024 * 1024:
    print("[STOP] Staging folder exceeds 5 MB!")
else:
    print(f"[OK] Under 5 MB limit ({total_size / (1024*1024):.2f} MB)")

print("\nFile counts by type:")
for ext, count in sorted(file_counts.items()):
    print(f"  {ext}: {count}")

print("\nAll files:")
for rel, sz in sorted(all_files):
    print(f"  {rel}  ({sz/1024:.1f} KB)")

# ── Write STAGING_REPORT.md ───────────────────────────────────────────
report_lines = []
report_lines.append("# Staging Report — dss-eulp-coupling-staged\n")
report_lines.append(f"Generated by build_staging.py\n")

report_lines.append("\n## 1. File Inventory\n")
report_lines.append(f"**Total size:** {total_size/1024:.1f} KB ({total_size/(1024*1024):.2f} MB)\n")
report_lines.append("| Extension | Count |")
report_lines.append("|-----------|-------|")
for ext, count in sorted(file_counts.items()):
    report_lines.append(f"| {ext} | {count} |")

report_lines.append("\n### All Files\n")
report_lines.append("| File | Size (KB) |")
report_lines.append("|------|-----------|")
for rel, sz in sorted(all_files):
    report_lines.append(f"| `{rel}` | {sz/1024:.1f} |")

report_lines.append("\n## 2. Copied Scripts (IN)\n")
report_lines.append("| Source | Destination | Phase |")
report_lines.append("|--------|-------------|-------|")
phase_labels = {
    "phase2": "2 — Extraction",
    "phase3": "3 — Matching",
    "phase4": "4 — Assignment",
    "phase5": "5 — Profiles",
    "phase6": "6 — kVAr",
    "phase7a": "7a — Circuit Build",
}
for src_rel, dst_rel in COPY_MAP:
    phase = "?"
    for key, label in phase_labels.items():
        if key in dst_rel:
            phase = label
            break
    report_lines.append(f"| `{src_rel}` | `{dst_rel}` | {phase} |")

report_lines.append("\n## 3. Excluded Scripts (OUT)\n")
report_lines.append("| Script | Reason |")
report_lines.append("|--------|--------|")
out_scripts = [
    ("run_mix_generator.py", "Phase 1 — LHS/Sobol mix generation"),
    ("deployer_modules/pfs_*.py", "Phase 7b — DER deployment modules"),
    ("run_all_deploys_v2.py", "Phase 7b — DER deployment runner"),
    ("power_flow_sim_daily_EV_STO_DG_deploy.py", "Phase 7c — Power flow simulation"),
    ("check_monitor_outputs.py", "Phase 7c — Monitor output checker"),
    ("aggregate_m1_m2_with_circuits.py", "Results analysis"),
    ("append_experiment_results.py", "XLRM results analysis"),
    ("append_xlrm_long_format.py", "XLRM analysis"),
    ("figure_generation_methodsx.py", "Figure generation"),
    ("download_parquets_*.py", "Data download (not pipeline logic)"),
    ("rev_daily_list_set.py", "Debug helper"),
    ("review_pickles.py", "Debug helper"),
]
for script, reason in out_scripts:
    report_lines.append(f"| `{script}` | {reason} |")

report_lines.append("\n## 4. Hardcoded Path Occurrences\n")
if hardcoded_hits:
    report_lines.append("| File | Line | Content | Suggested Fix |")
    report_lines.append("|------|------|---------|---------------|")
    for rel, ln, txt in hardcoded_hits:
        suggested = "Replace with relative path or config parameter"
        # Escape pipes in content
        txt_escaped = txt.replace("|", "\\|")[:120]
        report_lines.append(f"| `{rel}` | {ln} | `{txt_escaped}` | {suggested} |")
else:
    report_lines.append("No hardcoded paths found.\n")

report_lines.append("\n## 5. Dependency Notes\n")
report_lines.append("### Imports used across IN scripts\n")
report_lines.append("- `os`, `sys`, `re`, `csv`, `time`, `pickle`, `shutil`, `json`, `math`, `random` (stdlib)")
report_lines.append("- `pathlib.Path` (stdlib)")
report_lines.append("- `copy.deepcopy` (stdlib)")
report_lines.append("- `ast.literal_eval` (stdlib)")
report_lines.append("- `collections.defaultdict` (stdlib)")
report_lines.append("- `subprocess` (stdlib)")
report_lines.append("- `pandas` — data manipulation")
report_lines.append("- `numpy` — numerical operations")
report_lines.append("- `pyarrow.parquet` — Parquet I/O")
report_lines.append("- `openpyxl` — Excel I/O (used by `scale_feeder_curves`)")
report_lines.append("")
report_lines.append("All third-party imports are covered by `requirements.txt`.\n")

report_lines.append("### IN scripts that import OUT modules\n")
report_lines.append("- `instantiate_circuits_and_runs.py` (Phase 7a) contains DER deployment logic ")
report_lines.append("  (EV/PV/Storage assignment) inline — it does NOT import `deployer_modules/`. ")
report_lines.append("  For the MethodsX paper scope, the DER assignment portion can be disabled or ")
report_lines.append("  removed without affecting the LoadShapes/Loads rewriting.\n")

report_lines.append("\n## 6. Smoke Test Estimate\n")
report_lines.append("To run Phase 2 → Phase 3 on one feeder from one state:\n")
report_lines.append("1. Download one SMART-DS substation (e.g., `uhs0_1247`) — ~200 MB")
report_lines.append("2. Download EULP Parquets for the loads referenced by that substation's ")
report_lines.append("   `Loads.dss` files — ~50-100 MB per building type")
report_lines.append("3. Download state-level metadata CSVs (residential + commercial) — ~5 MB each")
report_lines.append("4. Run `circuit_make_daily_list_sets.py` (seconds)")
report_lines.append("5. Run `review_parquet_matches.py` (minutes, depends on number of parquets)")
report_lines.append("6. Run `match_smartds_parquets.py` — tolerance escalation across all loads ")
report_lines.append("   (minutes to hours depending on state size)\n")
report_lines.append("**Estimated wall time:** ~10-30 min for a single substation with one state.\n")

with open(os.path.join(STAGING, "STAGING_REPORT.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))
print("[OK] Wrote STAGING_REPORT.md")

print("\n[DONE] Staging complete.")
