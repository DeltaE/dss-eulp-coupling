#!/usr/bin/env python3
"""
scan_topology_universe.py — Inventory all SMART-DS circuits on a local drive.

Walks a root directory looking for feeder folders (directories containing
Loads.dss + LoadShapes.dss), extracts structure metadata (geography, urbanicity,
feeder ID), counts loads per feeder, and outputs:
  1. A summary table (printed + CSV)
  2. Draft topology_registry.yaml entries ready to paste

Usage (Anaconda Prompt on Machine 3):
    python scan_topology_universe.py --root D:\lvg
    python scan_topology_universe.py --root D:\lvg --geography AUS        # TX/Austin only
    python scan_topology_universe.py --root D:\lvg --geography AUS --csv  # also write CSV
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def has_required_dss(path: Path) -> bool:
    """A feeder directory must contain Loads.dss and LoadShapes.dss."""
    try:
        names = {f.name.lower() for f in path.iterdir() if f.is_file()}
    except PermissionError:
        return False
    return "loads.dss" in names and "loadshapes.dss" in names


def count_loads(feeder_dir: Path) -> int:
    """Count load definitions in Loads.dss."""
    loads_file = feeder_dir / "Loads.dss"
    if not loads_file.exists():
        # try case-insensitive
        for f in feeder_dir.iterdir():
            if f.name.lower() == "loads.dss":
                loads_file = f
                break
    try:
        return sum(1 for line in loads_file.read_text(encoding="utf-8").splitlines()
                   if line.strip().lower().startswith("new load."))
    except Exception:
        return -1


def infer_structure(feeder_path: Path, root: Path) -> dict:
    """Infer geography / urbanicity / feeder_id from the path structure.

    Expected pattern:  <root>/<geography>/<urbanicity>/base_timeseries/opendss/<feeder_id>/
    Falls back gracefully if the structure doesn't match exactly.
    """
    try:
        rel = feeder_path.relative_to(root)
    except ValueError:
        rel = feeder_path

    parts = rel.parts
    feeder_id = parts[-1] if parts else "unknown"

    # Try to find base_timeseries/opendss in the path to anchor the parsing
    parts_lower = [p.lower() for p in parts]
    if "opendss" in parts_lower:
        idx = parts_lower.index("opendss")
        # feeder_id is the folder right after opendss
        feeder_id = parts[idx + 1] if idx + 1 < len(parts) else feeder_id
        # geography and urbanicity are typically 2 and 1 levels above base_timeseries
        bt_idx = idx - 1  # base_timeseries
        urbanicity = parts[bt_idx - 1] if bt_idx - 1 >= 0 else "unknown"
        geography = parts[bt_idx - 2] if bt_idx - 2 >= 0 else "unknown"
    else:
        geography = parts[0] if len(parts) > 2 else "unknown"
        urbanicity = parts[1] if len(parts) > 2 else "unknown"

    # Build the relative path from root to the opendss parent (for smart_ds_relpath)
    try:
        opendss_dir = feeder_path.parent  # the opendss/ folder
        smart_ds_relpath = opendss_dir.relative_to(root).as_posix()
    except ValueError:
        smart_ds_relpath = str(feeder_path.parent)

    return {
        "feeder_id": feeder_id,
        "geography": geography,
        "urbanicity": urbanicity,
        "smart_ds_relpath": smart_ds_relpath,
        "feeder_path": feeder_path.as_posix(),
    }


def discover_feeders(root: Path, geography_filter: str | None = None) -> list[dict]:
    """Walk root, find all feeder directories, return structured metadata."""
    feeders = []
    for candidate in sorted(root.rglob("*"), key=lambda p: p.as_posix().lower()):
        if not candidate.is_dir():
            continue
        if not has_required_dss(candidate):
            continue
        if geography_filter:
            # Check if geography filter appears in the path
            if geography_filter.lower() not in candidate.as_posix().lower():
                continue

        info = infer_structure(candidate, root)
        info["load_count"] = count_loads(candidate)
        feeders.append(info)
    return feeders


def print_summary(feeders: list[dict]) -> None:
    """Print a formatted summary table."""
    if not feeders:
        print("No feeders found.")
        return

    print(f"\n{'='*90}")
    print(f"  Found {len(feeders)} feeder(s)")
    print(f"{'='*90}")
    print(f"  {'Geography':<10} {'Urbanicity':<12} {'Feeder ID':<25} {'Loads':<8} {'smart_ds_relpath'}")
    print(f"  {'-'*10} {'-'*12} {'-'*25} {'-'*8} {'-'*40}")
    for f in feeders:
        print(f"  {f['geography']:<10} {f['urbanicity']:<12} {f['feeder_id']:<25} {f['load_count']:<8} {f['smart_ds_relpath']}")

    # Summary by geography x urbanicity
    combos = {}
    for f in feeders:
        key = (f["geography"], f["urbanicity"])
        combos.setdefault(key, []).append(f)
    print(f"\n  Summary by geography x urbanicity:")
    for (geo, urb), group in sorted(combos.items()):
        total_loads = sum(f["load_count"] for f in group if f["load_count"] > 0)
        print(f"    {geo}/{urb}: {len(group)} feeder(s), {total_loads} total loads")


def print_registry_draft(feeders: list[dict]) -> None:
    """Print draft topology_registry.yaml entries."""
    print(f"\n{'='*90}")
    print("  Draft topology_registry.yaml entries (copy-paste into configs/topology_registry.yaml):")
    print(f"{'='*90}\n")

    # Map geography to state (known SMART-DS geographies)
    geo_to_state = {"GSO": "NC", "AUS": "TX", "SFO": "CA"}

    for f in feeders:
        state = geo_to_state.get(f["geography"].upper(), "??")
        topo_id = f"{state}_{f['geography']}_{f['urbanicity']}_{f['feeder_id']}"
        print(f"  {topo_id}:")
        print(f"    topology_state: {state}")
        print(f"    geography: {f['geography']}")
        print(f"    urbanicity: {f['urbanicity']}")
        print(f"    feeder_id: {f['feeder_id']}")
        print(f"    smart_ds_relpath: \"{f['smart_ds_relpath']}\"")
        print(f"    circuit_folder: \"{f['feeder_id']}\"")
        print(f"    status: ready")
        print(f"    description: \"{state} {f['geography']} {f['urbanicity']} SMART-DS feeder ({f['load_count']} loads)\"")
        print()


def write_csv(feeders: list[dict], output: Path) -> None:
    """Write inventory to CSV."""
    fields = ["geography", "urbanicity", "feeder_id", "load_count", "smart_ds_relpath", "feeder_path"]
    with open(output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(feeders)
    print(f"\n  CSV written: {output}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan local SMART-DS downloads and inventory available circuits.")
    ap.add_argument("--root", required=True, type=Path, help="Root of SMART-DS downloads (e.g. D:\\lvg)")
    ap.add_argument("--geography", default=None, help="Filter by geography (e.g. AUS, GSO, SFO)")
    ap.add_argument("--csv", action="store_true", help="Also write topology_inventory.csv")
    args = ap.parse_args()

    if not args.root.exists():
        sys.exit(f"Root not found: {args.root}")

    print(f"Scanning {args.root} for SMART-DS feeders...")
    if args.geography:
        print(f"  Filter: geography={args.geography}")

    feeders = discover_feeders(args.root, args.geography)
    print_summary(feeders)
    print_registry_draft(feeders)

    if args.csv:
        write_csv(feeders, Path("topology_inventory.csv"))


if __name__ == "__main__":
    main()
