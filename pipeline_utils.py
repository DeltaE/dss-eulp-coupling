import json
import os
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent


def resolve_config_path(path_value):
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def load_config(config_path=None):
    if config_path is None:
        config_path = REPO_ROOT / "pipeline_config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}

    cfg["state"] = os.environ.get("PIPELINE_STATE", cfg["state"])
    cfg["season"] = os.environ.get("PIPELINE_SEASON", cfg.get("season", "summer"))
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
