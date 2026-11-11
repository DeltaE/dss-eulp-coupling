import csv
import datetime
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


PEAK_DAY_RULES = ("per_group", "per_circuit", "given")


def peak_day_rule(cfg):
    """Return peak_day_rule from the loaded pipeline_config.yaml. A missing or unknown
    value prints [FAIL] and exits 1."""
    rule = cfg.get("peak_day_rule")
    if rule not in PEAK_DAY_RULES:
        print(f"[FAIL] peak_day_rule in pipeline_config.yaml is {rule!r}; "
              f"expected one of {', '.join(PEAK_DAY_RULES)}.")
        sys.exit(1)
    return rule


# peak_day_rule given: the caller names one day per circuit (feeder) and season in
# <settings folder>/given_days.csv. The season months are those of Phase 5b
# (find_max_day_curve_impl.py SUMMER_MONTHS, WINTER_MONTHS).
GIVEN_DAYS_FILE = "given_days.csv"
GIVEN_SEASON_MONTHS = {"summer": (6, 7, 8), "winter": (12, 1, 2)}


def read_given_days(folder):
    """{(feeder, season): (month, day)} from <folder>/given_days.csv (UTF-8, a byte order
    mark is accepted; columns Feeder, Season, Month, Day). A missing file, a wrong header,
    no data row, an empty Feeder, a Season other than summer or winter, a Month or Day
    that is not a whole number, a month and day that are not a date of a 365-day year, a
    month outside the season's months, or a (Feeder, Season) pair given twice prints
    [FAIL] with the file and the row number (header is row 1) and exits 1."""
    path = Path(folder) / GIVEN_DAYS_FILE
    where = path.as_posix()
    if not path.is_file():
        print(f"[FAIL] {where} not found.")
        sys.exit(1)
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    header = ["Feeder", "Season", "Month", "Day"]
    if not rows or rows[0] != header:
        found = ",".join(rows[0]) if rows else ""
        print(f"[FAIL] {where} row 1: header is {found!r}; expected {','.join(header)}.")
        sys.exit(1)
    days = {}
    for number, row in enumerate(rows[1:], start=2):
        if not row:
            continue

        def fail(message):
            print(f"[FAIL] {where} row {number}: {message}")
            sys.exit(1)

        if len(row) != len(header):
            fail(f"{len(row)} fields; expected {len(header)}.")
        feeder, season, month, day = (value.strip() for value in row)
        if not feeder:
            fail("Feeder is empty.")
        if season not in GIVEN_SEASON_MONTHS:
            fail(f"Season is {season!r}; expected summer or winter.")
        for name, value in (("Month", month), ("Day", day)):
            if not (value.isascii() and value.isdigit()):
                fail(f"{name} is {value!r}; expected a whole number.")
        month, day = int(month), int(day)
        try:
            datetime.date(2025, month, day)
        except ValueError:
            fail(f"month {month} and day {day} are not a date of a 365-day year.")
        if month not in GIVEN_SEASON_MONTHS[season]:
            fail(f"month {month} is not a {season} month "
                 f"({', '.join(str(m) for m in GIVEN_SEASON_MONTHS[season])}).")
        if (feeder, season) in days:
            fail(f"feeder {feeder} and season {season} are given twice.")
        days[(feeder, season)] = (month, day)
    if not days:
        print(f"[FAIL] {where} has no data row.")
        sys.exit(1)
    return days


def uses_mix_days(rule, baseline_only):
    """Whether a circuit reads its day and profiles from <work_root>/mix_days/<mix>/:
    always under peak_day_rule given, and under per_circuit for a mix that is not 100 %
    baseline."""
    return rule == "given" or (rule == "per_circuit" and not baseline_only)


EV_CONTROL_RULES = ("uncontrolled", "valley_fill_feeder", "valley_fill_transformer", "offpeak_start",
                    "water_fill_feeder")
EV_VALLEY_BASES = ("buildings_only", "after_pv")


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


EV_WORK_SHARE_CASES = ("low", "moderate", "high")


def ev_work_share_case(cfg):
    """Return ev_work_share_case from the loaded pipeline_config.yaml. A missing or
    unknown value prints [FAIL] and exits 1."""
    case = cfg.get("ev_work_share_case")
    if case not in EV_WORK_SHARE_CASES:
        print(f"[FAIL] ev_work_share_case in pipeline_config.yaml is {case!r}; "
              f"expected one of {', '.join(EV_WORK_SHARE_CASES)}.")
        sys.exit(1)
    return case


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


# Settings from a caller: run_case.py --settings <folder> sets PIPELINE_SETTINGS_DIR. The
# folder holds override files named as the repository's settings files; each holds only
# the keys it changes and is merged over the repository's file (merge_settings).
SETTINGS_ENV = "PIPELINE_SETTINGS_DIR"
SETTINGS_FILES = ("topology_registry.yaml", "donor_registry.yaml", "defaults.yaml", "local.yaml",
                  "pipeline_config.yaml")


def check_settings_dir(folder):
    """The names of the settings files in `folder`, in SETTINGS_FILES order. A missing
    folder, or a .yaml or .yml file that is not one of SETTINGS_FILES, prints [FAIL] and
    exits 1. Other files are ignored."""
    folder = Path(folder)
    if not folder.is_dir():
        print(f"[FAIL] settings folder {folder.as_posix()} does not exist or is not a folder.")
        sys.exit(1)
    for entry in sorted(folder.iterdir()):
        if not entry.name.lower().endswith((".yaml", ".yml")):
            continue
        if entry.name not in SETTINGS_FILES or not entry.is_file():
            print(f"[FAIL] settings file {entry.name} in {folder.as_posix()} is not one of "
                  f"{', '.join(SETTINGS_FILES)}.")
            sys.exit(1)
    return [name for name in SETTINGS_FILES if (folder / name).is_file()]


def read_settings_file(folder, name):
    """The override dict of <folder>/<name>: {} for an empty file, None when the file is
    absent. A file that does not load as a mapping prints [FAIL] and exits 1."""
    path = Path(folder) / name
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"[FAIL] settings file {path.as_posix()} does not load as YAML: {exc}")
        sys.exit(1)
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(f"[FAIL] settings file {path.as_posix()} does not hold a mapping of keys.")
        sys.exit(1)
    return data


def merge_settings(base, override, name, _path=()):
    """A new dict: `base` with `override` merged in. Mappings on both sides merge key by
    key; any other override value replaces the base value. A mapping against a
    non-mapping prints [FAIL] and exits 1. Strict keys: in pipeline_config.yaml every key
    path of the override must exist in the base, in defaults.yaml every top-level key;
    the registries and local.yaml take new keys at any level."""
    merged = dict(base)
    for key, value in override.items():
        path = _path + (str(key),)
        strict = name == "pipeline_config.yaml" or (name == "defaults.yaml" and not _path)
        if key not in base:
            if strict:
                print(f"[FAIL] settings {name}: key {'.'.join(path)} is not in the repository's {name}.")
                sys.exit(1)
            merged[key] = value
        elif isinstance(base[key], dict) and isinstance(value, dict):
            merged[key] = merge_settings(base[key], value, name, path)
        elif isinstance(base[key], dict) or isinstance(value, dict):
            print(f"[FAIL] settings {name}: key {'.'.join(path)} is a mapping on one side only "
                  f"(repository file or settings file).")
            sys.exit(1)
        else:
            merged[key] = value
    return merged


def settings_key_paths(override, _prefix=""):
    """The dotted key paths of the leaf values of `override`, sorted."""
    paths = []
    for key, value in override.items():
        if isinstance(value, dict) and value:
            paths.extend(settings_key_paths(value, f"{_prefix}{key}."))
        else:
            paths.append(f"{_prefix}{key}")
    return sorted(paths)


# The OEDI year folder and release whose metadata and download folders carry no release
# in their names.
EULP_CURRENT_RELEASE = {"residential": (2024, "resstock_tmy3_release_2"),
                        "commercial": (2024, "comstock_amy2018_release_1")}


def eulp_release(cfg, dataset):
    """(year, name) of the EULP release of `dataset` (residential or commercial) in
    eulp_release of pipeline_config.yaml; the year key defaults to 2024."""
    name = cfg["eulp_release"][dataset]
    year = int(cfg["eulp_release"].get(f"{dataset}_year", 2024))
    return year, name


def eulp_release_suffix(cfg, dataset):
    """The empty string for the current release of `dataset`, else _<year>_<release>."""
    year, name = eulp_release(cfg, dataset)
    if (year, name) == EULP_CURRENT_RELEASE[dataset]:
        return ""
    return f"_{year}_{name}"


def eulp_parquet_folder(cfg, dataset):
    """The Phase 5a download folder name of `dataset` under the parquet data root."""
    date, state = cfg["eulp_download_date"], cfg["state"]
    suffix = eulp_release_suffix(cfg, dataset)
    if dataset == "residential":
        return f"parquet_residential_short_{date}_{state}{suffix}"
    return f"parquet_commercial_{date}_comm_{state}{suffix}"


def load_config(config_path=None):
    settings_dir = os.environ.get(SETTINGS_ENV) if config_path is None else None
    if config_path is None:
        config_path = REPO_ROOT / "pipeline_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if settings_dir:
        check_settings_dir(settings_dir)
        override = read_settings_file(settings_dir, "pipeline_config.yaml")
        if override is not None:
            cfg = merge_settings(cfg, override, "pipeline_config.yaml")
    cfg = PipelineConfig(cfg)

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
