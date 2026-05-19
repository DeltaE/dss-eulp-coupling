#!/usr/bin/env python3
"""Stage downloaded SMART-DS OpenDSS feeders into a flat circuit folder."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SMARTDS_ROOT = REPO_ROOT / "0_download_smartds" / "data_raw" / "smartds"
DEFAULT_TARGET = REPO_ROOT / "ab_3b" / "circuits_plain_format"
DEFAULT_REGISTRY = REPO_ROOT / "ab_3b" / "feeder_registry.json"


@dataclass(frozen=True)
class FeederCopy:
    source: Path
    destination: Path
    relative_source: str


def has_required_dss_files(path: Path) -> bool:
    try:
        names = {child.name.lower() for child in path.iterdir() if child.is_file()}
    except PermissionError:
        return False
    return "loads.dss" in names and "loadshapes.dss" in names


def path_matches_filters(path: Path, filters: list[str]) -> bool:
    if not filters:
        return True
    haystack = path.as_posix().lower()
    return any(item.lower() in haystack for item in filters)


def discover_feeders(root: Path, filters: list[str]) -> list[Path]:
    feeders = [p for p in root.rglob("*") if p.is_dir() and has_required_dss_files(p)]
    feeders = [p for p in feeders if path_matches_filters(p.relative_to(root), filters)]
    feeders.sort(key=lambda p: p.relative_to(root).as_posix().lower())
    return feeders


def unique_destination(target: Path, feeder_name: str, used: set[Path], *, allow_existing: bool) -> Path:
    candidate = target / feeder_name
    if candidate not in used and (allow_existing or not candidate.exists()):
        used.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = target / f"{feeder_name}__{index}"
        if candidate not in used and (allow_existing or not candidate.exists()):
            used.add(candidate)
            return candidate
        index += 1


def build_copy_plan(
    feeders: list[Path],
    root: Path,
    target: Path,
    limit: Optional[int],
    *,
    allow_existing: bool,
) -> list[FeederCopy]:
    if limit is not None:
        feeders = feeders[:limit]

    used: set[Path] = set()
    plan: list[FeederCopy] = []
    for feeder in feeders:
        destination = unique_destination(target, feeder.name, used, allow_existing=allow_existing)
        plan.append(
            FeederCopy(
                source=feeder,
                destination=destination,
                relative_source=feeder.relative_to(root).as_posix() + "/",
            )
        )
    return plan


def copy_feeder(item: FeederCopy, *, dry_run: bool, overwrite: bool) -> None:
    if dry_run:
        return
    if item.destination.exists() and overwrite:
        shutil.rmtree(item.destination)
    if item.destination.exists():
        raise FileExistsError(f"Destination already exists: {item.destination}")
    item.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(item.source, item.destination)


def write_registry(path: Path, smartds_root: Path, target: Path, plan: list[FeederCopy], dry_run: bool) -> None:
    registry = {
        "smart_ds_root": str(smartds_root),
        "circuits_plain_format": str(target),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feeders": [
            {
                "circuit_id": index,
                "circuit": f"circuit_{index}",
                "substation": item.source.parent.name,
                "feeder_name": item.source.name,
                "original_path": item.relative_source,
                "flat_dir": item.destination.name + "/",
            }
            for index, item in enumerate(plan, start=1)
        ],
    }
    registry["circuit_name_map"] = {
        entry["feeder_name"]: entry["circuit"] for entry in registry["feeders"]
    }
    registry["reverse_circuit_map"] = {
        entry["circuit"]: entry["feeder_name"] for entry in registry["feeders"]
    }

    if dry_run:
        print(f"Dry run: would write registry to {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smartds-root", type=Path, default=DEFAULT_SMARTDS_ROOT)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--include",
        nargs="+",
        default=[],
        help="Optional substring filters applied to paths relative to --smartds-root.",
    )
    parser.add_argument("--max-feeders", type=int, help="Limit staged feeders for smoke tests.")
    parser.add_argument("--overwrite", action="store_true", help="Remove and replace existing destination feeder folders.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smartds_root = args.smartds_root.resolve()
    target = args.target.resolve()
    registry = args.registry.resolve()

    if not smartds_root.exists():
        print(f"SMART-DS root not found: {smartds_root}", file=sys.stderr)
        return 1

    feeders = discover_feeders(smartds_root, args.include)
    plan = build_copy_plan(
        feeders,
        smartds_root,
        target,
        args.max_feeders,
        allow_existing=args.overwrite,
    )

    print(f"Discovered feeders: {len(feeders):,}")
    print(f"Planned copies: {len(plan):,}")
    print(f"Target: {target}")

    for index, item in enumerate(plan, start=1):
        copy_feeder(item, dry_run=args.dry_run, overwrite=args.overwrite)
        if index == 1 or index % 100 == 0 or index == len(plan):
            print(f"{index:,}/{len(plan):,}: {item.source} -> {item.destination}")

    write_registry(registry, smartds_root, target, plan, args.dry_run)
    print(f"Registry: {registry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
