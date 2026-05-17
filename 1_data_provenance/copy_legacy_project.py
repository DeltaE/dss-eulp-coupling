"""Copy-only setup helper for the EULP metadata reproduction project.

This Python script mirrors the guarded copy procedure used to create this
workspace. It skips existing destination paths and never deletes source files.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(r"C:\Users\luisf\Dropbox\1_RESEARCH\1_FOCUS_PhD\6_Paper_3_Expander\workflow_download_metadata")
DESTINATION = Path(r"C:\Users\luisf\Documents\DSS")

LEGACY_FILES = [
    "append_csvs_script.py",
    "append_csvs_script_V2.py",
    "append_csvs_script_select_states.py",
    "slice_states_v2.py",
    "slice_states_v3.py",
    "download_residential_metadata.py",
    "download_residential_metadata_2.py",
    "download_commercial_metadata.py",
    "download_commercial_metadata_19_20.py",
    "preview_csvs.py",
    "folder_append_multiple.py",
    "pds_database_address.txt",
]

PROJECT_DIRS = [
    "config",
    "docs",
    "scripts_legacy",
    "src/eulp_metadata",
    "outputs",
    "data_raw",
    "data_derived/historical",
]


def copy_file_no_overwrite(src: Path, dst: Path) -> dict:
    if dst.exists():
        return {"kind": "file", "source": str(src), "destination": str(dst), "status": "skipped_exists"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"kind": "file", "source": str(src), "destination": str(dst), "status": "copied", "bytes": dst.stat().st_size}


def copy_dir_no_overwrite(src: Path, dst_parent: Path) -> dict:
    dst = dst_parent / src.name
    if dst.exists():
        return {"kind": "directory", "source": str(src), "destination": str(dst), "status": "skipped_exists"}
    dst_parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, copy_function=shutil.copy2)
    files = [p for p in dst.rglob("*") if p.is_file()]
    return {
        "kind": "directory",
        "source": str(src),
        "destination": str(dst),
        "status": "copied",
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
    }


def main() -> None:
    source = SOURCE.resolve()
    destination = DESTINATION.resolve()
    if source == destination:
        raise SystemExit("Source and destination are identical; refusing.")
    if str(destination).lower().startswith(str(source).lower() + "\\"):
        raise SystemExit("Destination is inside source; refusing.")

    operations = []
    for rel in PROJECT_DIRS:
        path = destination / rel
        status = "exists" if path.exists() else "created"
        path.mkdir(parents=True, exist_ok=True)
        operations.append({"kind": "directory", "source": "generated", "destination": str(path), "status": status})

    for name in LEGACY_FILES:
        src = source / name
        if src.exists():
            operations.append(copy_file_no_overwrite(src, destination / "scripts_legacy" / name))
        else:
            operations.append({"kind": "file", "source": str(src), "status": "missing_source"})

    metadata_folders = sorted(p for p in source.glob("Metadata_*") if p.is_dir())
    for folder in metadata_folders:
        operations.append(copy_dir_no_overwrite(folder, destination / "data_raw"))

    historical_csvs = sorted(
        p for p in source.glob("*.csv")
        if p.name.startswith(("residential_data", "commercial_data"))
    )
    for csv in historical_csvs:
        operations.append(copy_file_no_overwrite(csv, destination / "data_derived" / "historical" / csv.name))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "destination": str(destination),
        "metadata_folders": len(metadata_folders),
        "historical_csvs": len(historical_csvs),
        "operations": operations,
    }
    manifest_path = destination / "docs" / "copy_manifest_from_python_equivalent.json"
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
