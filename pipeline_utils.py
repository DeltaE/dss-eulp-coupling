import json
import os
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent

# Run values come only from the PIPELINE_* variables that run_case.py sets.
RUN_VALUES = {
    "state": "PIPELINE_STATE",
    "season": "PIPELINE_SEASON",
    "work_root": "PIPELINE_WORK_ROOT",
    "smart_ds_root": "PIPELINE_SMART_DS_ROOT",
    "smart_ds_parquet_root": "PIPELINE_SMART_DS_PARQUET_ROOT",
    "parquet_data_root": "PIPELINE_PARQUET_ROOT",
    "max_feeders": "PIPELINE_MAX_FEEDERS",
    "feeder_registry_path": "PIPELINE_FEEDER_REGISTRY_PATH",
    "eulp_download_date": "PIPELINE_EULP_DOWNLOAD_DATE",
}


def missing_run_value(key):
    sys.exit(f"{key} is not set: {RUN_VALUES[key]} is missing. "
             f"Run the pipeline through run_case.py.")


class PipelineConfig(dict):
    """Config dict. Reading a run value whose PIPELINE_* variable is unset exits 1."""

    def __missing__(self, key):
        if key in RUN_VALUES:
            missing_run_value(key)
        raise KeyError(key)

    def get(self, key, default=None):
        if key in RUN_VALUES and key not in self:
            missing_run_value(key)
        return super().get(key, default)


def resolve_config_path(path_value):
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def resolve_work_path(*parts):
    """Join parts under the active work_root (PIPELINE_WORK_ROOT, default REPO_ROOT).
    Returns an absolute path string. Creates nothing."""
    work_root = os.environ.get("PIPELINE_WORK_ROOT", REPO_ROOT)
    return os.path.join(work_root, *parts)


def load_config(config_path=None):
    if config_path is None:
        config_path = REPO_ROOT / "pipeline_config.yaml"
    with open(config_path) as f:
        cfg = PipelineConfig(yaml.safe_load(f) or {})

    for key, var in RUN_VALUES.items():
        if os.environ.get(var):
            cfg[key] = os.environ[var]
    if "max_feeders" in cfg:
        max_feeders = cfg["max_feeders"]
        cfg["max_feeders"] = None if max_feeders.lower() in {"none", "null"} else int(max_feeders)
    return cfg


def load_feeder_registry(config_path=None):
    cfg = load_config(config_path)
    configured_path = cfg.get("feeder_registry_path", "feeder_registry.json")
    candidates = [resolve_config_path(configured_path)]

    default_path = REPO_ROOT / "feeder_registry.json"
    if default_path not in candidates:
        candidates.append(default_path)

    for registry_path in candidates:
        if registry_path.exists():
            with registry_path.open("r", encoding="utf-8") as f:
                return json.load(f)

    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(
        "feeder_registry.json not found. Run phase 2 "
        f"(copy_circuits.py) first. Searched: {searched}"
    )
