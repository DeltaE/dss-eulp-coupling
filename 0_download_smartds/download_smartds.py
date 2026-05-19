#!/usr/bin/env python3
"""Download selected SMART-DS v1.0 assets from the public OEDI S3 bucket.

This is a command-line rewrite of the legacy D:\\lvg SMART-DS downloader. The
legacy script navigated the OpenEI S3 viewer with Selenium; this script queries
the public S3 ListObjectsV2 endpoint directly and writes the same practical
folder layout used by the local workflow.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional
from urllib.parse import quote

import requests


BUCKET = "oedi-data-lake"
S3_BASE_URL = f"https://{BUCKET}.s3.amazonaws.com"
SMARTDS_ROOT_PREFIX = "SMART-DS/v1.0"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YEAR = 2018
DEFAULT_SCENARIOS = ("base_timeseries", "solar_high_batteries_high_timeseries")
DEFAULT_REGIONS = ("SFO", "AUS", "GSO")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "0_download_smartds" / "data_raw" / "smartds"
DEFAULT_SUFFIXES = {
    "opendss": (".dss",),
    "analysis": (".csv",),
    "profiles": (".csv",),
    "solar": (".csv",),
    "load": (".parquet",),
}


@dataclass(frozen=True)
class DownloadItem:
    key: str
    destination: Path
    size: int


def strip_xml_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def child_text(element: ET.Element, name: str, default: str = "") -> str:
    for child in element:
        if strip_xml_namespace(child.tag) == name:
            return child.text or default
    return default


def request_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: Optional[dict[str, str]] = None,
    timeout: float,
    retries: int,
    stream: bool = False,
) -> requests.Response:
    last_error: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout, stream=stream)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= retries:
                break
            sleep_seconds = min(2**attempt, 20)
            print(f"Retrying after request failure: {exc}", file=sys.stderr)
            time.sleep(sleep_seconds)
    raise RuntimeError(f"Request failed after {retries + 1} attempts: {last_error}") from last_error


def list_s3_page(
    session: requests.Session,
    *,
    prefix: str,
    delimiter: Optional[str],
    continuation_token: Optional[str],
    timeout: float,
    retries: int,
) -> tuple[list[tuple[str, int]], list[str], Optional[str]]:
    params = {
        "list-type": "2",
        "prefix": prefix,
        "max-keys": "1000",
    }
    if delimiter is not None:
        params["delimiter"] = delimiter
    if continuation_token:
        params["continuation-token"] = continuation_token

    response = request_with_retries(
        session,
        S3_BASE_URL,
        params=params,
        timeout=timeout,
        retries=retries,
    )
    root = ET.fromstring(response.content)

    objects: list[tuple[str, int]] = []
    prefixes: list[str] = []
    next_token: Optional[str] = None

    for child in root:
        tag = strip_xml_namespace(child.tag)
        if tag == "Contents":
            key = child_text(child, "Key")
            size_text = child_text(child, "Size", "0")
            if key and not key.endswith("/"):
                objects.append((key, int(size_text)))
        elif tag == "CommonPrefixes":
            common_prefix = child_text(child, "Prefix")
            if common_prefix:
                prefixes.append(common_prefix)
        elif tag == "NextContinuationToken":
            next_token = child.text

    return objects, prefixes, next_token


def iter_s3_objects(
    session: requests.Session,
    prefix: str,
    *,
    timeout: float,
    retries: int,
) -> Iterator[tuple[str, int]]:
    continuation_token: Optional[str] = None
    while True:
        objects, _, continuation_token = list_s3_page(
            session,
            prefix=prefix,
            delimiter=None,
            continuation_token=continuation_token,
            timeout=timeout,
            retries=retries,
        )
        yield from objects
        if not continuation_token:
            break


def list_child_names(
    session: requests.Session,
    prefix: str,
    *,
    timeout: float,
    retries: int,
) -> list[str]:
    continuation_token: Optional[str] = None
    names: list[str] = []
    while True:
        _, prefixes, continuation_token = list_s3_page(
            session,
            prefix=prefix,
            delimiter="/",
            continuation_token=continuation_token,
            timeout=timeout,
            retries=retries,
        )
        for child_prefix in prefixes:
            child = child_prefix.removeprefix(prefix).strip("/")
            if child:
                names.append(child)
        if not continuation_token:
            break
    return sorted(set(names), key=str.lower)


def key_url(key: str) -> str:
    return f"{S3_BASE_URL}/{quote(key, safe='/')}"


def suffix_match(key: str, suffixes: Iterable[str]) -> bool:
    key_lower = key.lower()
    return any(key_lower.endswith(suffix.lower()) for suffix in suffixes)


def local_from_prefix(key: str, remote_prefix: str, local_prefix: Path) -> Path:
    relative = key.removeprefix(remote_prefix)
    return local_prefix / Path(*relative.split("/"))


def add_objects(
    items: list[DownloadItem],
    session: requests.Session,
    *,
    remote_prefix: str,
    local_prefix: Path,
    suffixes: Iterable[str],
    timeout: float,
    retries: int,
) -> None:
    for key, size in iter_s3_objects(session, remote_prefix, timeout=timeout, retries=retries):
        if suffix_match(key, suffixes):
            items.append(DownloadItem(key=key, destination=local_from_prefix(key, remote_prefix, local_prefix), size=size))


def build_download_plan(
    session: requests.Session,
    *,
    output_dir: Path,
    year: int,
    regions: list[str],
    subregions: Optional[list[str]],
    scenarios: list[str],
    include_profiles: bool,
    include_solar: bool,
    include_load: bool,
    include_opendss: bool,
    include_analysis: bool,
    timeout: float,
    retries: int,
) -> list[DownloadItem]:
    items: list[DownloadItem] = []
    year_prefix = f"{SMARTDS_ROOT_PREFIX}/{year}/"

    for region in regions:
        region = region.upper()
        region_prefix = f"{year_prefix}{region}/"
        region_subregions = subregions or list_child_names(
            session,
            region_prefix,
            timeout=timeout,
            retries=retries,
        )

        for subregion in region_subregions:
            subregion = subregion.strip("/")
            subregion_prefix = f"{region_prefix}{subregion}/"
            local_subregion = output_dir / region / subregion

            if include_profiles:
                add_objects(
                    items,
                    session,
                    remote_prefix=f"{subregion_prefix}profiles/",
                    local_prefix=local_subregion / "profiles_data",
                    suffixes=DEFAULT_SUFFIXES["profiles"],
                    timeout=timeout,
                    retries=retries,
                )

            if include_solar:
                add_objects(
                    items,
                    session,
                    remote_prefix=f"{subregion_prefix}solar_data/",
                    local_prefix=local_subregion / "solar_data",
                    suffixes=DEFAULT_SUFFIXES["solar"],
                    timeout=timeout,
                    retries=retries,
                )

            if include_load:
                add_objects(
                    items,
                    session,
                    remote_prefix=f"{subregion_prefix}load_data/",
                    local_prefix=local_subregion / "parquet_data",
                    suffixes=DEFAULT_SUFFIXES["load"],
                    timeout=timeout,
                    retries=retries,
                )

            for scenario in scenarios:
                scenario = scenario.strip("/")
                remote_opendss = f"{subregion_prefix}scenarios/{scenario}/opendss/"
                local_opendss = local_subregion / scenario / "opendss"
                suffixes: list[str] = []
                if include_opendss:
                    suffixes.extend(DEFAULT_SUFFIXES["opendss"])
                if include_analysis:
                    suffixes.extend(DEFAULT_SUFFIXES["analysis"])
                if suffixes:
                    add_objects(
                        items,
                        session,
                        remote_prefix=remote_opendss,
                        local_prefix=local_opendss,
                        suffixes=suffixes,
                        timeout=timeout,
                        retries=retries,
                    )

    return items


def download_item(
    session: requests.Session,
    item: DownloadItem,
    *,
    force: bool,
    dry_run: bool,
    timeout: float,
    retries: int,
) -> str:
    if item.destination.exists() and item.destination.stat().st_size == item.size and not force:
        return "skipped"

    if dry_run:
        return "planned"

    item.destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = item.destination.with_suffix(item.destination.suffix + ".part")

    response = request_with_retries(
        session,
        key_url(item.key),
        timeout=timeout,
        retries=retries,
        stream=True,
    )
    with temp_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    temp_path.replace(item.destination)
    return "downloaded"


def write_manifest(manifest_path: Path, items: list[DownloadItem]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps({"key": item.key, "destination": str(item.destination), "size": item.size}))
            f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--regions", nargs="+", default=list(DEFAULT_REGIONS), help="SMART-DS regions such as SFO AUS GSO.")
    parser.add_argument("--subregions", nargs="+", help="Optional subregion filter, e.g. P21U rural urban-suburban.")
    parser.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, help="Optional JSONL manifest path for the planned files.")
    parser.add_argument("--only-opendss", action="store_true", help="Download only OpenDSS .dss files and analysis CSVs.")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip analysis CSVs under opendss/**/analysis.")
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--skip-solar", action="store_true")
    parser.add_argument("--skip-load", action="store_true", help="Skip load_data parquet files.")
    parser.add_argument("--force", action="store_true", help="Re-download even when a local file has the expected size.")
    parser.add_argument("--dry-run", action="store_true", help="List and count planned downloads without writing files.")
    parser.add_argument("--max-files", type=int, help="Limit downloads after planning, useful for smoke tests.")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    include_profiles = not args.skip_profiles and not args.only_opendss
    include_solar = not args.skip_solar and not args.only_opendss
    include_load = not args.skip_load and not args.only_opendss
    include_opendss = True
    include_analysis = not args.skip_analysis

    session = requests.Session()
    print("Building SMART-DS download plan...")
    items = build_download_plan(
        session,
        output_dir=args.output_dir,
        year=args.year,
        regions=args.regions,
        subregions=args.subregions,
        scenarios=args.scenarios,
        include_profiles=include_profiles,
        include_solar=include_solar,
        include_load=include_load,
        include_opendss=include_opendss,
        include_analysis=include_analysis,
        timeout=args.timeout,
        retries=args.retries,
    )

    if args.max_files is not None:
        items = items[: args.max_files]

    total_bytes = sum(item.size for item in items)
    print(f"Planned files: {len(items):,}")
    print(f"Planned bytes: {total_bytes / 1024**3:.2f} GiB")

    if args.manifest:
        write_manifest(args.manifest, items)
        print(f"Wrote manifest: {args.manifest}")

    counts = {"downloaded": 0, "skipped": 0, "planned": 0}
    for index, item in enumerate(items, start=1):
        status = download_item(
            session,
            item,
            force=args.force,
            dry_run=args.dry_run,
            timeout=args.timeout,
            retries=args.retries,
        )
        counts[status] += 1
        if index == 1 or index % 100 == 0 or index == len(items):
            print(f"{index:,}/{len(items):,} {status}: {item.destination}")

    print(
        "Done. "
        f"downloaded={counts['downloaded']:,}, "
        f"skipped={counts['skipped']:,}, "
        f"planned={counts['planned']:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
