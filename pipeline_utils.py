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
    "runs_root": "PIPELINE_RUNS_ROOT",
    "smart_ds_root": "PIPELINE_SMART_DS_ROOT",
    "smart_ds_parquet_root": "PIPELINE_SMART_DS_PARQUET_ROOT",
    "parquet_data_root": "PIPELINE_PARQUET_ROOT",
    "max_feeders": "PIPELINE_MAX_FEEDERS",
    "feeder_registry_path": "PIPELINE_FEEDER_REGISTRY_PATH",
    "eulp_download_date": "PIPELINE_EULP_DOWNLOAD_DATE",
    "mixes_file": "PIPELINE_MIXES_FILE",
    "pv_profile_file": "PIPELINE_PV_PROFILE_FILE",
    "evwatts_extract_dir": "PIPELINE_EVWATTS_EXTRACT_DIR",
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
    """Join parts under the active work_root (PIPELINE_WORK_ROOT).
    Returns an absolute path string. Creates nothing."""
    work_root = os.environ.get("PIPELINE_WORK_ROOT")
    if not work_root:
        missing_run_value("work_root")
    return os.path.join(work_root, *parts)


def resolve_day_path(*parts):
    """Join parts under the folder that holds the files that depend on the simulated
    day: the work root, or <work_root>/mix_days/<mix>/ when PIPELINE_MIX names a mix
    (phase mix_days sets it). Returns an absolute path string. Creates nothing."""
    mix = os.environ.get("PIPELINE_MIX")
    if mix:
        return resolve_work_path("mix_days", mix, *parts)
    return resolve_work_path(*parts)


def load_mixes(path):
    """Return the mixes of the mixes file at path, a dict keyed by mix name in file
    order. Reads .yaml and .yml with yaml.safe_load and .json with json.load. Any other
    extension prints [FAIL] and exits 1."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".yaml", ".yml", ".json"):
        print(f"[FAIL] mixes file {path} has extension {suffix!r}; expected .yaml, .yml or .json.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f) if suffix == ".json" else yaml.safe_load(f)


PEAK_DAY_RULES = ("per_group", "per_circuit")


def peak_day_rule(cfg):
    """Return peak_day_rule from the loaded pipeline_config.yaml. A missing or unknown
    value prints [FAIL] and exits 1."""
    rule = cfg.get("peak_day_rule")
    if rule not in PEAK_DAY_RULES:
        print(f"[FAIL] peak_day_rule in pipeline_config.yaml is {rule!r}; "
              f"expected one of {', '.join(PEAK_DAY_RULES)}.")
        sys.exit(1)
    return rule


EV_CONTROL_RULES = ("uncontrolled", "valley_fill_feeder", "valley_fill_transformer", "offpeak_start",
                    "water_fill_feeder")
EV_VALLEY_BASES = ("buildings_only", "after_pv_storage")


def ev_control(cfg):
    """Return ev_control from the loaded pipeline_config.yaml. A missing or unknown
    value prints [FAIL] and exits 1."""
    rule = cfg.get("ev_control")
    if rule not in EV_CONTROL_RULES:
        print(f"[FAIL] ev_control in pipeline_config.yaml is {rule!r}; "
              f"expected one of {', '.join(EV_CONTROL_RULES)}.")
        sys.exit(1)
    return rule


def ev_valley_base(cfg):
    """Return ev_valley_base from the loaded pipeline_config.yaml. A missing or unknown
    value prints [FAIL] and exits 1."""
    base = cfg.get("ev_valley_base")
    if base not in EV_VALLEY_BASES:
        print(f"[FAIL] ev_valley_base in pipeline_config.yaml is {base!r}; "
              f"expected one of {', '.join(EV_VALLEY_BASES)}.")
        sys.exit(1)
    return base


EV_CARS_SOURCES = ("evwatts_sessions", "nhts_days", "session_rows")


def ev_cars(cfg):
    """Return ev_cars from the loaded pipeline_config.yaml. A missing or unknown value
    prints [FAIL] and exits 1."""
    source = cfg.get("ev_cars")
    if source not in EV_CARS_SOURCES:
        print(f"[FAIL] ev_cars in pipeline_config.yaml is {source!r}; "
              f"expected one of {', '.join(EV_CARS_SOURCES)}.")
        sys.exit(1)
    return source


EV_DAYS = ("typical", "stress")


def ev_day(cfg):
    """Return ev_day from the loaded pipeline_config.yaml. A missing or unknown value
    prints [FAIL] and exits 1."""
    day = cfg.get("ev_day")
    if day not in EV_DAYS:
        print(f"[FAIL] ev_day in pipeline_config.yaml is {day!r}; "
              f"expected one of {', '.join(EV_DAYS)}.")
        sys.exit(1)
    return day


HEATING_LABEL_UNITS = ("building", "customer")


def heating_label_unit(cfg):
    """Return heating_label_unit from the loaded pipeline_config.yaml. A missing or
    unknown value prints [FAIL] and exits 1."""
    unit = cfg.get("heating_label_unit")
    if unit not in HEATING_LABEL_UNITS:
        print(f"[FAIL] heating_label_unit in pipeline_config.yaml is {unit!r}; "
              f"expected one of {', '.join(HEATING_LABEL_UNITS)}.")
        sys.exit(1)
    return unit


def ev_home_window(cfg):
    """Return ev_home_window from the loaded pipeline_config.yaml. A missing or
    non-boolean value prints [FAIL] and exits 1."""
    value = cfg.get("ev_home_window")
    if not isinstance(value, bool):
        print(f"[FAIL] ev_home_window in pipeline_config.yaml is {value!r}; expected true or false.")
        sys.exit(1)
    return value


def resolve_dss_file(directory, filename):
    """Case-insensitive file lookup within `directory`. ext4 is genuinely
    case-sensitive (unlike the Windows machines SMART-DS exports were
    authored on), so a hardcoded-case path can silently miss a file that is
    actually present under a different case. Returns a Path; raises
    FileNotFoundError with a clear message if no case-insensitive match exists."""
    directory = Path(directory)
    exact = directory / filename
    if exact.exists():
        return exact
    target = filename.lower()
    for entry in directory.iterdir():
        if entry.is_file() and entry.name.lower() == target:
            return entry
    raise FileNotFoundError(f"{filename} not found in {directory} (case-insensitive search)")


def load_config(config_path=None):
    if config_path is None:
        config_path = REPO_ROOT / "pipeline_config.yaml"
    with open(config_path, encoding="utf-8") as f:
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
    registry_path = resolve_config_path(cfg["feeder_registry_path"])
    if registry_path.exists():
        with registry_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(
        "feeder_registry.json not found. Run phase 2 "
        f"(copy_circuits.py) first. Searched: {registry_path}"
    )
