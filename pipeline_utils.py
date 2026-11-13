import ast
import calendar
import csv
import datetime
import json
import math
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


def uses_mix_days(rule, baseline_only, growth=False):
    """Whether a circuit reads its day and profiles from <work_root>/mix_days/<mix>/:
    always under peak_day_rule given, and under per_circuit for a mix that is not 100 %
    baseline. With growth on (growth_years above 0 in growth.yaml) every mix under
    per_circuit does, 100 % baseline included, because its day is the peak day of the
    grown curve."""
    return rule == "given" or (rule == "per_circuit" and (growth or not baseline_only))


# The multi-day window (horizon_days in pipeline_config.yaml): horizon_days consecutive
# days around the simulated peak day, day X, solved as one run of STEPS_PER_DAY x
# horizon_days steps. horizon_days 1 is day X alone.
STEPS_PER_DAY = 96  # 15-minute steps in one day


def horizon_days(cfg):
    """Return horizon_days from the loaded pipeline_config.yaml as an int. A missing
    value, a value that is not a whole number or a value below 1 prints [FAIL] and
    exits 1."""
    days = cfg.get("horizon_days")
    if isinstance(days, float) and days.is_integer():
        days = int(days)
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        print(f"[FAIL] horizon_days in pipeline_config.yaml is {days!r}; "
              f"expected a whole number of days, 1 or above.")
        sys.exit(1)
    return days


# The script whose constants WINTER_MONTHS and SUMMER_MONTHS are the season months of
# the pipeline. It runs on import, so season_months reads the constants from its text.
PHASE5B_SCRIPT = REPO_ROOT / "5b_profile_generation" / "find_max_day_curve_impl.py"


def season_months(path=None):
    """{"winter": [months], "summer": [months]}: the Phase 5b constants WINTER_MONTHS and
    SUMMER_MONTHS, read from the text of find_max_day_curve_impl.py (path, when given,
    names another script that assigns the two constants). A script without both
    constants prints [FAIL] and exits 1."""
    path = Path(path) if path else PHASE5B_SCRIPT
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("WINTER_MONTHS", "SUMMER_MONTHS")):
            found[node.targets[0].id] = [int(m) for m in ast.literal_eval(node.value)]
    if set(found) != {"WINTER_MONTHS", "SUMMER_MONTHS"}:
        print(f"[FAIL] WINTER_MONTHS and SUMMER_MONTHS are not both assigned in {path.as_posix()}.")
        sys.exit(1)
    return {"winter": found["WINTER_MONTHS"], "summer": found["SUMMER_MONTHS"]}


# The calendar year of the building curves: the timestamps of the EULP releases of
# eulp_release (ComStock AMY 2018, and ResStock TMY3 stamped on the same year) and of
# the SMART-DS load and solar files are those of 2018. Window days take their weekday
# from this calendar; Phase 5b stops when the rows it cuts carry another year.
WINDOW_YEAR = 2018
# The U.S. federal holidays of WINDOW_YEAR, (month, day): name. U.S. Office of Personnel
# Management, Federal Holidays, 2018:
# https://opm.gov/policy-data-oversight/snow-dismissal-procedures/federal-holidays
# A holiday keeps the day type of its weekday; window_days.csv names it.
FEDERAL_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (1, 15): "Birthday of Martin Luther King, Jr.",
    (2, 19): "Washington's Birthday",
    (5, 28): "Memorial Day",
    (7, 4): "Independence Day",
    (9, 3): "Labor Day",
    (10, 8): "Columbus Day",
    (11, 12): "Veterans Day (observed)",
    (11, 22): "Thanksgiving Day",
    (12, 25): "Christmas Day",
}


def season_stretches(months):
    """The stretches of WINDOW_YEAR that hold months: each run of consecutive months, as
    (first date, last date). December and January are never joined, so a window never
    crosses 31 December."""
    runs = []
    for month in sorted(set(int(m) for m in months)):
        if runs and month == runs[-1][-1] + 1:
            runs[-1].append(month)
        else:
            runs.append([month])
    return [(datetime.date(WINDOW_YEAR, run[0], 1),
             datetime.date(WINDOW_YEAR, run[-1], calendar.monthrange(WINDOW_YEAR, run[-1])[1]))
            for run in runs]


def window_dates(month, day, season, days):
    """(dates, x): the days consecutive dates of WINDOW_YEAR of the window around day X
    (month, day) of season, and the position x of day X in the list (0 for the first
    date). Day X sits at position ceil(days / 2) counted from 1: X-3 to X+3 for 7 days,
    X-6 to X+7 for 14 days. The window is shifted to stay inside the stretch of the
    season that holds day X (season_stretches of the Phase 5b season months): summer 1
    June to 31 August; winter 1 January to 28 February, or 1 to 31 December. days 1
    returns day X alone. A season without months, a day X outside the season's months
    or a window longer than its stretch prints [FAIL] and exits 1."""
    x_date = datetime.date(WINDOW_YEAR, int(month), int(day))
    if days == 1:
        return [x_date], 0
    months = season_months().get(season)
    if not months:
        print(f"[FAIL] window_dates: no season months for season {season!r}.")
        sys.exit(1)
    stretch = next((s for s in season_stretches(months) if s[0] <= x_date <= s[1]), None)
    if stretch is None:
        print(f"[FAIL] window_dates: day X {int(month):02d}-{int(day):02d} is not in a {season} month "
              f"({', '.join(str(m) for m in months)}).")
        sys.exit(1)
    length = (stretch[1] - stretch[0]).days + 1
    if days > length:
        print(f"[FAIL] window_dates: a window of {days} days does not fit the {length} days from "
              f"{stretch[0].isoformat()} to {stretch[1].isoformat()} that hold day X "
              f"{int(month):02d}-{int(day):02d}.")
        sys.exit(1)
    start = x_date - datetime.timedelta(days=math.ceil(days / 2) - 1)
    start = min(max(start, stretch[0]), stretch[1] - datetime.timedelta(days=days - 1))
    dates = [start + datetime.timedelta(days=i) for i in range(days)]
    return dates, (x_date - start).days


def day_type(date):
    """weekend for a Saturday or Sunday, else weekday."""
    return "weekend" if date.weekday() >= 5 else "weekday"


WINDOW_DAYS_FILE = "window_days.csv"
WINDOW_DAYS_COLUMNS = ["date", "weekday", "day_type", "day_index", "day_x", "holiday"]


def window_day_rows(dates, x):
    """The rows of window_days.csv for the window dates and the position x of day X: date
    (YYYY-MM-DD), weekday (Monday to Sunday), day_type (weekday or weekend, from the date
    on the WINDOW_YEAR calendar), day_index (1 for the first day), day_x (1 on day X,
    else 0) and holiday (the FEDERAL_HOLIDAYS name, else empty)."""
    return [{"date": d.isoformat(), "weekday": calendar.day_name[d.weekday()], "day_type": day_type(d),
             "day_index": i + 1, "day_x": 1 if i == x else 0,
             "holiday": FEDERAL_HOLIDAYS.get((d.month, d.day), "")}
            for i, d in enumerate(dates)]


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


EV_VALLEY_DAYS = ("own_day", "peak_day")


def ev_valley_day(cfg):
    """Return ev_valley_day from the loaded pipeline_config.yaml. A missing or unknown
    value prints [FAIL] and exits 1."""
    day = cfg.get("ev_valley_day")
    if day not in EV_VALLEY_DAYS:
        print(f"[FAIL] ev_valley_day in pipeline_config.yaml is {day!r}; "
              f"expected one of {', '.join(EV_VALLEY_DAYS)}.")
        sys.exit(1)
    return day


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
                  "pipeline_config.yaml", "growth.yaml")


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
    the registries and local.yaml take new keys at any level. growth.yaml is strict as
    pipeline_config.yaml, except under the maps of GROWTH_OPEN_MAPS, which take new keys."""
    merged = dict(base)
    for key, value in override.items():
        path = _path + (str(key),)
        strict = name == "pipeline_config.yaml" or (name == "defaults.yaml" and not _path) \
            or (name == GROWTH_FILE and not (_path and _path[0] in GROWTH_OPEN_MAPS))
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


# Load growth over planning years: configs/growth.yaml, with the growth.yaml of the
# --settings folder merged over it. growth_years 0 is growth off. Phase growth
# (growth_plan.py) writes the plan of a run with growth on to
# <work_root>/growth/growth_plan.json; the later phases read it (read_growth_plan).
GROWTH_FILE = "growth.yaml"
GROWTH_OPEN_MAPS = ("infill_share_metro", "block_attach_buses")
GROWTH_CASES = ("low", "moderate", "high")
GROWTH_RATES = ("households", "use_per_household", "floorspace", "use_per_ft2")
GROWTH_COMPANIONS = ("feeder", "national", "aeo")
GROWTH_NAMED_BUS = ("seeded", "strongest", "weakest")
GROWTH_LIMITS = ("line_limit_percent", "head_limit_percent", "transformer_limit_percent",
                 "substation_limit_percent")
GROWTH_PLAN_DIR = "growth"
GROWTH_PLAN_FILE = "growth_plan.json"


def _growth_fail(key, value, expected):
    print(f"[FAIL] growth.yaml: {key} is {value!r}; expected {expected}.")
    sys.exit(1)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _whole(value):
    """value as an int when it is a whole number (7.0 is 7), else None."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def load_growth(settings_dir=None):
    """The merged growth settings, unchecked: configs/growth.yaml with the growth.yaml of
    settings_dir merged over it (merge_settings: strict keys, the maps of GROWTH_OPEN_MAPS
    take new keys, a list replaces a list). settings_dir None takes PIPELINE_SETTINGS_DIR."""
    with open(REPO_ROOT / "configs" / GROWTH_FILE, encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    if settings_dir is None:
        settings_dir = os.environ.get(SETTINGS_ENV)
    if settings_dir:
        override = read_settings_file(settings_dir, GROWTH_FILE)
        if override is not None:
            merged = merge_settings(merged, override, GROWTH_FILE)
    return merged


def _growth_band(key, value):
    if not (isinstance(value, list) and len(value) == 2 and all(_number(v) for v in value)
            and 0 < value[0] < value[1]):
        _growth_fail(key, value, "[low, high] in per unit, low below high")


def growth_settings(raw, topology_id=None):
    """Check the merged growth settings raw (load_growth) and return them with
    growth_years as an int. Any bad value prints one [FAIL] line that names the key, the
    value and the accepted values, and exits 1. With topology_id, infill_share metro
    also needs that topology in infill_share_metro."""
    g = dict(raw)
    years = _whole(g.get("growth_years"))
    if years is None or years < 0:
        _growth_fail("growth_years", g.get("growth_years"), "a whole number of years, 0 or above")
    g["growth_years"] = years
    if g.get("case") not in GROWTH_CASES:
        _growth_fail("case", g.get("case"), "one of " + ", ".join(GROWTH_CASES))
    for name in GROWTH_RATES:
        cases = (g.get("rate_cases") or {}).get(name)
        for case in GROWTH_CASES:
            value = cases.get(case) if isinstance(cases, dict) else None
            if not _number(value) or value <= -100:
                _growth_fail(f"rate_cases.{name}.{case}", value, "a number, percent a year, above -100")
        value = (g.get("rates") or {}).get(name)
        if value is not None and (not _number(value) or value <= -100):
            _growth_fail(f"rates.{name}", value, "null or a number, percent a year, above -100")
    share = g.get("infill_share")
    if share not in ("metro", "national") and not (_number(share) and 0 <= share <= 1):
        _growth_fail("infill_share", share, "metro, national or a number from 0 to 1")
    metro = g.get("infill_share_metro")
    if not isinstance(metro, dict):
        _growth_fail("infill_share_metro", metro, "a map of topology_id to a number from 0 to 1")
    for key, value in metro.items():
        if not (_number(value) and 0 <= value <= 1):
            _growth_fail(f"infill_share_metro.{key}", value, "a number from 0 to 1")
    if share == "metro" and topology_id is not None and topology_id not in metro:
        _growth_fail("infill_share", share, f"a value for topology {topology_id} in infill_share_metro "
                     f"(it holds {', '.join(str(k) for k in metro) or 'no topology'}), or national, "
                     f"or a number from 0 to 1")
    value = g.get("infill_share_national")
    if not (_number(value) and 0 <= value <= 1):
        _growth_fail("infill_share_national", value, "a number from 0 to 1")
    if g.get("companions") not in GROWTH_COMPANIONS:
        _growth_fail("companions", g.get("companions"), "one of " + ", ".join(GROWTH_COMPANIONS))
    for key in ("commercial_buildings_million", "households_million"):
        value = (g.get("companions_national") or {}).get(key)
        if not _number(value) or value <= 0:
            _growth_fail(f"companions_national.{key}", value, "a number above 0")
    value = g.get("companion_excluded_types")
    if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
        _growth_fail("companion_excluded_types", value, "a list of ComStock building types")
    attach = g.get("block_attach_buses")
    if not isinstance(attach, dict):
        _growth_fail("block_attach_buses", attach, "a map of feeder name to a list of buses")
    for key, value in attach.items():
        if not (isinstance(value, list) and all(isinstance(v, str) and v for v in value)):
            _growth_fail(f"block_attach_buses.{key}", value, "a list of bus names")
    named = g.get("named_loads")
    if not isinstance(named, list):
        _growth_fail("named_loads", named, "a list of {feeder, type, count, year, bus}")
    for i, entry in enumerate(named):
        key = f"named_loads[{i}]"
        if not isinstance(entry, dict) or set(entry) - {"feeder", "type", "count", "year", "bus"}:
            _growth_fail(key, entry, "a map with the keys feeder, type, count, year and, optional, bus")
        for field in ("feeder", "type"):
            if not (isinstance(entry.get(field), str) and entry[field]):
                _growth_fail(f"{key}.{field}", entry.get(field), "a name")
        if _whole(entry.get("count")) is None or _whole(entry["count"]) < 1:
            _growth_fail(f"{key}.count", entry.get("count"), "a whole number, 1 or above")
        if _whole(entry.get("year")) is None or _whole(entry["year"]) < 0:
            _growth_fail(f"{key}.year", entry.get("year"), "a whole number of years, 0 or above")
        if "bus" in entry and not (isinstance(entry["bus"], str) and entry["bus"]):
            _growth_fail(f"{key}.bus", entry["bus"], "a bus name, or no bus key")
    if g.get("named_load_bus") not in GROWTH_NAMED_BUS:
        _growth_fail("named_load_bus", g.get("named_load_bus"), "one of " + ", ".join(GROWTH_NAMED_BUS))
    factors = g.get("load_factors")
    if not isinstance(factors, list):
        _growth_fail("load_factors", factors, "a list of {feeder, load, factor, peak_factor}")
    for i, entry in enumerate(factors):
        key = f"load_factors[{i}]"
        if not isinstance(entry, dict) or set(entry) - {"feeder", "load", "factor", "peak_factor"}:
            _growth_fail(key, entry, "a map with the keys feeder, load, factor and, optional, peak_factor")
        for field in ("feeder", "load"):
            if not (isinstance(entry.get(field), str) and entry[field]):
                _growth_fail(f"{key}.{field}", entry.get(field), "a name")
        if not _number(entry.get("factor")) or entry["factor"] <= 0:
            _growth_fail(f"{key}.factor", entry.get("factor"), "a number above 0")
        if "peak_factor" in entry and (not _number(entry["peak_factor"]) or entry["peak_factor"] <= 0):
            _growth_fail(f"{key}.peak_factor", entry["peak_factor"], "a number above 0, or no peak_factor key")
    limits = g.get("planning_limits")
    if not isinstance(limits, dict):
        _growth_fail("planning_limits", limits, "a map")
    bands = limits.get("voltage_bands")
    if not isinstance(bands, dict):
        _growth_fail("planning_limits.voltage_bands", bands, "a map with range_a and range_b")
    for name in ("range_a", "range_b"):
        _growth_band(f"planning_limits.voltage_bands.{name}", bands.get(name))
    band = limits.get("voltage_band")
    if band not in ("repository", "range_a", "range_b"):
        if isinstance(band, list):
            _growth_band("planning_limits.voltage_band", band)
        else:
            _growth_fail("planning_limits.voltage_band", band,
                         "repository, range_a, range_b or [low, high] in per unit")
    for name in GROWTH_LIMITS:
        if not _number(limits.get(name)) or limits[name] <= 0:
            _growth_fail(f"planning_limits.{name}", limits.get(name), "a number of percent above 0")
    # off without quotes loads as a boolean in YAML: the value is read as text
    mode = (g.get("network_growth") or {}).get("mode") if isinstance(g.get("network_growth"), dict) else None
    if not (isinstance(mode, str) and mode == "off"):
        _growth_fail("network_growth.mode", mode, 'the text "off", in quotes (no other mode exists yet)')
    return g


def growth_on(g):
    """True when the checked growth settings g ask for growth (growth_years above 0)."""
    return g["growth_years"] > 0


def growth_rates(g):
    """{rate name: percent a year}: the rates of the case, each replaced by its value in
    rates when that is a number."""
    return {name: g["rates"][name] if g["rates"].get(name) is not None else g["rate_cases"][name][g["case"]]
            for name in GROWTH_RATES}


def growth_infill_share(g, topology_id):
    """The infill share as a number: infill_share itself, infill_share_national, or the
    value of topology_id in infill_share_metro."""
    share = g["infill_share"]
    if share == "national":
        return float(g["infill_share_national"])
    if share == "metro":
        if topology_id not in g["infill_share_metro"]:
            _growth_fail("infill_share", share, f"a value for topology {topology_id} in infill_share_metro")
        return float(g["infill_share_metro"][topology_id])
    return float(share)


def planning_band(g, cfg):
    """(low, high) per unit of planning_limits.voltage_band: voltage_band of
    pipeline_config.yaml for repository, a named band of voltage_bands, or the two given
    values."""
    band = g["planning_limits"]["voltage_band"]
    if band == "repository":
        return float(cfg["voltage_band"]["low_pu"]), float(cfg["voltage_band"]["high_pu"])
    if isinstance(band, str):
        band = g["planning_limits"]["voltage_bands"][band]
    return float(band[0]), float(band[1])


def read_growth_plan(g, phase):
    """The plan of phase growth, <work_root>/growth/growth_plan.json, for a run with
    growth on. Stops with [FAIL] when the file is missing, or when the settings it
    records differ from the merged growth settings of this call (the plan belongs to
    other settings: phase growth has to run again)."""
    path = resolve_work_path(GROWTH_PLAN_DIR, GROWTH_PLAN_FILE)
    if not os.path.isfile(path):
        print(f"[FAIL] {phase}: growth_years is {g['growth_years']} but {path} is missing. "
              f"Run phase growth first (it sits between 4 and 5a in phase_order).")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        plan = json.load(f)
    if plan.get("settings") != json.loads(json.dumps(g)):
        print(f"[FAIL] {phase}: the growth settings of this run differ from those recorded in {path}. "
              f"Run phase growth again with these settings.")
        sys.exit(1)
    return plan


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
