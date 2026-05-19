import os

import yaml


def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "pipeline_config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    cfg["state"] = os.environ.get("PIPELINE_STATE", cfg["state"])
    cfg["season"] = os.environ.get("PIPELINE_SEASON", cfg.get("season", "summer"))
    return cfg
