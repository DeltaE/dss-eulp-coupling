#!/usr/bin/env python3
r"""
archive_multistate.py — Lean archive builder for dss-eulp-coupling.

Copies BC/ON/QC stage folders from Dropbox into archive/, renamed to
WA/MI/VT.  Uses SMART RECURSION:

  - Root-level files in each stage folder: always copied
  - Small subdirectories (<=30 trackable files): copied fully,
    BUT capped at 5 small dirs per stage (the rest get stubbed)
  - Large subdirectories (>30 trackable files): stubbed with .gitkeep
  - .dss / .parquet / .pkl files: always skipped
  - Blacklisted folder names (daily_parquets etc.): always skipped

The subdir cap keeps stage 8 lean (deployer_modules + a few sample
circuits, matching MT's pattern) while stages 3b-7 are unaffected.

Usage from Anaconda Prompt:
    cd C:\Users\luisfernando\Desktop\phd_workspace\dss-eulp-coupling

    python archive_multistate.py plan     # preview + tree comparison
    python archive_multistate.py copy     # execute
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# ── Paths (baked in) ─────────────────────────────────────────────────────────

DROPBOX_SOURCE = Path(
    r"C:\Users\luisfernando\Dropbox\1_RESEARCH\1_FOCUS_PhD"
    r"\Conferences\Conference_EMH_2025_Ottawa\dist"
)

REPO_ROOT = Path(
    r"C:\Users\luisfernando\Desktop\phd_workspace\dss-eulp-coupling"
)

ARCHIVE_DIR = REPO_ROOT / "archive"

# ── Province -> State mapping ────────────────────────────────────────────────

PROVINCE_TO_STATE = {
    "bc": "wa",
    "on": "mi",
    "qc": "vt",
}

STAGE_SUFFIXES = [
    "3b",
    "3c_downloads",
    "4_profhp",
    "5_kvar",
    "6_profhp_dm",
    "7_profhp_un",
    "8_summer",
    "8_winter",
]

# ── Filtering rules ──────────────────────────────────────────────────────────

SKIP_EXTENSIONS = {".dss", ".parquet", ".pq", ".pkl"}

SKIP_FOLDER_NAMES = {
    "daily_parquets", "parquet_data", "daily_csvs",
    "profiles_use_bench", "data_ev", "_audit",
    "__pycache__", ".spyderproject", ".spyproject",
}
SKIP_FOLDER_PREFIXES = (
    "daily_parquets", "daily_csvs", "profiles_use_bench", "parquet_",
)

# Subdirectories with more than this many trackable files get stubbed
SUBDIR_FILE_THRESHOLD = 30

# Max number of small subdirectories to fully copy per stage folder.
# After this cap, remaining small dirs get stubbed too.
# Keeps stage 8 lean (deployer_modules + a few sample circuits).
MAX_SMALL_SUBDIRS_PER_STAGE = 5

SMARTDS_FOLDER = "3_smartds"


# ── Helpers ──────────────────────────────────────────────────────────────────

def should_skip_dir(name: str) -> bool:
    low = name.lower()
    if low in SKIP_FOLDER_NAMES:
        return True
    for prefix in SKIP_FOLDER_PREFIXES:
        if low.startswith(prefix):
            return True
    return False


def should_skip_file(name: str) -> bool:
    return Path(name).suffix.lower() in SKIP_EXTENSIONS


def count_trackable(path: Path) -> int:
    count = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for name in filenames:
            if not should_skip_file(name):
                count += 1
    return count


def size_str(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 * 1024):.2f} MB"


def ensure_gitkeep(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    gk = folder / ".gitkeep"
    if not gk.exists():
        gk.write_text(
            "# Placeholder - bulk data excluded from Git.\n"
            "# See ARCHIVE_README.md for reproduction instructions.\n"
        )


# ── Smart copy: one stage folder ─────────────────────────────────────────────

def smart_copy_stage(src: Path, dst: Path, dry_run: bool) -> dict:
    stats = {"copied": 0, "skipped_ext": 0, "stubbed_dirs": 0,
             "copied_dirs": 0, "bytes": 0, "capped_dirs": 0}

    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)

    # 1) Root-level files
    for item in sorted(src.iterdir()):
        if item.is_file():
            if should_skip_file(item.name):
                stats["skipped_ext"] += 1
                continue
            stats["copied"] += 1
            try:
                stats["bytes"] += item.stat().st_size
            except OSError:
                pass
            if not dry_run:
                shutil.copy2(item, dst / item.name)

    # 2) Subdirectories
    small_dirs_copied = 0

    for item in sorted(src.iterdir()):
        if not item.is_dir():
            continue
        if should_skip_dir(item.name):
            stats["stubbed_dirs"] += 1
            if not dry_run:
                ensure_gitkeep(dst / item.name)
            continue

        trackable = count_trackable(item)

        if trackable <= SUBDIR_FILE_THRESHOLD and small_dirs_copied < MAX_SMALL_SUBDIRS_PER_STAGE:
            # Small dir under cap: copy fully
            stats["copied_dirs"] += 1
            small_dirs_copied += 1
            _copy_dir_filtered(item, dst / item.name, stats, dry_run)
        elif trackable <= SUBDIR_FILE_THRESHOLD:
            # Small dir but cap reached: stub it
            stats["capped_dirs"] += 1
            if not dry_run:
                ensure_gitkeep(dst / item.name)
        else:
            # Large dir: stub it
            stats["stubbed_dirs"] += 1
            if not dry_run:
                ensure_gitkeep(dst / item.name)

    return stats


def _copy_dir_filtered(src: Path, dst: Path, stats: dict, dry_run: bool) -> None:
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)

    for item in sorted(src.iterdir()):
        if item.is_file():
            if should_skip_file(item.name):
                stats["skipped_ext"] += 1
                continue
            stats["copied"] += 1
            try:
                stats["bytes"] += item.stat().st_size
            except OSError:
                pass
            if not dry_run:
                shutil.copy2(item, dst / item.name)
        elif item.is_dir():
            if should_skip_dir(item.name):
                stats["stubbed_dirs"] += 1
                if not dry_run:
                    ensure_gitkeep(dst / item.name)
                continue
            _copy_dir_filtered(item, dst / item.name, stats, dry_run)


# ── Tree building (for comparison) ───────────────────────────────────────────

def build_existing_tree(root: Path, prefix: str) -> list[str]:
    """Build a tree of files that exist under root for a given state prefix."""
    paths: list[str] = []
    for suffix in STAGE_SUFFIXES:
        folder = root / f"{prefix}_{suffix}"
        if not folder.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames.sort()
            for name in sorted(filenames):
                rel = Path(dirpath).relative_to(root) / name
                paths.append(str(rel).replace("\\", "/"))
    return paths


def build_planned_tree(src_prefix: str, dst_prefix: str) -> list[str]:
    """Simulate what smart_copy_stage would produce."""
    paths: list[str] = []

    for suffix in STAGE_SUFFIXES:
        src = DROPBOX_SOURCE / f"{src_prefix}_{suffix}"
        dst_name = f"{dst_prefix}_{suffix}"

        if not src.exists():
            continue

        # Root files
        for item in sorted(src.iterdir()):
            if item.is_file() and not should_skip_file(item.name):
                paths.append(f"{dst_name}/{item.name}")

        # Subdirectories (with cap logic)
        small_dirs_copied = 0
        for item in sorted(src.iterdir()):
            if not item.is_dir():
                continue
            if should_skip_dir(item.name):
                paths.append(f"{dst_name}/{item.name}/.gitkeep")
                continue

            trackable = count_trackable(item)

            if trackable <= SUBDIR_FILE_THRESHOLD and small_dirs_copied < MAX_SMALL_SUBDIRS_PER_STAGE:
                small_dirs_copied += 1
                _collect_planned(item, f"{dst_name}/{item.name}", paths)
            elif trackable <= SUBDIR_FILE_THRESHOLD:
                paths.append(f"{dst_name}/{item.name}/.gitkeep  "
                             f"[CAPPED: {trackable} files]")
            else:
                paths.append(f"{dst_name}/{item.name}/.gitkeep  "
                             f"[STUBBED: {trackable} files]")

    return paths


def _collect_planned(src: Path, rel_prefix: str, paths: list[str]) -> None:
    for item in sorted(src.iterdir()):
        if item.is_file():
            if not should_skip_file(item.name):
                paths.append(f"{rel_prefix}/{item.name}")
        elif item.is_dir():
            if should_skip_dir(item.name):
                paths.append(f"{rel_prefix}/{item.name}/.gitkeep")
            else:
                _collect_planned(item, f"{rel_prefix}/{item.name}", paths)


def print_tree(title: str, paths: list[str], max_per_stage: int = 40) -> None:
    """Print a tree grouped by stage, truncating long stages."""
    print(f"\n--- {title} ---\n")

    if not paths:
        print("  (empty)\n")
        return

    current_stage = None
    stage_count = 0

    for p in paths:
        # Detect stage boundary (first path component)
        stage = p.split("/")[0]
        if stage != current_stage:
            if current_stage is not None and stage_count > max_per_stage:
                print(f"    ... and {stage_count - max_per_stage} more")
            current_stage = stage
            stage_count = 0
            print(f"  {stage}/")

        stage_count += 1
        inner = "/".join(p.split("/")[1:])
        if stage_count <= max_per_stage:
            print(f"    {inner}")

    # Final stage overflow
    if stage_count > max_per_stage:
        print(f"    ... and {stage_count - max_per_stage} more")

    print(f"\n  Total: {len(paths)} entries\n")


def show_tree_comparison() -> None:
    print("\n" + "=" * 55)
    print("  TREE COMPARISON: existing MT vs planned WA / MI / VT")
    print("=" * 55)

    mt_tree = build_existing_tree(ARCHIVE_DIR, "mt")
    print_tree("MT (existing in repo)", mt_tree)

    for province, state in sorted(PROVINCE_TO_STATE.items()):
        planned = build_planned_tree(province, state)
        print_tree(f"{state.upper()} (planned from {province.upper()})", planned)


# ── SMART-DS ─────────────────────────────────────────────────────────────────

def process_smartds(dry_run: bool) -> None:
    print("\n=== SMART-DS topology (dir structure only) ===\n")

    src = DROPBOX_SOURCE / SMARTDS_FOLDER
    dst = ARCHIVE_DIR / SMARTDS_FOLDER

    if not src.exists():
        print(f"  SKIP    {SMARTDS_FOLDER} not in Dropbox source")
        return

    if dst.exists():
        print(f"  EXISTS  {SMARTDS_FOLDER} already in archive")
        return

    dir_count = sum(1 for _ in os.walk(src))

    if dry_run:
        print(f"  PLAN    Would create {dir_count} dirs with .gitkeep")
        sample = []
        for dirpath, dirnames, _ in os.walk(src):
            rel = str(Path(dirpath).relative_to(src)).replace("\\", "/")
            if rel == ".":
                rel = SMARTDS_FOLDER
            else:
                rel = f"{SMARTDS_FOLDER}/{rel}"
            sample.append(rel + "/")
        print(f"\n  Directory structure ({len(sample)} dirs):\n")
        for s in sample[:30]:
            print(f"    {s}")
        if len(sample) > 30:
            print(f"    ... and {len(sample) - 30} more dirs")
    else:
        for dirpath, dirnames, _ in os.walk(src):
            rel = Path(dirpath).relative_to(src)
            dest_dir = dst / rel
            ensure_gitkeep(dest_dir)
        print(f"  DONE    Created {dir_count} dirs with .gitkeep")


# ── Main pipeline ────────────────────────────────────────────────────────────

def process_state_stages(dry_run: bool) -> None:
    print("\n=== State stage folders (province -> state) ===\n")

    grand = {"copied": 0, "skipped_ext": 0, "stubbed_dirs": 0,
             "copied_dirs": 0, "bytes": 0, "capped_dirs": 0}

    for province, state in sorted(PROVINCE_TO_STATE.items()):
        for suffix in STAGE_SUFFIXES:
            src = DROPBOX_SOURCE / f"{province}_{suffix}"
            dst = ARCHIVE_DIR / f"{state}_{suffix}"

            if not src.exists():
                print(f"  MISSING  {province}_{suffix}")
                continue

            if dst.exists():
                existing = sum(1 for f in dst.rglob("*") if f.is_file())
                print(f"  EXISTS   {state}_{suffix}  ({existing} files)")
                continue

            stats = smart_copy_stage(src, dst, dry_run)

            for k in grand:
                grand[k] += stats[k]

            tag = "PLAN  " if dry_run else "COPIED"
            parts = [f"{stats['copied']} files",
                     size_str(stats['bytes']),
                     f"{stats['copied_dirs']} small dirs"]
            if stats['stubbed_dirs']:
                parts.append(f"{stats['stubbed_dirs']} stubbed")
            if stats['capped_dirs']:
                parts.append(f"{stats['capped_dirs']} capped")
            detail = ", ".join(parts)
            print(f"  {tag} {province}_{suffix} -> {state}_{suffix}  ({detail})")

    print(f"\n  Grand total: {grand['copied']} files ({size_str(grand['bytes'])})")
    print(f"  Skipped by ext: {grand['skipped_ext']}")
    print(f"  Dirs stubbed: {grand['stubbed_dirs']}, capped: {grand['capped_dirs']}")


def write_readme(dry_run: bool) -> None:
    print("\n=== ARCHIVE_README.md ===\n")

    readme_path = ARCHIVE_DIR / "ARCHIVE_README.md"

    found: dict[str, list[str]] = {}
    for item in sorted(ARCHIVE_DIR.iterdir()):
        if not item.is_dir():
            continue
        name = item.name
        for suffix in STAGE_SUFFIXES:
            if name.endswith(f"_{suffix}"):
                state_code = name[: -(len(suffix) + 1)]
                found.setdefault(state_code.upper(), []).append(suffix)

    states_section = ""
    for state, stages in sorted(found.items()):
        states_section += f"- **{state}**: stages {', '.join(stages)}\n"

    content = f"""\
# Archive: Multi-State EULP x SMART-DS Coupling Results

Pipeline output artifacts for multiple US states, demonstrating that the
SMART-DS x EULP coupling pipeline generalises beyond the primary North
Carolina validation site.

## Province to State Mapping

| Province | State | Abbr |
|----------|-------|------|
| British Columbia | Washington | WA |
| Ontario | Michigan | MI |
| Quebec | Vermont | VT |
| Alberta | Montana | MT |

## States Archived

{states_section}
## Pipeline Stages

| Stage | Description |
|-------|-------------|
| `3b` | Building-type matching (residential + commercial CSVs) |
| `3c_downloads` | EULP download manifests and scripts |
| `4_profhp` | Baseline load profile assignment |
| `5_kvar` | Reactive power (kVAr) preparation |
| `6_profhp_dm` | Demand-managed profile variant |
| `7_profhp_un` | Uncontrolled profile variant |
| `8_summer` | OpenDSS summer simulation results |
| `8_winter` | OpenDSS winter simulation results |

## What Is Included

- **CSV manifests**: matching tables, parquet inventories, circuit summaries
- **Python scripts**: pipeline stage scripts for each state
- **Run logs**: `run_log.txt` with ok/fail counts per simulation batch
- **Convergence reports**: `circuit_check_report.csv` with per-feeder status
- **Small utility folders**: scenario controls, deployer modules, etc.
- **Sample circuits**: a few per-feeder result directories per state
- **SMART-DS structure**: feeder directory hierarchy (`.dss` files excluded)

## What Is Excluded

Large data directories are stubbed with `.gitkeep` placeholders:

- `*.dss` : OpenDSS circuit models (regenerate via stage 7)
- `*.parquet` / `*.pq` : EULP load profile data (download via NREL OEDI)
- `*.pkl` : intermediate pickle files
- Per-feeder bulk directories (>30 files) : stubbed with `.gitkeep`
- Per-circuit directories beyond the sample cap : stubbed with `.gitkeep`
- `parquet_data/`, `daily_parquets/`, `daily_csvs/` : bulk data dirs

## Reproduction

1. Clone this repository and follow the root `README.md`
2. Run pipeline stages 1-7 with the desired state configuration
3. Simulation outputs appear in `8_summer/` and `8_winter/`

## Data Provenance

Processed during the EMH 2025 multi-state simulation campaign
(174 circuit-season configurations, 116 successful runs across four US
states).  See `emh_2025_variant_and_matching_inventory.md` for inventory.
"""

    if dry_run:
        print(f"  PLAN   Would write {readme_path.name} ({len(content)} chars)")
    else:
        readme_path.write_text(content, encoding="utf-8")
        print(f"  WROTE  {readme_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command", choices=["plan", "copy"],
        help="'plan' = dry run + tree comparison; 'copy' = execute.",
    )
    args = parser.parse_args()
    dry_run = args.command == "plan"

    label = "DRY RUN (plan)" if dry_run else "EXECUTING (copy)"
    print(f"\n{'=' * 55}")
    print(f"  {label}")
    print(f"  Source:    {DROPBOX_SOURCE}")
    print(f"  Archive:   {ARCHIVE_DIR}")
    print(f"  Threshold: subdirs >{SUBDIR_FILE_THRESHOLD} files -> stubbed")
    print(f"  Cap:       max {MAX_SMALL_SUBDIRS_PER_STAGE} small subdirs "
          f"copied per stage")
    print(f"{'=' * 55}")

    if not DROPBOX_SOURCE.exists():
        print(f"\nERROR: Source not found:\n  {DROPBOX_SOURCE}")
        return 1
    if not REPO_ROOT.exists():
        print(f"\nERROR: Repo not found:\n  {REPO_ROOT}")
        return 1

    # Show source contents
    print("\n=== Dropbox source ===\n")
    for item in sorted(DROPBOX_SOURCE.iterdir()):
        if item.is_dir():
            print(f"  [dir] {item.name}/")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    process_state_stages(dry_run)
    process_smartds(dry_run)
    write_readme(dry_run)

    if dry_run:
        show_tree_comparison()

    print(f"\n{'=' * 55}")
    if dry_run:
        print("Plan complete. Review the trees above, then:")
        print("  python archive_multistate.py copy")
    else:
        print("Done! Next in Git Bash:")
        print("  cd /c/Users/luisfernando/Desktop/phd_workspace/dss-eulp-coupling")
        print("  git add archive/")
        print("  git status")
        print('  git commit -m "archive: add WA/MI/VT multi-state results"')
        print("  git push origin archive/mt-nc-results")
    print(f"{'=' * 55}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
