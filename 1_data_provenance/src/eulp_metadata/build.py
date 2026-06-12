"""YAML-driven EULP / SMART-DS metadata reproduction CLI.

The implementation reads the root pipeline configuration so the
``pipeline_state`` cluster follows the active state.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


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
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} did not load as a mapping")
        return loaded
    except ImportError:
        return parse_yaml_subset(text)


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
        "validation_historical_residential": f"residential_data_SELECT_STATES_{state}.csv",
        "validation_historical_commercial": f"commercial_data_SELECT_STATES_{state}.csv",
    }


def parse_yaml_subset(text: str) -> dict[str, Any]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped_comment = strip_yaml_comment(raw).rstrip()
        if not stripped_comment.strip():
            continue
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        lines.append((indent, stripped_comment.strip()))

    if not lines:
        return {}

    parsed, index = parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("Could not parse complete YAML file")
    if not isinstance(parsed, dict):
        raise ValueError("Top-level YAML must be a mapping")
    return parsed


def strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return line[:index]
    return line


def parse_block(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_text.startswith("- "):
        return parse_list(lines, index, current_indent)
    return parse_dict(lines, index, current_indent)


def parse_dict(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Unexpected indentation near: {text}")
        if text.startswith("- "):
            break
        if ":" not in text:
            raise ValueError(f"Expected key/value line, got: {text}")
        key, raw_value = text.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            result[key] = parse_scalar(raw_value)
            index += 1
        else:
            child, index = parse_block(lines, index + 1, indent + 2)
            result[key] = child
    return result, index


def parse_list(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Unexpected indentation near: {text}")
        if not text.startswith("- "):
            break
        item = text[2:].strip()
        if item:
            result.append(parse_scalar(item))
            index += 1
        else:
            child, index = parse_block(lines, index + 1, indent + 2)
            result.append(child)
    return result, index


def parse_scalar(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lower = value.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    if lower in {"null", "none"}:
        return None
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def project_path(config: dict[str, Any], key: str) -> Path:
    raw = config["paths"][key]
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def cluster_output_dir(config: dict[str, Any], cluster_name: str) -> Path:
    return project_path(config, "outputs") / cluster_name


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
    data_raw = project_path(config, "data_raw")
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
                        "folder": str(folder.relative_to(PROJECT_ROOT)),
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
                            "folder": str(folder.relative_to(PROJECT_ROOT)),
                            "exists": True,
                            "file": str(csv_path.relative_to(PROJECT_ROOT)),
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
        "output_dir": str(cluster_output_dir(config, cluster_name).relative_to(PROJECT_ROOT)),
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
    elif mode == "historical_slice":
        historical = project_path(config, "historical_data")
        plan["inputs"] = {
            "residential": str(
                (historical / cluster["historical_residential"]).relative_to(PROJECT_ROOT)
            ),
            "commercial": str(
                (historical / cluster["historical_commercial"]).relative_to(PROJECT_ROOT)
            ),
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
        "download_policy": config.get("download_stage", {}).get(
            "policy", "cache_first_fallback_only"
        ),
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
    elif mode == "historical_slice":
        for dataset in ("residential", "commercial"):
            rel_path = plan["inputs"][dataset]
            exists = (PROJECT_ROOT / rel_path).exists()
            result["inputs"][dataset] = {"file": rel_path, "exists": exists}
            if not exists:
                missing.append({"dataset": dataset, "file": rel_path, "exists": False})
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    if missing:
        result["cache_status"] = "missing_inputs"
        result["fallback"] = {
            "status": "use_download_stage",
            "message": "Some cached inputs are missing. Use the recovered download-stage recipes in config/workflow.yaml, then rerun this check.",
            "download_stage": config.get("download_stage", {}),
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
    elif mode == "historical_slice":
        summaries = build_historical_slice(config, cluster, output_dir)
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    manifest = {
        "cluster": cluster_name,
        "mode": mode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(DEFAULT_CONFIG.relative_to(PROJECT_ROOT)),
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

    summary = CsvSummary(path=str(output_path.relative_to(PROJECT_ROOT)))
    writer: csv.DictWriter[str] | None = None
    selected_columns: list[str] | None = None

    with output_path.open("w", newline="", encoding="utf-8") as out_handle:
        for item in planned:
            input_path = PROJECT_ROOT / item["file"]
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


def build_historical_slice(
    config: dict[str, Any], cluster: dict[str, Any], output_dir: Path
) -> dict[str, CsvSummary]:
    historical = project_path(config, "historical_data")
    jobs = {
        "residential": (
            historical / cluster["historical_residential"],
            output_dir / cluster["output_residential"],
        ),
        "commercial": (
            historical / cluster["historical_commercial"],
            output_dir / cluster["output_commercial"],
        ),
    }
    states = set(cluster["states"])
    return {
        dataset: write_historical_slice(input_path, output_path, states)
        for dataset, (input_path, output_path) in jobs.items()
    }


def write_historical_slice(
    input_path: Path, output_path: Path, states: set[str]
) -> CsvSummary:
    summary = CsvSummary(path=str(output_path.relative_to(PROJECT_ROOT)))
    with input_path.open("r", newline="", encoding="utf-8-sig") as in_handle:
        reader = csv.DictReader(in_handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Missing header in {input_path}")
        output_columns = list(reader.fieldnames)
        if "State" not in output_columns:
            output_columns.append("State")
        summary.columns = output_columns
        with output_path.open("w", newline="", encoding="utf-8") as out_handle:
            writer = csv.DictWriter(out_handle, fieldnames=output_columns)
            writer.writeheader()
            for row in reader:
                state = infer_state(row)
                if state not in states:
                    continue
                row["State"] = state
                writer.writerow({col: row.get(col, "") for col in output_columns})
                update_summary(summary, row)
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


def count_csv(path: Path) -> CsvSummary:
    summary = CsvSummary(path=str(path.relative_to(PROJECT_ROOT)))
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit(f"Missing header in {path}")
        summary.columns = list(reader.fieldnames)
        for row in reader:
            update_summary(summary, row)
    return summary


def validate_cluster(config: dict[str, Any], cluster_name: str) -> dict[str, Any]:
    cluster = get_cluster(config, cluster_name)
    output_dir = cluster_output_dir(config, cluster_name)
    historical_dir = project_path(config, "historical_data")
    comparisons: dict[str, Any] = {}

    for dataset in ("residential", "commercial"):
        generated_name = cluster[f"output_{dataset}"]
        historical_name = cluster.get(f"validation_historical_{dataset}", generated_name)
        generated_path = output_dir / generated_name
        historical_path = historical_dir / historical_name
        if not generated_path.exists():
            raise SystemExit(f"Generated output not found: {generated_path}")
        if not historical_path.exists():
            raise SystemExit(f"Historical comparison file not found: {historical_path}")
        generated = count_csv(generated_path)
        historical = count_csv(historical_path)
        comparisons[dataset] = compare_summaries(generated, historical)

    report = {
        "cluster": cluster_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparisons": comparisons,
        "passed": all(item["passed"] for item in comparisons.values()),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "validation_report.json", report)
    write_validation_summary(output_dir / "validation_summary.csv", report)
    return report


def compare_summaries(generated: CsvSummary, historical: CsvSummary) -> dict[str, Any]:
    checks = {
        "row_count": generated.rows == historical.rows,
        "column_count": generated.column_count == historical.column_count,
        "column_names": generated.columns == historical.columns,
        "state_counts": generated.state_counts == historical.state_counts,
        "upgrade_counts": generated.upgrade_counts == historical.upgrade_counts,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "generated": generated.to_dict(),
        "historical": historical.to_dict(),
    }


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


def write_validation_summary(path: Path, report: dict[str, Any]) -> None:
    rows = []
    for dataset, comparison in report["comparisons"].items():
        for check, passed in comparison["checks"].items():
            rows.append({"dataset": dataset, "check": check, "passed": passed})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dataset", "check", "passed"])
        writer.writeheader()
        writer.writerows(rows)


def print_brief_manifest(manifest: dict[str, Any]) -> None:
    print(f"Built cluster: {manifest['cluster']}")
    for dataset, summary in manifest["summaries"].items():
        print(
            f"  {dataset}: {summary['rows']} rows, "
            f"{summary['column_count']} columns -> {summary['path']}"
        )


def print_brief_validation(report: dict[str, Any]) -> None:
    status = "passed" if report["passed"] else "failed"
    print(f"Validation {status}: {report['cluster']}")
    for dataset, comparison in report["comparisons"].items():
        failed = [
            name for name, passed in comparison["checks"].items() if not passed
        ]
        detail = "all checks passed" if not failed else "failed: " + ", ".join(failed)
        print(f"  {dataset}: {detail}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and validate EULP / SMART-DS metadata CSV clusters."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to workflow YAML.")
    parser.add_argument("--cluster", help="Cluster name from config/workflow.yaml.")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing outputs.")
    parser.add_argument(
        "--check-inputs",
        action="store_true",
        help="Check cached local inputs and report whether download fallback is needed.",
    )
    parser.add_argument("--validate", action="store_true", help="Validate outputs after building.")
    parser.add_argument("--validate-only", action="store_true", help="Validate existing outputs without building.")
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

    if args.validate_only:
        report = validate_cluster(config, args.cluster)
        print_brief_validation(report)
        return 0 if report["passed"] else 1

    manifest = build_cluster(config, args.cluster)
    print_brief_manifest(manifest)

    if args.validate:
        report = validate_cluster(config, args.cluster)
        print_brief_validation(report)
        return 0 if report["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
