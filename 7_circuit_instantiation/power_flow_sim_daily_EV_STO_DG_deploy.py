# -*- coding: utf-8 -*-
"""
power_flow_sim_daily_EV_STO_DG_deploy.py
----------------------------------------
Build and solve one DER scenario of one prepared circuit as a 96-step daily run.

Run from inside a prepared circuit folder <circuit>/ (run_circuits.py starts it with
cwd set to that folder). instantiate_circuits.py copies this script there and rewrites
ROOT so that deployer_modules/ and pipeline_config.yaml are found in the repository.

Inputs
- <circuit>/<feeder>/: the first subfolder other than ModifiedCircuitData that holds
  Loads.dss, LoadShapes.dss and Master.dss. Loads.dss gives load names, buses, kV,
  phases, conn and daily shapes; Loads_original.dss gives the original kW.
- <circuit>/scenario_assignments.json: ev.lvl2_perc, ev.effective_seed,
  ev_loads_uncontrolled, ev_loads_controlled (or ev_loads, split in half when both are
  empty), storage_targets, pv_targets, season.
- <circuit>/data_ev/: two Team-Nando EV charging profiles; under ev_cars session_rows
  the check curve of ev_inputs.yaml (pfs_ev_base_profiles).
- ev_cars and ev_home_window in pipeline_config.yaml: the source of the EV cars and
  whether controlled charging stays inside each car's plug-in window at home.
- <repo>/7_circuit_instantiation/data_ev_cars/ev_inputs.yaml (typical values) and,
  under nhts_days and session_rows, <STATE>_nhts2017_vehicle_days.csv there.
- Under ev_cars evwatts_sessions and session_rows: PIPELINE_EVWATTS_EXTRACT_DIR
  (evwatts_extract_dir in configs/local.yaml), the folder of
  evwatts_residential_l2_weekday.csv (build_evwatts_extract.py).
- <circuit>/../profiles_use_bench/<circuit>/<daily>.csv: one-column kW profiles, used
  for storage and PV sizing.
- der_sizing in pipeline_config.yaml: storage and PV ratios and minimums.
- <work_root>/5b_profile_generation/<STATE>_peak_days.csv: each feeder's baseline
  winter and summer peak day (Phase 5b).
- With peak_day_rule: per_circuit in pipeline_config.yaml, for a circuit whose mix is
  not 100 % baseline: <work_root>/mix_days/<STATE>_circuit_days.csv, the circuit's own
  peak day per feeder, season and mix (phase mix_days), and the mix's shares in
  <work_root>/7_circuit_instantiation/mixes.json. The mix is the part of the circuit
  folder name after _circuit_<n>_.
- PIPELINE_PV_PROFILE_FILE: the donor's SMART-DS solar file (pv_profile in
  configs/donor_registry.yaml).
- voltage_band in pipeline_config.yaml: low_pu and high_pu for the load voltage
  summaries.
- ev_control and ev_valley_base in pipeline_config.yaml: the rule for controlled EVs
  and what the no-EV base solve of the valley rules holds.
- Under ev_control offpeak_start: <repo>/7_circuit_instantiation/data_tariffs/
  <STATE>_urdb_rate.json, the donor state's saved URDB time-of-use rate
  (fetch_tou_rates.py).
- Environment: SC_KW_TARGET_FACTOR (0.8), SC_KW_TARGET_LOW (0.0), SC_RESERVE_PCT (20).

Steps
1. Builds one car per EV host with ev_cars.py, uncontrolled hosts then controlled
   hosts, each group with its own seeded draws: Level 2 (level2_kw) for the
   ev.lvl2_perc share of the group's cars, Level 1 (level1_kw) for the rest; under
   evwatts_sessions and session_rows the measured share of cars charges today. Each
   car's uncontrolled row comes from its own EV WATTS session (evwatts_sessions), NHTS
   vehicle-day (nhts_days) or block on the check curve (session_rows), with its
   plug-in window at home.
2. Copies every .dss file of the feeder (except *_original*) into ModifiedCircuitData/
   and points LoadShapes.dss at ../../profiles_use_bench/<circuit>/.
3. Appends two EV loads per host (EVu_<host>_1 and _2, or EVc_, kW=0.5 each, pf=1)
   to ModifiedCircuitData/Loads.dss:
   on the host's legs <host>_1 and <host>_2 when both exist, else both on the host
   load itself with its own bus1, kV, conn and phases (a balanced three-phase EV load
   at a three-phase host).
4. Writes Storage.dss: per target kWRated = max(storage_min_kw,
   round(storage_kw_per_peak_kw * peak, 3)), kWhRated = storage_hours * kWRated,
   kVA = kWRated / 0.90, 20 % stored, two monitors, and one StorageController
   (PeakShave, kWTarget = max(50, SC_KW_TARGET_FACTOR * total kW)) anchored on
   Monitor m1/m2 or the first Energymeter of Master.dss.
5. Writes PVSystems.dss and LoadShapes_PV.dss: per target pmpp = max(pv_min_kw,
   round(pv_kw_per_peak_kw * peak, 1)), kVA = 1.1 * pmpp, and one 96-point daily
   shape: "kW Generated (1000 kW Array)" / 1000 in the donor's SMART-DS solar file on
   this feeder's baseline peak day of the run's season, or on the circuit's own peak
   day under per_circuit (pv_daily_shape).
6. Rewrites Master.dss: replaces the yearly 15-minute 35040-step solve with
   "Solve mode=daily stepsize=15m number=96", comments out Plot lines, places the
   new Redirect lines before the first Solve, and appends Export lines for the
   storage monitors.
7. Writes Monitors_LoadVoltage.dss: one mode=0 Monitor vl_<load> per Load in
   ModifiedCircuitData/Loads.dss (load_voltage.py), and adds
   "Redirect Monitors_LoadVoltage.dss" just before the first Solve line.
7a. Makes the controlled rows with the ev_control rule (ev_control.py). Each
   controlled car starts from its own uncontrolled row. With ev_home_window true, a
   car with a window charges only inside it (energy that does not fit is left over);
   a car without one, and every car with ev_home_window false, may use every interval.
   - uncontrolled: the session rows unchanged.
   - valley_fill_feeder: solves the circuit without EVs in EVControl/base_solve/
     (run_base_solve; buildings only, or also PV and storage under ev_valley_base
     after_pv_storage), takes feeder-head P from Monitor m2, adds every uncontrolled
     car's kW, and places each controlled car in host order on the intervals where
     that curve is lowest, keeping its energy and its number of charging intervals.
   - valley_fill_transformer: the same on the terminal-1 P of each car's service
     transformer (service_transformers, without switched-out enabled=n lines; one
     Monitor mt_<n> per transformer that hosts a controlled car), plus the
     uncontrolled cars on it; a car whose host has no
     service transformer uses the feeder curve. Every placed car also joins the feeder
     curve.
   - offpeak_start: on the simulated day's month row of the weekday schedule of the
     saved tariff (the cars draw weekdays), each car starts at the first cheap
     interval of its window (its plug-in interval when none is cheap), or without a
     window at the first cheap interval at or after its first charging interval, and
     charges at its own power until its energy is delivered or the window ends.
   Then writes LoadShapes_EV.dss (EVu_i, EVc_i, 4 decimals).
8. Compiles Master.dss in OpenDSS (dss_engine), which runs its Solve and Export lines,
   and reads Solution.Converged.
9. When converged, reads every load Monitor through the engine (no Export lines) and
   writes the load voltage tables (per unit of the load's bus base kV).

Outputs
- ModifiedCircuitData/: copied and edited .dss files, LoadShapes_EV.dss, Storage.dss,
  PVSystems.dss, LoadShapes_PV.dss and the monitor CSVs OpenDSS exports.
- ModifiedCircuitData/Monitors_LoadVoltage.dss, load_voltages.parquet (one row per
  load, step and phase conductor), load_voltage_steps.csv (one row per step, customer
  loads only) and load_voltage_loads.csv (one row per load). The parquet and the load
  table mark EV legs in ev_leg. Columns in docs/outputs.md.
- <circuit>/EVControl/ev_cars.csv (when the circuit has EV cars): one row per car.
- <circuit>/EVControl/ (when the circuit has controlled cars and ev_control is not
  uncontrolled): ev_control_cars.csv (one row per controlled car); under the valley
  rules also ev_control_curves.csv (one row per curve and step) and base_solve/ (the
  .dss files and monitor CSVs of the no-EV solve). Columns in docs/outputs.md.
- Console counts: the ev_loads split when used, storage and PV raised to their
  minimum, peaks taken from Loads_original.dss, and EV hosts placed on their own
  bus (with how many carry a commercial com_ profile); load monitors, steps and the
  loads whose bus has no base voltage; under valley_fill_transformer the loads with
  one, no or several service transformers and the controlled cars on the feeder curve.

Fallbacks and floors
- ev_loads_uncontrolled and ev_loads_controlled both empty: ev_loads split in half.
- Peak: profile CSV maximum, else Loads_original.dss kW.
- Storage and PV minimums from der_sizing; controller kWTarget floor 50 kW.

Stops (exit 1 unless noted)
- ModifiedCircuitData/ already holds files.
- No feeder subfolder.
- scenario_assignments.json missing, unparsable or not a JSON object.
- der_sizing key missing from pipeline_config.yaml.
- A .dss copy into ModifiedCircuitData/ (or EVControl/base_solve/) fails, or the
  profiles_use_bench/<circuit>/ folder its LoadShapes.dss points at does not exist.
- A storage or PV target is not a load in Loads.dss.
- An EV host has neither both _1 and _2 legs nor a load of its own in Loads.dss.
- PV shape: season not summer or winter, peak-day record or row missing, solar file,
  column or the 96 rows of the date missing.
- No peak kW for a storage or PV target.
- No yearly solve line to retarget in Master.dss.
- RuntimeError: storage objects exist but Master.dss has no Monitor m1/m2 or
  Energymeter; a DER Redirect line is missing; a monitor export CSV is missing; the
  loads of the compiled circuit differ from the monitored loads, or a load monitor
  does not match its load.
- voltage_band missing from pipeline_config.yaml; ev_control, ev_valley_base or
  ev_cars missing or unknown; ev_home_window not true or false.
- EV cars: ev.effective_seed missing; charging_share or months of ev_inputs.yaml other
  than measured and all; under evwatts_sessions and session_rows, evwatts_extract_dir
  unset or without the extract file, or no census_division for the donor state.
- EV base solve: no yearly solve line or no Monitor m2 in Master.dss, no convergence,
  or a monitor without 96 steps.
- offpeak_start: the tariff file missing; without a window, a car's energy longer
  than the day at its power (ValueError).
- Uncaught exception: for example the check curve in data_ev/ missing under
  session_rows (FileNotFoundError).
- Solution.Converged is not True after Compile, or the circuit was not compiled.
- exit 0 otherwise.
"""

import os, re, sys, csv, time, json, shutil
import numpy as np, pandas as pd

# -----------------------
# Knobs
# -----------------------
DEFAULT_EV_L2_PERC   = 0.80

# Storage sizing vs load peak (ratios and minimums: der_sizing in pipeline_config.yaml)
STORAGE_PF           = 0.90
STORAGE_EFF_CHG      = 95.0
STORAGE_EFF_DCH      = 95.0

# PV sizing vs load peak (ratio and minimum: der_sizing in pipeline_config.yaml)
IRRADIANCE_NPTS      = 96
IRR_INTERVAL_H       = 0.25

ACTIVATE_EV          = True
COMPILE_CIRCUIT      = True

# -----------------------
# Helpers
# -----------------------
# read_text / read_lines: the UTF-8 text or list of lines of a file.
# write_text / write_lines: write text or lines to a file in UTF-8, replacing it.
# try_float(x, default): float(x), or default if conversion fails.
# clamp01(x): float(x) limited to [0, 1].
def read_text(p):  return open(p,'r',encoding='utf-8').read()
def write_text(p,t): open(p,'w',encoding='utf-8').write(t)
def read_lines(p): return open(p,'r',encoding='utf-8').readlines()
def write_lines(p,ls): open(p,'w',encoding='utf-8').writelines(ls)
def try_float(x, default=None):
    try: return float(x)
    except Exception: return default
def clamp01(x): return max(0.0, min(1.0, float(x)))
def is_feeder_dir(path):
    """Return True if path is a folder whose file names include loads.dss,
    loadshapes.dss and master.dss (case-insensitive); False if it is not a folder
    or cannot be listed. ModifiedCircuitData/ qualifies once it exists, so the
    caller leaves it out."""
    if not os.path.isdir(path):
        return False
    try:
        names = {nm.lower() for nm in os.listdir(path)}
    except PermissionError:
        return False
    return {"loads.dss", "loadshapes.dss", "master.dss"}.issubset(names)

def resolve_dss_file(directory, filename):
    """Case-insensitive file lookup within `directory`. ext4 is genuinely
    case-sensitive (unlike the Windows machine this was authored on), and
    SMART-DS export casing is not guaranteed, so a hardcoded-case path can
    silently miss a file that is actually present under a different case.
    Returns the real on-disk path; raises clearly if no match exists."""
    exact = os.path.join(directory, filename)
    if os.path.exists(exact):
        return exact
    target = filename.lower()
    for entry in os.listdir(directory):
        if entry.lower() == target and os.path.isfile(os.path.join(directory, entry)):
            return os.path.join(directory, entry)
    raise FileNotFoundError(f"{filename} not found in {directory} (case-insensitive search)")

# EV helpers (your modules)
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
ROOT        = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
sys.path.insert(0, os.path.join(ROOT, 'deployer_modules'))
from pfs_ev_base_profiles import process_vehicle_data
from dss_engine import create_dss_engine
from load_voltage import monitor_lines, read_load_monitors, load_voltage_frame, step_table, load_table
from ev_control import valley_fill, valley_fill_curves, monitor_p_kw, service_transformers, cheap_intervals, offpeak_start

# DER sizing from der_sizing in pipeline_config.yaml (repository root, one level above ROOT)
sys.path.insert(0, os.path.join(ROOT, '..'))
from pipeline_utils import load_config, peak_day_rule, ev_control, ev_valley_base, ev_home_window
from pipeline_utils import ev_cars as ev_cars_source
sys.path.append(ROOT)
from heating_split import is_baseline_only
from ev_cars import (load_inputs, read_evwatts_pool, charging_share, read_nhts_pool, evwatts_cars,
                     nhts_cars, session_rows_cars, cars_frame, EVWATTS_EXTRACT_FILE, NHTS_EXTRACT_FILE)
CFG = load_config()
PEAK_DAY_RULE = peak_day_rule(CFG)
EV_CONTROL = ev_control(CFG)
EV_VALLEY_BASE = ev_valley_base(CFG)
EV_CARS = ev_cars_source(CFG)
EV_HOME_WINDOW = ev_home_window(CFG)
DER_SIZING = CFG.get("der_sizing") or {}
def der_sizing(key):
    if key not in DER_SIZING:
        print(f"[FAIL] der_sizing.{key} is missing from pipeline_config.yaml.")
        sys.exit(1)
    return float(DER_SIZING[key])
STORAGE_KW_PER_PEAK  = der_sizing("storage_kw_per_peak_kw")
STORAGE_MIN_KW       = der_sizing("storage_min_kw")
STORAGE_ENERGY_HOURS = der_sizing("storage_hours")
PV_KW_PER_PEAK       = der_sizing("pv_kw_per_peak_kw")
PV_MIN_KW            = der_sizing("pv_min_kw")
VOLTAGE_BAND = CFG.get("voltage_band") or {}
if "low_pu" not in VOLTAGE_BAND or "high_pu" not in VOLTAGE_BAND:
    print("[FAIL] voltage_band.low_pu and voltage_band.high_pu must be set in pipeline_config.yaml.")
    sys.exit(1)
V_LOW_PU, V_HIGH_PU = float(VOLTAGE_BAND["low_pu"]), float(VOLTAGE_BAND["high_pu"])

# -----------------------
# Start
# -----------------------
START_TIME     = time.time()
CIRCUIT_FOLDER = os.path.basename(CURRENT_DIR)
PROFILES_PATH  = os.path.join(CURRENT_DIR, '..', 'profiles_use_bench', CIRCUIT_FOLDER)
OUT_DIR        = os.path.join(CURRENT_DIR, "ModifiedCircuitData")

# A second run in the same folder would read its own results and append the EV loads again.
if os.path.isdir(OUT_DIR) and os.listdir(OUT_DIR):
    print(f"[FAIL] {OUT_DIR} already holds results of this script. "
          "Run the deploy only in a freshly instantiated circuit folder.")
    sys.exit(1)

# feeder subfolder (ModifiedCircuitData is this script's output, never the feeder source)
subs = [d for d in os.listdir(CURRENT_DIR)
        if d != "ModifiedCircuitData" and is_feeder_dir(os.path.join(CURRENT_DIR, d))]
if not subs:
    print("[FAIL] No feeder subfolder with Loads, LoadShapes, and Master DSS files found.")
    sys.exit(1)
CIRCUIT_NAME = subs[0]
CIRCUIT_DIR  = os.path.join(CURRENT_DIR, CIRCUIT_NAME)

# assignments JSON (instantiate_circuits.py writes it for every circuit)
ASSIGN_PATH = os.path.join(CURRENT_DIR, "scenario_assignments.json")
if not os.path.exists(ASSIGN_PATH):
    print(f"[FAIL] scenario_assignments.json not found: {ASSIGN_PATH}. "
          "Run instantiate_circuits.py (Phase 7b) first.")
    sys.exit(1)
try:
    ASSIGN = json.loads(read_text(ASSIGN_PATH))
except Exception as e:
    print(f"[FAIL] Could not parse scenario_assignments.json: {e}")
    sys.exit(1)
if not isinstance(ASSIGN, dict):
    print(f"[FAIL] scenario_assignments.json does not hold a JSON object: {ASSIGN_PATH}")
    sys.exit(1)
print(f"[OK] Loaded scenario assignments: {ASSIGN_PATH}")

# EV params
lvl2_charger_perc = clamp01(ASSIGN.get("ev", {}).get("lvl2_perc", DEFAULT_EV_L2_PERC))
print(f"EV params -> L2 share={lvl2_charger_perc:.2f}")

# Read Loads.dss (for bases + daily mapping)
PATH_LOADS_DSS = resolve_dss_file(CIRCUIT_DIR, 'Loads.dss')
try:
    # Optional: the instantiation script's pre-modification backup. Resolve
    # case-insensitively too -- its on-disk case tracks whatever case Loads.dss
    # had at backup time, not this literal.
    PATH_LOADS_DSS_ORIG = resolve_dss_file(CIRCUIT_DIR, 'Loads_original.dss')
except FileNotFoundError:
    PATH_LOADS_DSS_ORIG = os.path.join(CIRCUIT_DIR, 'Loads_original.dss')
loads_content        = read_lines(PATH_LOADS_DSS)
unique_bases = set(); all_full=set(); base_to_daily={}
for line in loads_content:
    if line.strip().lower().startswith("new load."):
        m_name = re.search(r"New\s+Load\.(\S+)", line, flags=re.IGNORECASE)
        if not m_name: continue
        full = m_name.group(1)
        base = re.sub(r"_[0-9]+$", "", full)
        if base != "load":
            unique_bases.add(base)
        all_full.add(full)
        m_daily = re.search(r"\bdaily=(\S+)", line, flags=re.IGNORECASE)
        if m_daily:
            base_to_daily.setdefault(base, set()).add(m_daily.group(1))
unique_loads_list = sorted(unique_bases)
print(f"Found {len(unique_loads_list)} unique base loads.")

# Parsed attributes for EV loads
parsed_loads_map = {}
for line in read_lines(PATH_LOADS_DSS):
    s = line.strip()
    if not s.lower().startswith("new load."): continue
    m = re.search(r"New\s+Load\.(\S+)", s)
    if not m: continue
    name = m.group(1)
    bus  = re.search(r"bus1=([\w\.\-]+)", s)
    kv   = re.search(r"kV=([\d\.Ee+-]+)", s)
    ph   = re.search(r"phases=(\d+)", s.lower())
    conn = re.search(r"conn=(\w+)", s.lower())
    parsed_loads_map[name] = {
        "bus1": bus.group(1) if bus else None,
        "kV":   kv.group(1)  if kv  else None,
        "ph":   ph.group(1)  if ph  else None,
        "conn": conn.group(1) if conn else None,
    }

def ensure_redirects_before_solve(master_path):
    """
    Rewrite master_path so that the Redirect lines for the files this script creates
    come before the first Solve.

    Removes every line containing "Redirect LoadShapes_EV.dss",
    "Redirect LoadShapes_PV.dss", "Redirect PVSystems.dss" or "Redirect Storage.dss",
    then inserts, for each of those files that exists next to master_path:
    - LoadShapes_EV.dss and LoadShapes_PV.dss after the first "Redirect LoadShapes.dss";
    - Storage.dss and PVSystems.dss after the first "Redirect Loads.dss";
    - either block just before the first Solve line if its anchor was not met, or at
      the end of the file if there is no Solve line.
    Does nothing if none of the four files exists. Writes master_path; returns None.
    The comment lines written earlier ("! Added EV files" and similar) are kept.
    """
    ml = read_lines(master_path)

    # Which files exist in the scenario folder?
    base_dir = os.path.dirname(master_path)
    have_ev_ls = os.path.exists(os.path.join(base_dir, "LoadShapes_EV.dss"))
    have_pv_ls = os.path.exists(os.path.join(base_dir, "LoadShapes_PV.dss"))
    have_pv    = os.path.exists(os.path.join(base_dir, "PVSystems.dss"))
    have_sto   = os.path.exists(os.path.join(base_dir, "Storage.dss"))

    # Build insertion blocks
    block_shapes = []
    if have_ev_ls:
        block_shapes += ["\n! Added EV files\n", "Redirect LoadShapes_EV.dss\n"]
    if have_pv_ls:
        block_shapes += ["\n! Added PV loadshape\n", "Redirect LoadShapes_PV.dss\n"]

    block_objs = []
    if have_sto:
        block_objs += ["\n! Added Storage file\n", "Redirect Storage.dss\n"]
    if have_pv:
        block_objs += ["\n! Added PV items\n", "Redirect PVSystems.dss\n"]

    if not block_shapes and not block_objs:
        return  # nothing to do

    # Remove any lines we manage already to avoid duplicates
    MANAGED = (
        "Redirect LoadShapes_EV.dss",
        "Redirect LoadShapes_PV.dss",
        "Redirect PVSystems.dss",
        "Redirect Storage.dss",
    )
    cleaned = [ln for ln in ml if not any(m in ln for m in MANAGED)]

    out = []
    inserted_shapes = False
    inserted_objs   = False

    for ln in cleaned:
        s = ln.strip()
        out.append(ln)

        # After LoadShapes.dss -> shapes
        if (not inserted_shapes) and re.search(r'(?i)\bRedirect\s+LoadShapes\.dss\b', ln):
            if block_shapes:
                out.extend(block_shapes)
            inserted_shapes = True

        # After Loads.dss -> objects (storage/pv)
        if (not inserted_objs) and re.search(r'(?i)\bRedirect\s+Loads\.dss\b', ln):
            if block_objs:
                out.extend(block_objs)
            inserted_objs = True

        # Just before the first Solve, make sure both blocks are in
        if re.match(r'(?i)^\s*Solve\b', s):
            # remove the Solve temporarily
            out.pop()
            if (not inserted_shapes) and block_shapes:
                out.extend(block_shapes)
                inserted_shapes = True
            if (not inserted_objs) and block_objs:
                out.extend(block_objs)
                inserted_objs = True
            # put Solve back
            out.append(ln)

    # If there was no Solve (rare), append at end
    if (not inserted_shapes) and block_shapes:
        out.extend(block_shapes)
    if (not inserted_objs) and block_objs:
        out.extend(block_objs)

    write_lines(master_path, out)

def add_redirect_before_solve(master_path, filename):
    """Insert the one line "Redirect <filename>" just before the first Solve line of
    master_path (at the end if there is no Solve line). Writes master_path."""
    ml = read_lines(master_path)
    idx = next((i for i, ln in enumerate(ml) if re.match(r'(?i)^\s*Solve\b', ln.strip())), len(ml))
    ml.insert(idx, f"Redirect {filename}\n")
    write_lines(master_path, ml)

def assert_expected_redirects(master_path, storage_present, pv_present, ev_present):
    """Fail loudly if a DER redirect we depend on didn't make it into Master.dss.

    Without this, a silently-missed insertion (e.g. from a case mismatch on the
    'Redirect ...' anchor lines) still compiles and solves -- it just reports a
    Flex scenario containing no DER, with no error at all.
    """
    content = read_text(master_path)
    def has_redirect(name):
        return re.search(rf'(?i)\bRedirect\s+{re.escape(name)}\b', content) is not None
    missing = []
    if storage_present and not has_redirect("Storage.dss"):
        missing.append("Storage.dss")
    if pv_present and not (has_redirect("PVSystems.dss") and has_redirect("LoadShapes_PV.dss")):
        missing.append("PVSystems.dss/LoadShapes_PV.dss")
    if ev_present and not has_redirect("LoadShapes_EV.dss"):
        missing.append("LoadShapes_EV.dss")
    if missing:
        raise RuntimeError(
            f"Master.dss is missing expected Redirect line(s) for: {', '.join(missing)}. "
            "DER would silently compile out of the circuit. Aborting before solve."
        )

def find_controller_anchor(master_path):
    """
    Return the element monitored by the first "New Monitor.m1" or "New Monitor.m2"
    line of master_path (its element= value); if none, the element of the first
    "New Energymeter.<name> <element>" line; if none, or if the file cannot be read,
    None. The caller raises RuntimeError on None.
    """
    elem = None
    try:
        with open(master_path, "r", encoding="utf-8") as f:
            for ln in f:
                m = re.search(r'(?i)\bnew\s+monitor\.m[12]\b.*\belement\s*=\s*([^\s]+)', ln)
                if m:
                    elem = m.group(1)
                    break
        if elem is None:
            with open(master_path, "r", encoding="utf-8") as f:
                for ln in f:
                    m = re.search(r'(?i)\bnew\s+energymeter\.\S+\s+([^\s]+)', ln)
                    if m:
                        elem = m.group(1)
                        break
    except Exception:
        pass
    return elem

def retarget_master_to_daily(master_path, npts=96, stepsize="15m", comment_plots=True):
    """
    Turn the yearly run in master_path into a daily run.

    Replaces each line that starts with "solve" and contains mode=yearly, stepsize=15m
    and number=35040 (case-insensitive, any order) with
    "Solve mode=daily stepsize=<stepsize> number=<npts>". With comment_plots, also turns
    each uncommented line starting with "plot" into "! <line>   (disabled by deploy)".
    Other lines are kept, with a newline added if missing.
    Writes master_path only if a solve line was replaced. Returns True if a solve line
    was replaced, else False; the caller stops on False.
    """
    ml = read_lines(master_path)
    out = []
    changed = False
    commented_plots = 0

    for ln in ml:
        lns = ln.rstrip("\n")
        s = ln.strip()
        # 1) Match only lines that start with "solve" and contain the 3 yearly properties
        if re.match(r'(?i)^solve\b', s):
            has_yearly   = re.search(r'(?i)\bmode\s*=\s*yearly\b', s) is not None
            has_15m      = re.search(r'(?i)\bstepsize\s*=\s*15m\b', s) is not None
            has_35040    = re.search(r'(?i)\bnumber\s*=\s*35040\b', s) is not None
            if has_yearly and has_15m and has_35040:
                out.append(f"Solve mode=daily stepsize={stepsize} number={npts}\n")
                changed = True
                continue  # skip original yearly line

        # 2) Comment out Plot lines (but keep Exports)
        if comment_plots and re.match(r'(?i)^\s*plot\b', s) and not re.match(r'^\s*!', lns):
            out.append(f"! {lns}   (disabled by deploy)\n")
            commented_plots += 1
            continue

        # default: pass through unchanged
        out.append(ln if ln.endswith("\n") else ln + "\n")

    if changed:
        write_lines(master_path, out)
    return changed

PEAK_FROM_ORIGINAL_KW = []  # loads sized from Loads_original.dss kW instead of a profile CSV

def peak_kw_for_load(full_name):
    """
    Return the peak kW used to size storage or PV on load full_name.

    1. For each daily loadshape of the load's base name (full_name without its _<n>
       suffix), in sorted order: if <circuit>/../profiles_use_bench/<circuit>/<shape>.csv
       exists, return the maximum of its first column (read with header=None). Read errors are ignored and the next shape is tried.
    2. Else, the kW= value of the first line of <feeder>/Loads_original.dss that
       contains "New Load.<full_name>" followed by white space; the name is added to
       PEAK_FROM_ORIGINAL_KW, which the script counts.
    3. Else, print [FAIL] and exit 1.
    """
    base = re.sub(r"_[0-9]+$", "", full_name)
    for dn in sorted(base_to_daily.get(base, set())):
        csv_path = os.path.join(PROFILES_PATH, f"{dn}.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, header=None)
                return float(df[0].max())
            except Exception:
                pass
    if os.path.exists(PATH_LOADS_DSS_ORIG):
        for line in read_lines(PATH_LOADS_DSS_ORIG):
            if re.search(rf"New Load\.{re.escape(full_name)}\s", line):
                m_kw = re.search(r"\bkW=([0-9\.Ee+-]+)", line)
                if m_kw:
                    v = try_float(m_kw.group(1), None)
                    if v is not None:
                        PEAK_FROM_ORIGINAL_KW.append(full_name)
                        return v
    print(f"[FAIL] No peak kW for {full_name}: no profile CSV in {PROFILES_PATH} "
          f"and no kW= in {PATH_LOADS_DSS_ORIG}.")
    sys.exit(1)

PV_KW_COLUMN = "kW Generated (1000 kW Array)"

def simulated_day(feeder, season):
    """
    Return (month, day) of the simulated day of feeder for season: the feeder's
    baseline peak day for that season in <work_root>/5b_profile_generation/<STATE>_peak_days.csv.
    With peak_day_rule per_circuit and a circuit mix that is not 100 % baseline, the
    date is the row of the feeder, season and mix in
    <work_root>/mix_days/<STATE>_circuit_days.csv instead. The records hold no year.
    Stops if the season or the peak day is missing, or under per_circuit if the
    circuit's mix is not in mixes.json.
    """
    if season not in ("summer", "winter"):
        print(f"[FAIL] scenario_assignments.json season is {season!r}; expected summer or winter.")
        sys.exit(1)
    peak_days_path = os.path.join(CFG["work_root"], "5b_profile_generation",
                                  f"{CFG['state']}_peak_days.csv")
    mix_name = None
    if PEAK_DAY_RULE == "per_circuit":
        m_mix = re.match(r"^.*_circuit_\d+_(.+)$", CIRCUIT_FOLDER)
        mixes_path = os.path.join(CFG["work_root"], "7_circuit_instantiation", "mixes.json")
        mixes = json.loads(read_text(mixes_path)) if os.path.exists(mixes_path) else {}
        if not m_mix or m_mix.group(1) not in mixes:
            print(f"[FAIL] No mix for circuit folder {CIRCUIT_FOLDER} in {mixes_path}.")
            sys.exit(1)
        if not is_baseline_only(mixes[m_mix.group(1)]["shares"]):
            mix_name = m_mix.group(1)
            peak_days_path = os.path.join(CFG["work_root"], "mix_days",
                                          f"{CFG['state']}_circuit_days.csv")
    if not os.path.exists(peak_days_path):
        print(f"[FAIL] Peak-day record not found: {peak_days_path}. "
              f"Run Phase {'mix_days' if mix_name else '5b'} first.")
        sys.exit(1)
    with open(peak_days_path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["Feeder"] == feeder and r["Season"] == season
                and (mix_name is None or r["Mix"] == mix_name)]
    if len(rows) != 1:
        print(f"[FAIL] {len(rows)} {season} peak days for feeder {feeder}"
              f"{' and mix ' + mix_name if mix_name else ''} in {peak_days_path}; expected 1.")
        sys.exit(1)
    if mix_name:
        print(f"PV day -> peak_day_rule per_circuit, mix {mix_name}, from {peak_days_path}")
    return int(rows[0]["Month"]), int(rows[0]["Day"])

def pv_daily_shape(feeder, season):
    """
    Return the PV daily shape of feeder for season: the IRRADIANCE_NPTS values of
    PV_KW_COLUMN divided by 1000 (rounded to 9 decimals) in the donor's SMART-DS solar file
    (PIPELINE_PV_PROFILE_FILE), on the month and day of simulated_day(feeder, season).
    The file's year is ignored. Stops as simulated_day does, or if the file, the
    column or the IRRADIANCE_NPTS rows of that date are missing.
    """
    month, day = simulated_day(feeder, season)
    pv_file = CFG["pv_profile_file"]
    if not os.path.exists(pv_file):
        print(f"[FAIL] PV profile file not found: {pv_file}")
        sys.exit(1)
    with open(pv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if PV_KW_COLUMN not in (reader.fieldnames or []):
            print(f"[FAIL] Column {PV_KW_COLUMN!r} not in {pv_file}")
            sys.exit(1)
        values = [round(float(r[PV_KW_COLUMN]) / 1000, 9) for r in reader
                  if int(r["Month"]) == month and int(r["Day"]) == day]
    if len(values) != IRRADIANCE_NPTS:
        print(f"[FAIL] {len(values)} rows for month {month} day {day} in {pv_file}; "
              f"expected {IRRADIANCE_NPTS}.")
        sys.exit(1)
    print(f"PV shape -> {season} peak day {month:02d}-{day:02d} of {feeder} from {pv_file}")
    return values

def get_circuit_name(master_path):
    """Parse the 'New Circuit.<name>' line from Master.dss."""
    with open(master_path, "r", encoding="utf-8") as f:
        for ln in f:
            m = re.search(r'(?i)^\s*new\s+circuit\.(\S+)', ln.strip())
            if m:
                return m.group(1)
    return None

def assert_monitor_exports(master_path, monitor_names, search_dir):
    """Fail loudly if an expected 'Export Monitors <name>' CSV isn't on disk
    after Compile/Solve, rather than silently trusting the export happened.

    OpenDSS writes these to '<CircuitName>_Mon_<monitorname>_1.csv' under
    DataPath. Compile "<path>/Master.dss" moves DataPath to the folder of
    Master.dss (ModifiedCircuitData/), so search_dir is that folder.
    """
    if not monitor_names:
        return
    circuit_name = get_circuit_name(master_path)
    if not circuit_name:
        raise RuntimeError("Could not parse circuit name from Master.dss to verify monitor exports.")
    missing = [
        name for name in monitor_names
        if not os.path.exists(os.path.join(search_dir, f"{circuit_name}_Mon_{name}_1.csv"))
    ]
    if missing:
        raise RuntimeError(
            f"Expected monitor export CSV(s) not found after Compile/Solve: {missing} "
            f"(circuit={circuit_name}, dir={search_dir})"
        )

# ---------------- EV host lists from JSON ----------------
json_ev_un = ASSIGN.get("ev_loads_uncontrolled", []) if isinstance(ASSIGN, dict) else []
json_ev_ct = ASSIGN.get("ev_loads_controlled",   []) if isinstance(ASSIGN, dict) else []

# If missing, fallback to ev_loads + even split
if (not json_ev_un) and (not json_ev_ct):
    all_ev = ASSIGN.get("ev_loads", [])
    half = len(all_ev)//2
    json_ev_un = all_ev[:half]
    json_ev_ct = all_ev[half:]
    if all_ev:
        print(f"[WARN] ev_loads_uncontrolled and ev_loads_controlled are empty: "
              f"split {len(all_ev)} ev_loads hosts into {len(json_ev_un)} uncontrolled "
              f"and {len(json_ev_ct)} controlled.")

N_u = len(json_ev_un)
N_c = len(json_ev_ct)

# ---------------- EV cars (ev_cars in pipeline_config.yaml, deployer_modules/ev_cars.py) ----------------
EV_INPUTS = load_inputs(os.path.join(ROOT, "data_ev_cars", "ev_inputs.yaml"))
cars = []
if ACTIVATE_EV and (N_u + N_c) > 0:
    if EV_INPUTS["charging_share"] != "measured" or EV_INPUTS["months"] != "all":
        print(f"[FAIL] ev_inputs.yaml: charging_share {EV_INPUTS['charging_share']!r} and months "
              f"{EV_INPUTS['months']!r}; this deploy supports measured and all.")
        sys.exit(1)
    ev_effective_seed = ASSIGN.get("ev", {}).get("effective_seed")
    if ev_effective_seed is None:
        print(f"[FAIL] ev.effective_seed is missing from {ASSIGN_PATH}.")
        sys.exit(1)
    ev_state = CFG["state"]
    if EV_CARS in ("evwatts_sessions", "session_rows"):
        ev_extract_dir = CFG["evwatts_extract_dir"] if "evwatts_extract_dir" in CFG else None
        if not ev_extract_dir or not os.path.exists(os.path.join(ev_extract_dir, EVWATTS_EXTRACT_FILE)):
            print(f"[FAIL] ev_cars {EV_CARS} needs evwatts_extract_dir in configs/local.yaml, a folder "
                  f"holding {EVWATTS_EXTRACT_FILE} (build_evwatts_extract.py); got {ev_extract_dir!r}.")
            sys.exit(1)
        if ev_state not in EV_INPUTS["census_division"]:
            print(f"[FAIL] No census_division for {ev_state} in ev_inputs.yaml.")
            sys.exit(1)
        ev_pool = read_evwatts_pool(ev_extract_dir, EV_INPUTS["census_division"][ev_state])
        ev_share = charging_share(ev_pool)
        print(f"EV cars -> EV WATTS pool: {len(ev_pool)} sessions of {EV_INPUTS['census_division'][ev_state]}, "
              f"share of cars charging {ev_share:.6f}")
    if EV_CARS in ("nhts_days", "session_rows"):
        ev_nhts_pool = read_nhts_pool(os.path.join(ROOT, "data_ev_cars", NHTS_EXTRACT_FILE.format(state=ev_state)))
    if EV_CARS == "session_rows":
        ev_check_curve = process_vehicle_data(CURRENT_DIR,
                                              profile_folder=EV_INPUTS["check_curve_folder"],
                                              profile_file=EV_INPUTS["check_curve_file"])
    for group, hosts in (("uncontrolled", json_ev_un), ("controlled", json_ev_ct)):
        if EV_CARS == "evwatts_sessions":
            group_cars = evwatts_cars(group, hosts, ev_pool, ev_share, lvl2_charger_perc, EV_INPUTS, ev_effective_seed)
        elif EV_CARS == "nhts_days":
            group_cars = nhts_cars(group, hosts, ev_nhts_pool, lvl2_charger_perc, EV_INPUTS, ev_effective_seed)
        else:
            group_cars = session_rows_cars(group, hosts, ev_check_curve, ev_share, lvl2_charger_perc, EV_INPUTS,
                                           ev_effective_seed, ev_nhts_pool if group == "controlled" else None)
        print(f"EV cars -> {EV_CARS}, {group}: {len(group_cars)} cars, Level 2 "
              f"{sum(c['level'] == 'L2' for c in group_cars)}, charging today {sum(c['charges_today'] for c in group_cars)}")
        cars += group_cars
cars_u = [c for c in cars if c["group"] == "uncontrolled"]
cars_c = [c for c in cars if c["group"] == "controlled"]
arr_u = np.zeros((N_u, IRRADIANCE_NPTS))
arr_c_sessions = np.zeros((N_c, IRRADIANCE_NPTS))  # controlled cars' own uncontrolled rows
for j, c in enumerate(cars_u):
    arr_u[j, :] = c["row"]
for j, c in enumerate(cars_c):
    arr_c_sessions[j, :] = c["row"]
arr_c = arr_c_sessions                               # replaced by the ev_control rule before LoadShapes_EV.dss is written
# Controlled cars' windows (None: every interval) and charging power for the ev_control rules
windows_c = [c["window"] if EV_HOME_WINDOW else None for c in cars_c]
power_c = [c["power_kw"] for c in cars_c]

EV_HOSTS_OWN_BUS = []  # EV hosts without _1/_2 legs (three-phase loads): EV on the host's own bus

def ev_leg_infos(base):
    """Return the parsed attributes for the two EV legs of host base: those of
    <base>_1 and <base>_2 when both are loads; else those of the host load <base>
    itself for both legs (its own bus1, kV, conn and phases, so a three-phase host
    gets a balanced three-phase EV load), and base is added to EV_HOSTS_OWN_BUS.
    Stops if base has neither both legs nor a load of its own in Loads.dss."""
    n1 = base + "_1"; n2 = base + "_2"
    if n1 in parsed_loads_map and n2 in parsed_loads_map:
        return parsed_loads_map[n1], parsed_loads_map[n2]
    host = parsed_loads_map.get(base)
    if host is None:
        print(f"[FAIL] EV host {base} is not a load in {PATH_LOADS_DSS}.")
        sys.exit(1)
    EV_HOSTS_OWN_BUS.append(base)
    return host, host

# ---------------- Prepare scenario dir ----------------
os.makedirs(OUT_DIR, exist_ok=True)

# Copy ALL .dss files from the feeder directory (dynamic discovery).
# Handles Regulators.dss, Capacitors.dss, or any other optional files
# that vary across SMART-DS feeders.  Excludes _original.dss backups
# created by the instantiation script.
dss_files = [f for f in os.listdir(CIRCUIT_DIR)
             if f.lower().endswith('.dss') and '_original' not in f.lower()]

def copy_feeder_dss(dst_dir, up):
    """Copy every file of dss_files from the feeder folder into dst_dir, point
    LoadShapes.dss at <up>profiles_use_bench/<circuit>/ (up climbs from dst_dir to the
    folder that holds the circuit folders: "../../" for ModifiedCircuitData/,
    "../../../" for EVControl/base_solve/), and return the path of the Master.dss copy.
    Stops if a copy fails or that profiles folder does not exist."""
    if not os.path.isdir(os.path.join(dst_dir, up, "profiles_use_bench", CIRCUIT_FOLDER)):
        print(f"[FAIL] {up}profiles_use_bench/{CIRCUIT_FOLDER}/ does not exist from {dst_dir}.")
        sys.exit(1)
    master_path = None
    for fn in dss_files:
        src = os.path.join(CIRCUIT_DIR, fn)
        dst = os.path.join(dst_dir, fn)
        try:
            shutil.copy2(src, dst)
        except Exception as e:
            print(f"[FAIL] Could not copy {src} to {dst}: {e}")
            sys.exit(1)
        if fn.lower() == 'master.dss':
            master_path = dst
        if fn.lower() == 'loadshapes.dss':
            lines = read_lines(dst)
            upd = []
            needle = f"file=../profiles_use_bench/{CIRCUIT_FOLDER}/"
            repl   = f"file={up}profiles_use_bench/{CIRCUIT_FOLDER}/"
            for ln in lines:
                upd.append(ln.replace(needle, repl))
            write_lines(dst, upd)
    return master_path

master_dss_path = copy_feeder_dss(OUT_DIR, "../../")

# ---------------- Write EV loads (EV shapes after the ev_control rule, below) ----------------
loads_ev_path      = resolve_dss_file(OUT_DIR, "Loads.dss")      # append into existing (copied above, case preserved)
loadshapes_ev_path = os.path.join(OUT_DIR, "LoadShapes_EV.dss")  # new EV shapes file

if ACTIVATE_EV and (N_u + N_c) > 0:
    # Append EV loads (two legs _1/_2) using attributes from parsed_loads_map
    with open(loads_ev_path, "a", encoding="utf-8") as f_ld:
        f_ld.write("\n! EV Loads (mixed types)\n\n")
        # uncontrolled
        for i, base in enumerate(json_ev_un):
            for suff, info in zip(("_1","_2"), ev_leg_infos(base)):
                ev_load_name = f"EVu_{base}{suff}"
                f_ld.write(
                    f"New Load.{ev_load_name} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVu_{i}\n"
                )
        # controlled
        for i, base in enumerate(json_ev_ct):
            for suff, info in zip(("_1","_2"), ev_leg_infos(base)):
                ev_load_name = f"EVc_{base}{suff}"
                f_ld.write(
                    f"New Load.{ev_load_name} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVc_{i}\n"
                )

    # Ensure Master redirects EV shapes
    if master_dss_path:
        ml = read_lines(master_dss_path); new_ml = []; inserted=False
        for ln in ml:
            new_ml.append(ln)
            if re.search(r'(?i)\bRedirect\s+LoadShapes\.dss\b', ln) and not inserted:
                new_ml.append("\n! Added EV files\n")
                new_ml.append("Redirect LoadShapes_EV.dss\n")
                inserted = True
        if not inserted:
            new_ml.append("\n! Added EV files at end\nRedirect LoadShapes_EV.dss\n")
        write_lines(master_dss_path, new_ml)

# ---------------- Storage (from JSON targets) ----------------
storage_targets = ASSIGN.get("storage_targets", []) if isinstance(ASSIGN, dict) else []
storage_path = os.path.join(OUT_DIR, "Storage.dss")
monitor_export_lines = []
monitor_names = []       # bare monitor names (no class prefix), for the post-export existence check
# Controller sizing knobs (override with env if desired)
SC_KW_TARGET_FACTOR = float(os.environ.get("SC_KW_TARGET_FACTOR", "0.8"))  # fraction of total storage kW
SC_KW_TARGET_LOW    = float(os.environ.get("SC_KW_TARGET_LOW",  "0.0"))    # charge threshold
SC_RESERVE_PCT      = float(os.environ.get("SC_RESERVE_PCT",    "20"))     # %Reserve

storage_names = []       # DSS object names without class prefix (e.g., 'storage_busA')
storage_objnames = []    # Full class-qualified ('Storage.storage_busA')
storage_objnames_2 = []
total_storage_kW = 0.0
n_storage = 0
n_storage_at_min = 0

if storage_targets:
    with open(storage_path, "w", encoding="utf-8") as f_st:
        f_st.write("! ==========================\n! STORAGE ELEMENTS (from JSON targets)\n! ==========================\n\n")
        for full in storage_targets:
            info = parsed_loads_map.get(full)
            if not info:
                print(f"[FAIL] Storage target {full} is not a load in {PATH_LOADS_DSS}.")
                sys.exit(1)

            pk = peak_kw_for_load(full)  # your existing helper
            if round(STORAGE_KW_PER_PEAK * pk, 3) < STORAGE_MIN_KW:
                n_storage_at_min += 1
            kWRated  = max(STORAGE_MIN_KW, round(STORAGE_KW_PER_PEAK * pk, 3))
            kWhRated = round(kWRated * STORAGE_ENERGY_HOURS, 3)
            kVA      = round(kWRated / max(STORAGE_PF, 1e-3), 3)

            busname = info["bus1"].split('.')[0]
            ph = info.get("ph", "1")
            bus_str = f"{busname}.1.2.3" if ph == "3" else info["bus1"]
            stg_name = f"storage_{full}"

            # write the storage element
            f_st.write(
                f"New Storage.{stg_name} phases={ph} bus1={bus_str} kV={info['kV']} kVA={kVA}\n"
                f"~ kWRated={kWRated} kWhRated={kWhRated} kWhStored={0.2*kWhRated:.3f} State=IDLE\n"
                f"~ %EffCharge={STORAGE_EFF_CHG} %EffDischarge={STORAGE_EFF_DCH} Balanced=yes varFollowInverter=yes\n\n"
            )
            # monitors (optional)
            mon_pwr  = f"mon_{stg_name}_power"
            mon_soc  = f"mon_{stg_name}_soc"
            f_st.write(f"New Monitor.{mon_pwr} element=Storage.{stg_name} mode=1\n")
            f_st.write(f"New Monitor.{mon_soc} element=Storage.{stg_name} mode=3\n\n")
            monitor_export_lines.append(f"Export Monitors {mon_pwr}\n")
            monitor_export_lines.append(f"Export Monitors {mon_soc}\n")
            monitor_names.append(mon_pwr)
            monitor_names.append(mon_soc)

            storage_names.append(stg_name)
            storage_objnames.append(f"Storage.{stg_name}")
            storage_objnames_2.append(f"{stg_name}")
            total_storage_kW += kWRated
            n_storage += 1

        # --- Controller (only if we created storages) ---
        if n_storage > 0:
            anchor_elem = find_controller_anchor(master_dss_path)
            if not anchor_elem:
                raise RuntimeError(
                    "Could not infer StorageController anchor from Master.dss. "
                    "Expected a Monitor.m1/m2 element or an Energymeter element."
                )
            kw_target   = max(50.0, total_storage_kW * SC_KW_TARGET_FACTOR)

            f_st.write("\n! ==========================\n! STORAGE CONTROLLER\n! ==========================\n\n")
            # anchor where your feeder monitors are
            f_st.write(f"New StorageController.sc_combined element={anchor_elem}\n")
            f_st.write("~ terminal=1 modeDischarge=PeakShave ")
            f_st.write(f"kWTarget={kw_target}\n")
            f_st.write("~ modeCharge=PeakShaveLow ")
            f_st.write(f"kWTargetLow={SC_KW_TARGET_LOW}\n")
            f_st.write(f"~ %Reserve={SC_RESERVE_PCT} MonPhase=AVG EventLog=yes\n")
            # explicitly bind the fleet so DSS doesn't say "No unassigned Storage Elements"
            f_st.write("~ elementList=(" + " ".join(storage_objnames_2) + ")\n")

# Patch Master with Storage redirects + export lines
if master_dss_path:
    ml = read_lines(master_dss_path)
    new_ml = ml[:]
    if n_storage > 0 and not any(re.search(r'(?i)\bRedirect\s+Storage\.dss\b', ln) for ln in ml):
        new_ml.append("\n! Added Storage file\nRedirect Storage.dss\n")
    if monitor_export_lines:
        new_ml.append("\n! Export monitor data for storage\n")
        new_ml.extend(monitor_export_lines)
    write_lines(master_dss_path, new_ml)

# ---------------- PV (from JSON targets) ----------------
pv_targets      = ASSIGN.get("pv_targets", [])      if isinstance(ASSIGN, dict) else []
n_pv = 0
n_pv_at_min = 0
if PV_KW_PER_PEAK > 0.0 and pv_targets:
    pv_path    = os.path.join(OUT_DIR, "PVSystems.dss")
    pv_ls_path = os.path.join(OUT_DIR, "LoadShapes_PV.dss")
    with open(pv_path, "w", encoding="utf-8") as f_pv, open(pv_ls_path, "w", encoding="utf-8") as f_ls:
        f_pv.write("! PV SYSTEMS (from JSON targets)\n\n")
        f_ls.write("! PV LoadShapes\n\n")
        season = (ASSIGN.get("season") or "").lower()
        # Shape on this feeder's baseline peak day of the run's season
        profile = pv_daily_shape(CIRCUIT_NAME, season)
        prof_str = " ".join(str(v) for v in profile)

        for idx, full in enumerate(pv_targets):
            info = parsed_loads_map.get(full)
            if not info:
                print(f"[FAIL] PV target {full} is not a load in {PATH_LOADS_DSS}.")
                sys.exit(1)
            pk = peak_kw_for_load(full)
            if round(PV_KW_PER_PEAK * pk, 1) < PV_MIN_KW:
                n_pv_at_min += 1
            pv_kw   = max(PV_MIN_KW, round(PV_KW_PER_PEAK * pk, 1))
            busname = info["bus1"].split('.')[0]
            ph      = info.get("ph", "1")
            bus_str = f"{busname}.1.2.3" if ph == "3" else info["bus1"]
            ls_name = f"PVShape_{idx}"
            pv_name = f"pv_{full}"
            f_ls.write(f"New Loadshape.{ls_name} npts={IRRADIANCE_NPTS} interval={IRR_INTERVAL_H} mult=({prof_str})\n")
            f_pv.write(
                f"New PVSystem.{pv_name} phases={ph} bus1={bus_str} kV={info['kV']} "
                f"kVA={pv_kw*1.1:.1f} pmpp={pv_kw:.1f} pf=1 %Cutin=0.1 %Cutout=0.1 "
                f"daily={ls_name} irradiance=1\n\n"
            )
            n_pv += 1

    # Ensure Master includes these redirects
    if master_dss_path:
        ml = read_lines(master_dss_path)
        new_ml = ml[:]
        if n_pv > 0 and not any(re.search(r'(?i)\bRedirect\s+LoadShapes_PV\.dss\b', ln) for ln in ml):
            new_ml.append("\n! Added PV loadshape\nRedirect LoadShapes_PV.dss\n")
        if n_pv > 0 and not any(re.search(r'(?i)\bRedirect\s+PVSystems\.dss\b', ln) for ln in ml):
            new_ml.append("\n! Added PV items\nRedirect PVSystems.dss\n")
        write_lines(master_dss_path, new_ml)

print(f"Sizing -> storage at the {STORAGE_MIN_KW} kW minimum: {n_storage_at_min} of {n_storage}; "
      f"PV at the {PV_MIN_KW} kW minimum: {n_pv_at_min} of {n_pv}")
print(f"Peak kW from Loads_original.dss instead of a profile CSV: {len(PEAK_FROM_ORIGINAL_KW)}")
n_ev_own_bus_com = sum(1 for b in EV_HOSTS_OWN_BUS
                       if any(d.lower().startswith("com_") for d in base_to_daily.get(b, set())))
print(f"EV hosts without _1/_2 legs, EV on the host's own bus: {len(EV_HOSTS_OWN_BUS)} "
      f"(commercial profile: {n_ev_own_bus_com})")

# Finally, force Master to a DAILY run (96x15m), and (optionally) comment plot lines
if not retarget_master_to_daily(master_dss_path, npts=96, stepsize="15m"):
    print(f"[FAIL] No 'Solve mode=yearly stepsize=15m number=35040' line to retarget in {master_dss_path}.")
    sys.exit(1)

# One voltage Monitor per Load (every phase leg, EV loads included)
LV_MONITORS_FILE = "Monitors_LoadVoltage.dss"
LV_LOADS = []
for ln in read_lines(loads_ev_path):
    m_ld = re.match(r"(?i)^\s*New\s+Load\.(\S+)", ln)
    if m_ld:
        LV_LOADS.append(m_ld.group(1))
write_lines(os.path.join(OUT_DIR, LV_MONITORS_FILE), monitor_lines(LV_LOADS))

# ---------------- EV control (ev_control in pipeline_config.yaml) ----------------
EVC_DIR = os.path.join(CURRENT_DIR, "EVControl")
EV_VALLEY_RULES = ("valley_fill_feeder", "valley_fill_transformer")

if ACTIVATE_EV and (N_u + N_c) > 0:
    os.makedirs(EVC_DIR, exist_ok=True)
    cars_frame(cars).to_csv(os.path.join(EVC_DIR, "ev_cars.csv"), index=False)

def ev_host_leg(base):
    """The load whose bus carries the EV legs of host base (as in ev_leg_infos):
    <base>_1 when both <base>_1 and <base>_2 are loads, else base itself."""
    n1, n2 = base + "_1", base + "_2"
    return n1 if (n1 in parsed_loads_map and n2 in parsed_loads_map) else base

def first_interval(row):
    """The first non-zero interval of row, 1 to 96, or None for an all-zero row."""
    nz = np.flatnonzero(row)
    return int(nz[0]) + 1 if nz.size else None

def run_base_solve(transformer_names):
    """
    Solve the circuit without EVs in EVControl/base_solve/ and return (feeder-head P,
    {transformer name: terminal-1 P}), each 96 kW values. The folder holds the same
    .dss copies as ModifiedCircuitData/ (copy_feeder_dss; it sits one level deeper, so
    LoadShapes.dss points at ../../../profiles_use_bench/), so Loads.dss has no EV load,
    and no LoadShapes_EV.dss or Monitors_LoadVoltage.dss. Under ev_valley_base
    after_pv_storage it also holds Storage.dss, PVSystems.dss and LoadShapes_PV.dss of
    ModifiedCircuitData/. Master.dss is retargeted to the daily solve and its Redirect
    lines placed as in the main Master.dss. With transformer_names, one mode=1 Monitor
    mt_<n> per transformer (n from 1 in the given order) in Monitors_Transformers.dss,
    redirected just before the first Solve. P per step from monitor_p_kw. Stops if
    Master.dss has no yearly solve line or no Monitor m2, or the solve does not converge.
    """
    base_dir = os.path.join(EVC_DIR, "base_solve")
    os.makedirs(base_dir, exist_ok=True)
    base_master = copy_feeder_dss(base_dir, "../../../")
    if EV_VALLEY_BASE == "after_pv_storage":
        for fn in ("Storage.dss", "PVSystems.dss", "LoadShapes_PV.dss"):
            if os.path.exists(os.path.join(OUT_DIR, fn)):
                shutil.copy2(os.path.join(OUT_DIR, fn), os.path.join(base_dir, fn))
    if not base_master or not retarget_master_to_daily(base_master, npts=96, stepsize="15m"):
        print(f"[FAIL] No 'Solve mode=yearly stepsize=15m number=35040' line to retarget in the base solve Master.dss of {base_dir}.")
        sys.exit(1)
    if not re.search(r'(?im)^\s*new\s+monitor\.m2\b', read_text(base_master)):
        print(f"[FAIL] {base_master} has no Monitor.m2 for the feeder-head load of the EV base solve.")
        sys.exit(1)
    ensure_redirects_before_solve(base_master)
    if transformer_names:
        write_lines(os.path.join(base_dir, "Monitors_Transformers.dss"),
                    [f"New Monitor.mt_{n} element=Transformer.{name} terminal=1 mode=1\n"
                     for n, name in enumerate(transformer_names, start=1)])
        add_redirect_before_solve(base_master, "Monitors_Transformers.dss")
    engine = create_dss_engine()
    engine.AllowForms = False
    engine.Start(0)
    engine.Text.Command = f'Compile "{base_master}"'
    circuit = engine.ActiveCircuit
    if not bool(circuit.Solution.Converged):
        print(f"[FAIL] The EV base solve did not converge: {base_master}")
        sys.exit(1)
    def read_p(name):
        mon = circuit.Monitors
        mon.Name = name
        p = monitor_p_kw(list(mon.Header), mon.Channel)
        if len(p) != IRRADIANCE_NPTS:
            print(f"[FAIL] Monitor {name} of the EV base solve holds {len(p)} steps; expected {IRRADIANCE_NPTS}.")
            sys.exit(1)
        return p
    feeder_p = read_p("m2")
    trans_p = {name: read_p(f"mt_{n}") for n, name in enumerate(transformer_names, start=1)}
    return feeder_p, trans_p

if ACTIVATE_EV and N_c > 0 and EV_CONTROL != "uncontrolled":
    os.makedirs(EVC_DIR, exist_ok=True)
    car_curve = [""] * N_c
    starts = None
    if EV_CONTROL in EV_VALLEY_RULES:
        # ASSUMPTION: uncontrolled cars are added to the base curve as their own kW,
        # without the line losses they cause; losses at the feeder head are a small
        # share of EV kW.
        unc_total = arr_u.sum(axis=0) if N_u else np.zeros(IRRADIANCE_NPTS)
        tr_names, tr_monitor, unc_on = [], {}, {}
        if EV_CONTROL == "valley_fill_transformer":
            dss_texts = [read_text(os.path.join(OUT_DIR, fn)) for fn in dss_files]
            skipped_lines = []
            tr_map, tr_status = service_transformers(dss_texts, {n: i["bus1"] for n, i in parsed_loads_map.items()},
                                                     skipped_lines)
            print(f"Service transformers -> switched-out lines (enabled=n) left out of the map: {len(skipped_lines)}")
            n_status = {s: sum(1 for v in tr_status.values() if v == s) for s in ("one", "none", "several")}
            print(f"Service transformers -> loads with one: {n_status['one']}, none: {n_status['none']}, "
                  f"several: {n_status['several']}")
            ctl_tr = [tr_map.get(ev_host_leg(b)) for b in json_ev_ct]
            car_curve = [t if t else "feeder_fallback" for t in ctl_tr]
            tr_names = sorted({t for t in ctl_tr if t})
            tr_monitor = {t: f"mt_{n}" for n, t in enumerate(tr_names, start=1)}
            unc_tr = [tr_map.get(ev_host_leg(b)) for b in json_ev_un]
            for t in tr_names:
                rows_t = [i for i, ut in enumerate(unc_tr) if ut == t]
                unc_on[t] = arr_u[rows_t, :].sum(axis=0) if rows_t else np.zeros(IRRADIANCE_NPTS)
            print(f"Controlled cars on the feeder curve (host without one service transformer): "
                  f"{car_curve.count('feeder_fallback')} of {N_c}")
        else:
            car_curve = ["feeder"] * N_c
        feeder_p, trans_p = run_base_solve(tr_names)
        if EV_CONTROL == "valley_fill_feeder":
            arr_c, _ = valley_fill(arr_c_sessions, feeder_p + unc_total, windows_c)
        else:
            start_curves = {"feeder": feeder_p + unc_total}
            start_curves.update({t: trans_p[t] + unc_on[t] for t in tr_names})
            keys = [c if c in tr_monitor else "feeder" for c in car_curve]
            arr_c, _ = valley_fill_curves(arr_c_sessions, start_curves, keys, "feeder", windows_c)
        curve_rows = []
        for name in ["feeder"] + tr_names:
            on = [j for j in range(N_c) if name == "feeder" or car_curve[j] == name]
            base_kw = feeder_p if name == "feeder" else trans_p[name]
            unc_kw = unc_total if name == "feeder" else unc_on[name]
            ctl_kw = arr_c[on, :].sum(axis=0)
            for i in range(IRRADIANCE_NPTS):
                curve_rows.append({"curve": name, "monitor": "m2" if name == "feeder" else tr_monitor[name],
                                   "step": i + 1, "base_kw": base_kw[i], "uncontrolled_ev_kw": unc_kw[i],
                                   "controlled_ev_kw": ctl_kw[i]})
        pd.DataFrame(curve_rows).to_csv(os.path.join(EVC_DIR, "ev_control_curves.csv"), index=False)
    else:  # offpeak_start
        tariff_path = os.path.join(ROOT, "data_tariffs", f"{CFG['state']}_urdb_rate.json")
        if not os.path.exists(tariff_path):
            print(f"[FAIL] Tariff file not found: {tariff_path}. Run fetch_tou_rates.py first.")
            sys.exit(1)
        tariff = json.loads(read_text(tariff_path))
        month, _ = simulated_day(CIRCUIT_NAME, (ASSIGN.get("season") or "").lower())
        cheap_period, cheap = cheap_intervals(tariff["rate"], month)
        print(f"Off-peak start -> {tariff['rate'].get('label')} month {month}: period {cheap_period}, "
              f"{len(cheap)} cheap intervals")
        arr_c, starts = offpeak_start(arr_c_sessions, cheap, power_c, windows_c)
    car_rows = []
    for j, host in enumerate(json_ev_ct):
        s_row, c_row = arr_c_sessions[j, :], arr_c[j, :]
        # Under offpeak_start a car's charging can wrap past midnight, so its first
        # charging interval is its start, not its lowest non-zero interval.
        if starts is not None:
            first_ctl = starts[j] + 1 if starts[j] is not None else None
        else:
            first_ctl = first_interval(c_row)
        car_rows.append({
            "car": f"EVc_{j}", "host": host, "rule": EV_CONTROL, "curve": car_curve[j],
            "energy_kw_intervals": s_row.sum(), "n_intervals": int(np.count_nonzero(c_row)),
            "first_interval_uncontrolled": first_interval(s_row), "first_interval_controlled": first_ctl,
            "max_kw_uncontrolled": s_row.max(), "max_kw_controlled": c_row.max(),
            "window_on": windows_c[j] is not None, "power_kw": power_c[j],
            "delivered_kwh_controlled": c_row.sum() / 4.0,
            "leftover_kwh_controlled": (s_row.sum() - c_row.sum()) / 4.0})
    cars_df = pd.DataFrame(car_rows)
    for col in ("first_interval_uncontrolled", "first_interval_controlled"):
        cars_df[col] = cars_df[col].astype("Int64")
    cars_df.to_csv(os.path.join(EVC_DIR, "ev_control_cars.csv"), index=False)
    print(f"EV control -> {EV_CONTROL}: {N_c} controlled cars")

if ACTIVATE_EV and (N_u + N_c) > 0:
    # EV loadshapes: uncontrolled -> EVu_i, controlled -> EVc_i
    with open(loadshapes_ev_path, "w", encoding="utf-8") as f_ls:
        f_ls.write("! EV LoadShapes (uncontrolled + controlled)\n\n")
        for i in range(N_u):
            row = arr_u[i, :]
            f_ls.write(f"New Loadshape.EVu_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")
        for i in range(N_c):
            row = arr_c[i, :]
            f_ls.write(f"New Loadshape.EVc_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")

# patch Master
if master_dss_path:
    ensure_redirects_before_solve(master_dss_path)
    add_redirect_before_solve(master_dss_path, LV_MONITORS_FILE)
    assert_expected_redirects(
        master_dss_path,
        storage_present=(n_storage > 0),
        pv_present=(n_pv > 0),
        ev_present=(ACTIVATE_EV and (N_u + N_c) > 0),
    )
    '''
    ml = read_lines(master_dss_path)
    new_ml = []; ins_ls = ins_pv = False
    for ln in ml:
        new_ml.append(ln)
        if "Redirect LoadShapes.dss" in ln and not ins_ls:
            new_ml.append("\n! Added PV loadshape\nRedirect LoadShapes_PV.dss\n")
            ins_ls = True
        if "Redirect Storage.dss" in ln and not ins_pv:
            new_ml.append("\n! Added PV items\nRedirect PVSystems.dss\n")
            ins_pv = True
    if not ins_ls:
        new_ml.append("\n! Added PV loadshape at end\nRedirect LoadShapes_PV.dss\n")
    if not ins_pv:
        new_ml.append("\n! Added PV items at end\nRedirect PVSystems.dss\n")
    write_lines(master_dss_path, new_ml)
    '''

# ---------------- Compile & Solve ----------------
DSSobj   = create_dss_engine()
DSSobj.AllowForms = False
DSSstart = DSSobj.Start(0)
DSStext  = DSSobj.Text
DSScircuit = DSSobj.ActiveCircuit

if COMPILE_CIRCUIT and master_dss_path:
    '''
    PREVIOUS
    DSStext.Command = f'Compile "{master_dss_path}"'
    DSScircuit.Solution.Solve()
    print(f"Scenario (mixed EV) solved. Converged? {DSScircuit.Solution.Converged}")
    '''
    # Compile first
    DSStext.Command = f'Compile "{master_dss_path}"'

    '''
    # Force DAILY time-series: 96 x 15-minute steps
    DSStext.Command = "set mode=daily"
    DSStext.Command = "set stepsize=15m"
    DSStext.Command = "set number=96"
    DSStext.Command = "set controlmode=time"
    DSStext.Command = "reset"

    # (optional sanity prints)
    DSStext.Command = "? mode"
    print("Mode:", DSStext.Result.strip())
    DSStext.Command = "? number"
    print("Number of steps:", DSStext.Result.strip())
    DSStext.Command = "? stepsize"
    print("Stepsize:", DSStext.Result.strip())
    '''

    # Run the 96-step daily simulation
    # DSScircuit.Solution.Solve()
    converged = bool(DSScircuit.Solution.Converged)
    print(f"Converged? {converged}")

    # Master.dss's own embedded "Solve"/"Export Monitors" lines run as part of
    # the Compile above; don't just trust that -- confirm the CSVs landed.
    assert_monitor_exports(master_dss_path, monitor_names, os.path.dirname(master_dss_path))

    # Voltage at every load, read from the monitors through the engine
    if converged:
        lv_start = time.time()
        engine_loads = {str(n).lower() for n in DSScircuit.Loads.AllNames}
        if engine_loads != {n.lower() for n in LV_LOADS}:
            raise RuntimeError(f"Loads in the compiled circuit ({len(engine_loads)}) differ from "
                               f"the loads with a voltage monitor ({len(LV_LOADS)}).")
        lv_frame, lv_no_base = load_voltage_frame(read_load_monitors(DSScircuit, LV_LOADS))
        lv_frame.to_parquet(os.path.join(OUT_DIR, "load_voltages.parquet"), index=False)
        step_table(lv_frame, V_LOW_PU, V_HIGH_PU).to_csv(
            os.path.join(OUT_DIR, "load_voltage_steps.csv"), index=False)
        load_table(lv_frame, V_LOW_PU, V_HIGH_PU).to_csv(
            os.path.join(OUT_DIR, "load_voltage_loads.csv"), index=False)
        print(f"Load voltages -> {len(LV_LOADS)} load monitors, {lv_frame['step'].nunique()} steps, "
              f"{time.time() - lv_start:.2f} s")
        print(f"Loads on a bus with no base voltage (base from the load kV): {len(lv_no_base)}"
              f"{' ' + ' '.join(lv_no_base) if lv_no_base else ''}")
else:
    converged = None  # circuit was never compiled/solved


print("[OK] Finished single-scenario deploy.")
print(f"Time taken: {time.time() - START_TIME:.2f} s")
if converged is not True:
    # A non-convergent solve still writes Monitor CSVs (garbage data), and
    # run_circuits.py scores any rc==0 as a pass - without this the
    # batch runner has no way to see the solve failed.
    if converged is None:
        print("[FAIL] circuit never solved - exiting non-zero.")
    else:
        print("[FAIL] Non-convergent solve - exiting non-zero.")
    sys.exit(1)
sys.exit(0)
