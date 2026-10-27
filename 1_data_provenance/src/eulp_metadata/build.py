"""YAML-driven EULP / SMART-DS metadata reproduction CLI.

The implementation reads the root pipeline configuration so the
``pipeline_state`` cluster follows the active state.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "workflow.yaml"
sys.path.insert(0, str(REPO_ROOT))
from pipeline_utils import load_config as load_pipeline_config


@dataclass
class CsvSummary:
    path: str
    rows: int = 0
    columns: list[str] = field(default_factory=list)
    state_counts: Counter[str] = field(default_factory=Counter)
    upgrade_counts: Counter[str] = field(default_factory=Counter)

    @property
    def column_count(self) -> int:
        return len(self.columns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rows": self.rows,
            "column_count": self.column_count,
            "columns": self.columns,
            "state_counts": dict(sorted(self.state_counts.items())),
            "upgrade_counts": dict(sorted(self.upgrade_counts.items())),
        }


def load_workflow(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} did not load as a mapping")
    return loaded


def inject_pipeline_state_cluster(config: dict[str, Any]) -> None:
    pipeline_cfg = load_pipeline_config()
    state = pipeline_cfg["state"]
    config.setdefault("clusters", {})["pipeline_state"] = {
        "states": [state],
        "mode": "baseline_from_folders",
        "residential_folder_groups": ["residential_tmy3"],
        "commercial_folder_groups": ["commercial_amy2018"],
        "residential_upgrades": ["baseline"],
        "commercial_upgrades": ["baseline"],
        "output_residential": "residential_data_SELECT_STATES.csv",
        "output_commercial": "commercial_data_SELECT_STATES.csv",
    }


def eulp_metadata_root() -> Path:
    raw = os.environ.get("PIPELINE_EULP_METADATA_ROOT")
    if not raw:
        sys.exit(
            "PIPELINE_EULP_METADATA_ROOT is not set. run_case.py sets it from "
            "eulp_metadata_root in configs/local.yaml."
        )
    return Path(raw)


def cluster_output_dir(config: dict[str, Any], cluster_name: str) -> Path:
    outputs = Path(config["paths"]["outputs"])
    if outputs.is_absolute():
        return outputs / cluster_name
    base = Path(load_pipeline_config()["work_root"])
    return base / PROJECT_ROOT.name / outputs / cluster_name


def runs_root() -> Path:
    # run_case.py puts every workspace under runs_root and passes it as PIPELINE_RUNS_ROOT
    return Path(load_pipeline_config()["runs_root"])


def _display_path(p):
    try:
        return p.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return p.relative_to(runs_root()).as_posix()
    except ValueError:
        return p.as_posix()


def get_cluster(config: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        cluster = config["clusters"][name]
    except KeyError as exc:
        available = ", ".join(sorted(config.get("clusters", {})))
        raise SystemExit(f"Unknown cluster {name!r}. Available: {available}") from exc
    if not isinstance(cluster, dict):
        raise SystemExit(f"Cluster {name!r} must be a mapping")
    return cluster


def upgrade_matches(filename: str, labels: Iterable[str]) -> bool:
    lower = filename.lower()
    for label in labels:
        label_lower = str(label).lower()
        if label_lower == "baseline" and "baseline" in lower:
            return True
        if label_lower in lower:
            return True
    return False


def planned_files_for_dataset(
    config: dict[str, Any],
    cluster: dict[str, Any],
    dataset: str,
) -> list[dict[str, Any]]:
    data_raw = eulp_metadata_root()
    groups_key = f"{dataset}_folder_groups"
    upgrades_key = f"{dataset}_upgrades"
    group_names = cluster.get(groups_key, [])
    upgrade_labels = cluster.get(upgrades_key, [])
    states = cluster["states"]
    folder_groups = config["folder_groups"]
    files: list[dict[str, Any]] = []

    for state in states:
        for group_name in group_names:
            group = folder_groups[group_name]
            folder = data_raw / group["folder_pattern"].format(state=state)
            if not folder.exists():
                files.append(
                    {
                        "state": state,
                        "group": group_name,
                        "folder": folder.relative_to(data_raw).as_posix(),
                        "exists": False,
                        "file": None,
                    }
                )
                continue
            for csv_path in sorted(folder.glob("*.csv")):
                if upgrade_matches(csv_path.name, upgrade_labels):
                    files.append(
                        {
                            "state": state,
                            "group": group_name,
                            "folder": folder.relative_to(data_raw).as_posix(),
                            "exists": True,
                            "file": csv_path.relative_to(data_raw).as_posix(),
                        }
                    )
    return files


def plan_cluster(config: dict[str, Any], cluster_name: str) -> dict[str, Any]:
    cluster = get_cluster(config, cluster_name)
    mode = cluster["mode"]
    plan: dict[str, Any] = {
        "cluster": cluster_name,
        "mode": mode,
        "states": cluster["states"],
        "output_dir": _display_path(cluster_output_dir(config, cluster_name)),
        "outputs": {
            "residential": cluster.get("output_residential"),
            "commercial": cluster.get("output_commercial"),
        },
    }
    if mode == "baseline_from_folders":
        plan["inputs"] = {
            "residential": planned_files_for_dataset(config, cluster, "residential"),
            "commercial": planned_files_for_dataset(config, cluster, "commercial"),
        }
    else:
        raise SystemExit(f"Unsupported mode: {mode}")
    return plan


def check_cluster_inputs(config: dict[str, Any], cluster_name: str) -> dict[str, Any]:
    cluster = get_cluster(config, cluster_name)
    plan = plan_cluster(config, cluster_name)
    mode = cluster["mode"]
    result: dict[str, Any] = {
        "cluster": cluster_name,
        "mode": mode,
        "cache_status": "available",
        "inputs": {},
        "fallback": {
            "status": "not_needed",
            "message": "All required cached inputs are available.",
        },
    }

    missing: list[dict[str, Any]] = []
    if mode == "baseline_from_folders":
        for dataset in ("residential", "commercial"):
            planned = plan["inputs"][dataset]
            result["inputs"][dataset] = planned
            for item in planned:
                if not item.get("exists") or not item.get("file"):
                    missing.append({"dataset": dataset, **item})
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    if missing:
        result["cache_status"] = "missing_inputs"
        result["fallback"] = {
            "status": "see_prerequisites",
            "message": 'Some inputs are missing. See README.md, section "Prerequisites for a cold clone", then rerun this check.',
            "missing": missing,
        }
    return result


def build_cluster(config: dict[str, Any], cluster_name: str) -> dict[str, Any]:
    cluster = get_cluster(config, cluster_name)
    output_dir = cluster_output_dir(config, cluster_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = cluster["mode"]
    if mode == "baseline_from_folders":
        summaries = build_baseline_from_folders(config, cluster, output_dir)
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    manifest = {
        "cluster": cluster_name,
        "mode": mode,
        "config": DEFAULT_CONFIG.relative_to(PROJECT_ROOT).as_posix(),
        "states": cluster["states"],
        "summaries": {name: summary.to_dict() for name, summary in summaries.items()},
        "plan": plan_cluster(config, cluster_name),
    }
    write_json(output_dir / "manifest.json", manifest)
    write_row_counts(output_dir / "row_counts.csv", summaries)
    return manifest


def build_baseline_from_folders(
    config: dict[str, Any], cluster: dict[str, Any], output_dir: Path
) -> dict[str, CsvSummary]:
    outputs = {
        "residential": output_dir / cluster["output_residential"],
        "commercial": output_dir / cluster["output_commercial"],
    }
    return {
        dataset: write_folder_append_dataset(config, cluster, dataset, path)
        for dataset, path in outputs.items()
    }


def write_folder_append_dataset(
    config: dict[str, Any],
    cluster: dict[str, Any],
    dataset: str,
    output_path: Path,
) -> CsvSummary:
    configured_columns = config["columns"][f"{dataset}_append_csvs_script_v2"]
    configured_set = set(configured_columns)
    planned = [item for item in planned_files_for_dataset(config, cluster, dataset) if item["file"]]
    if not planned:
        raise SystemExit(f"No input CSVs found for {dataset}")

    summary = CsvSummary(path=_display_path(output_path))
    writer: csv.DictWriter[str] | None = None
    selected_columns: list[str] | None = None
    data_raw = eulp_metadata_root()

    with output_path.open("w", newline="", encoding="utf-8") as out_handle:
        for item in planned:
            input_path = data_raw / item["file"]
            with input_path.open("r", newline="", encoding="utf-8-sig") as in_handle:
                reader = csv.DictReader(in_handle)
                if reader.fieldnames is None:
                    raise SystemExit(f"Missing header in {input_path}")
                missing = [col for col in configured_columns if col not in reader.fieldnames]
                if missing:
                    raise SystemExit(
                        f"{input_path} is missing configured columns: {', '.join(missing[:10])}"
                    )
                if selected_columns is None:
                    selected_columns = [
                        col for col in reader.fieldnames if col in configured_set
                    ]
                    output_columns = selected_columns + ["Folder_File", "State"]
                    summary.columns = output_columns
                    writer = csv.DictWriter(out_handle, fieldnames=output_columns)
                    writer.writeheader()
                assert selected_columns is not None
                assert writer is not None
                folder_file = f"{Path(item['folder']).name}_{input_path.name}"
                state = str(item["state"])
                for row in reader:
                    out_row = {col: row.get(col, "") for col in selected_columns}
                    out_row["Folder_File"] = folder_file
                    out_row["State"] = state
                    writer.writerow(out_row)
                    update_summary(summary, out_row)
    return summary


def infer_state(row: dict[str, str]) -> str:
    if row.get("State"):
        return row["State"]
    if row.get("in.state"):
        return row["in.state"]
    folder_file = row.get("Folder_File", "")
    parts = folder_file.split("_")
    return parts[1] if len(parts) > 1 else ""


def update_summary(summary: CsvSummary, row: dict[str, str]) -> None:
    summary.rows += 1
    summary.state_counts[infer_state(row)] += 1
    summary.upgrade_counts[row.get("upgrade", "")] += 1


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def write_row_counts(path: Path, summaries: dict[str, CsvSummary]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["dataset", "rows", "column_count", "output_file"]
        )
        writer.writeheader()
        for dataset, summary in summaries.items():
            writer.writerow(
                {
                    "dataset": dataset,
                    "rows": summary.rows,
                    "column_count": summary.column_count,
                    "output_file": summary.path,
                }
            )


def print_brief_manifest(manifest: dict[str, Any]) -> None:
    print(f"Built cluster: {manifest['cluster']}")
    for dataset, summary in manifest["summaries"].items():
        print(
            f"  {dataset}: {summary['rows']} rows, "
            f"{summary['column_count']} columns -> {summary['path']}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build EULP / SMART-DS metadata CSV clusters."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to workflow YAML.")
    parser.add_argument("--cluster", help="Cluster name from config/workflow.yaml.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing outputs.")
    parser.add_argument(
        "--check-inputs",
        action="store_true",
        help="Check that the input CSVs exist under the EULP metadata root.",
    )
    parser.add_argument("--list-clusters", action="store_true", help="List configured clusters.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = load_workflow(Path(args.config))
    inject_pipeline_state_cluster(config)

    if args.list_clusters:
        for name in sorted(config.get("clusters", {})):
            print(name)
        return 0

    if not args.cluster:
        raise SystemExit("--cluster is required unless --list-clusters is used")

    if args.dry_run:
        print(json.dumps(plan_cluster(config, args.cluster), indent=2, sort_keys=True))
        return 0

    if args.check_inputs:
        check = check_cluster_inputs(config, args.cluster)
        print(json.dumps(check, indent=2, sort_keys=True))
        return 0 if check["cache_status"] == "available" else 1

    manifest = build_cluster(config, args.cluster)
    print_brief_manifest(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
