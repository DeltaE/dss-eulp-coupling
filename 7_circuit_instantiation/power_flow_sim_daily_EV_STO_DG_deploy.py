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
  empty), pv.<segment>.hosts and storage.<segment>.hosts (segment residential or
  commercial), season.
- <circuit>/data_ev/: two Team-Nando EV charging profiles; under ev_cars session_rows
  the check curve of ev_inputs.yaml (pfs_ev_base_profiles).
- ev_cars, ev_home_window and ev_day in pipeline_config.yaml: the source of the EV
  cars, whether controlled charging stays inside each car's plug-in window at home, and
  the value set of ev_inputs.yaml (typical or stress).
- <repo>/7_circuit_instantiation/data_ev_cars/ev_inputs.yaml (the ev_day values) and,
  under nhts_days and session_rows, <STATE>_nhts2017_vehicle_days.csv there.
- Under ev_cars evwatts_sessions and session_rows: PIPELINE_EVWATTS_EXTRACT_DIR
  (evwatts_extract_dir in configs/local.yaml), the folder of
  evwatts_residential_l2_weekday.csv (build_evwatts_extract.py).
- <circuit>/../profiles_use_bench/<circuit>/<daily>.csv: one-column kW profiles, used
  for storage and PV sizing under pv_rule peak_ratio.
- der_sizing in pipeline_config.yaml: the PV and storage size rules and their values,
  and the storage rule, view, order, measurement and layer (der_sizing.py,
  storage_control.py).
- <work_root>/5b_profile_generation/<STATE>_parquet_and_bldgs.csv: the building of each
  host's loadshape (Feeder, Yearly_Type, Yearly_Number): bldg_id, floor area, stories,
  building type, roof area and annual electricity use (Phase 1 metadata columns).
- <work_root>/5b_profile_generation/<STATE>_peak_days.csv: each feeder's baseline
  winter and summer peak day (Phase 5b).
- With peak_day_rule: per_circuit in pipeline_config.yaml, for a circuit whose mix is
  not 100 % baseline: <work_root>/mix_days/<STATE>_circuit_days.csv, the circuit's own
  peak day per feeder, season and mix (phase mix_days), and the mix's shares in
  <work_root>/7_circuit_instantiation/mixes.<ext>, the workspace copy of the mixes
  file (ext yaml, yml or json). The mix is the part of the circuit folder name after
  _circuit_<n>_.
- PIPELINE_PV_PROFILE_FILE: the donor's SMART-DS solar file (pv_profile in
  configs/donor_registry.yaml), for the PV shape and the annual yield.
- voltage_band in pipeline_config.yaml: low_pu and high_pu for the load voltage
  summaries.
- ev_control and ev_valley_base in pipeline_config.yaml: the rule for controlled EVs
  and what the no-EV base solve of the valley rules holds.
- Under ev_control offpeak_start: <repo>/7_circuit_instantiation/data_tariffs/
  <STATE>_urdb_rate.json, the donor state's saved URDB time-of-use rate
  (fetch_tou_rates.py).

Steps
1. Builds one car per EV host with ev_cars.py, uncontrolled hosts then controlled
   hosts, each group with its own seeded draws: Level 2 (level2_kw) for the
   ev.lvl2_perc share of the group's cars, Level 1 (level1_kw) for the rest; under
   evwatts_sessions and session_rows the measured share of cars charges today (every
   car under charging_share all). Each car's uncontrolled row comes from its own EV
   WATTS session (evwatts_sessions), NHTS vehicle-day (nhts_days) or block on the check
   curve (session_rows), with its plug-in window at home. Under months season the EV
   WATTS and NHTS pools keep the season_months of the simulated season only; under
   charging_share all the NHTS pool of nhts_days and session_rows keeps class (i) days
   only.
2. Copies every .dss file of the feeder (except *_original*) into ModifiedCircuitData/
   and points LoadShapes.dss at ../../profiles_use_bench/<circuit>/.
3. Appends two EV loads per host (EVu_<host>_1 and _2, or EVc_, kW=0.5 each, pf=1)
   to ModifiedCircuitData/Loads.dss:
   on the host's legs <host>_1 and <host>_2 when both exist, else both on the host
   load itself with its own bus1, kV, conn and phases (a balanced three-phase EV load
   at a three-phase host).
4. Sizes every PV and storage host (host_sizes, der_sizing.py) and writes
   ModifiedCircuitData/der_hosts.csv. Under pv_rule roof_and_use: PV kW (Pmpp, DC) =
   min(roof coverage x roof m2 x module kW per m2, annual use share x annual use kWh /
   annual yield), the yield summed over the year of the donor's solar file; under the
   commercial coverage_rule comstock the roof cap is comstock_roof_coverage x the
   metadata roof x comstock_kw_per_m2. Storage kW = storage_kw_per_pv_kw x the host's
   PV kW under its segment's rule (also at a storage host without PV), kWh =
   storage_hours x kW. Under peak_ratio: Pmpp = max(pv_min_kw, round(pv_kw_per_peak_kw
   x peak, 1)), storage kW = max(storage_min_kw, round(storage_kw_per_peak_kw x peak,
   3)), kWh = storage_hours x kW. Inverter kVA = Pmpp / inverter loading ratio; storage
   kVA = kW / storage_pf. The low, moderate or high entry follows sizing_case.
5. Writes Storage.dss (two monitors per battery) and PVSystems.dss and
   LoadShapes_PV.dss: at a host with <host>_1 and <host>_2 legs each unit is split
   into two equal halves, one on each leg's bus (as the EV legs); at a host without
   legs, one unit on the host's own bus (.1.2.3 when three-phase). The PV shape is one
   96-point daily shape: "kW Generated (1000 kW Array)" / 1000 in the donor's SMART-DS
   solar file on this feeder's baseline peak day of the run's season, or on the
   circuit's own peak day under per_circuit (pv_daily_shape).
6. Rewrites Master.dss: replaces the yearly 15-minute 35040-step solve with
   "Solve mode=daily stepsize=15m number=96", comments out Plot lines, places the
   new Redirect lines before the first Solve, and appends Export lines for the
   storage monitors. With storage, "Set MaxControlIter=<storage_max_control_iter>"
   goes just before the first Solve (also in the EV base solve under before_cars).
7. Writes Monitors_LoadVoltage.dss: one mode=0 Monitor vl_<load> per Load in
   ModifiedCircuitData/Loads.dss (load_voltage.py), and adds
   "Redirect Monitors_LoadVoltage.dss" just before the first Solve line.
7a. Makes the controlled rows with the ev_control rule (ev_control.py). Each
   controlled car starts from its own uncontrolled row. With ev_home_window true, a
   car with a window charges only inside it (energy that does not fit is left over);
   a car without one, and every car with ev_home_window false, may use every interval.
   - uncontrolled: the session rows unchanged.
   - valley_fill_feeder: solves the circuit without EVs in EVControl/base_solve/
     (run_base_solve; buildings only, or also PV under ev_valley_base after_pv, and
     also PV and storage under storage_order before_cars), takes feeder-head P from
     Monitor m2, adds every uncontrolled
     car's kW, and places each controlled car in order of plug-in time (plugin_order)
     on the intervals where the forecast of that curve is lowest, keeping its energy
     and its number of charging intervals. The forecast (forecast_curve) adds to each
     starting curve an hourly normal error of relative size CV(W) from the
     forecast_error model of ev_inputs.yaml, drawn with rng(forecast_<curve>); each
     placed car joins the forecast.
   - water_fill_feeder: the same base, order and forecast; each car's power varies
     from 0 to its power_kw in each interval of its window, filling the lowest
     intervals toward one level (water_fill).
   - valley_fill_transformer: the same on the terminal-1 P of each car's service
     transformer (service_transformers, without switched-out enabled=n lines; one
     Monitor mt_<n> per transformer that hosts a controlled car), plus the
     uncontrolled cars on it; a car whose host has no
     service transformer uses the feeder curve. Every placed car also joins the feeder
     curve.
   - offpeak_start: on the simulated day's month row of the weekday schedule of the
     saved tariff (the cars draw weekdays), each car whose window holds a cheap
     interval (or that has no window) has a schedule time: the start of the cheap
     period it meets, moved by round(z x start_spread_min / 15) intervals
     (start_offsets, z from rng(start_spread_controlled)). It starts at the later of its
     schedule time and its plug-in, capped at the end of its window (ev_control.offpeak_row);
     a window with no cheap interval starts at plug-in. It charges at its own power until
     its energy is delivered or the window ends.
   Then writes LoadShapes_EV.dss (EVu_i, EVc_i, 4 decimals).
7b. Storage control (storage_rule, before the EV control under storage_order
   before_cars, after it otherwise; storage_control_step). Each battery watches one
   view (storage_view): the feeder-head element of Monitor m1/m2; or its host's service
   transformer (terminal 1), the feeder when the host has none; or the Line that feeds
   its host's bus from the service transformer (storage_control.feeding_lines), the
   transformer or the feeder when there is none. The measured curve of a view
   (storage_measure, storage_order, storage_layer): buildings, plus PV under
   all_placed, plus the cars under all_placed and after_cars; under add_kw a
   buildings-only solve (the EV base solve when it is one and the view is the feeder,
   else StorageControl/base_solve/) plus the kW of PV (min(Pmpp x shape, kVA)) and cars
   on the view; under solve an OpenDSS solve with those layers in
   StorageControl/measure_solve/. Targets and schedules use its forecast
   (forecast_curve, forecast_error of the ev_day value set, z from
   rng(forecast_storage_<view>)). original and simple and tuned write one
   StorageController per view (PeakShave, PeakShaveLow, %Reserve, %kWBand and %kWBandLow
   storage_kw_band_pct, DispFactor storage_disp_factor) into Storage.dss;
   schedule writes a daily loadshape per host and sets its batteries to DispMode=FOLLOW,
   computed host by host on the view's forecast, each schedule joining it.
8. Compiles Master.dss in OpenDSS (dss_engine), which runs its Solve and Export lines,
   and reads Solution.Converged.
9. When converged, reads every load Monitor through the engine (no Export lines) and
   writes the load voltage tables (per unit of the load's bus base kV), and reads each
   battery's state monitor for StorageControl/storage_targets.csv.

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
- ModifiedCircuitData/der_hosts.csv: one row per PV or storage host (attributes and
  sizes). Columns in docs/outputs.md.
- <circuit>/StorageControl/ (when the circuit has storage): storage_curves.csv (one row
  per view and step: measured, forecast error and forecast kW), storage_targets.csv
  (one row per battery: view, targets or schedule energy, and after the solve the
  energy charged and discharged and the stored energy range), storage_schedule.csv
  under schedule (one row per host and step), and base_solve/ or measure_solve/ when a
  solve was run for the measured curves.
- Console counts: the ev_loads split when used, storage and PV raised to their
  minimum under peak_ratio, peaks taken from Loads_original.dss, PV and storage hosts
  with and without legs per segment, the annual yield, and EV hosts placed on their own
  bus (with how many carry a commercial com_ profile); load monitors, steps and the
  loads whose bus has no base voltage; under valley_fill_transformer the loads with
  one, no or several service transformers and the controlled cars on the feeder curve;
  the EV WATTS and NHTS pool sizes; under the valley rules W and CV of each forecast
  curve and the curves with W <= 0 (no error); under offpeak_start the cars with a
  start offset.

Fallbacks and floors
- ev_loads_uncontrolled and ev_loads_controlled both empty: ev_loads split in half.
- Peak (peak_ratio): profile CSV maximum, else Loads_original.dss kW.
- Storage and PV minimums from der_sizing under peak_ratio.
- storage_view transformer or building: a host without the element watches the
  feeder (or its transformer, under building).

Stops (exit 1 unless noted)
- ModifiedCircuitData/ already holds files.
- No feeder subfolder.
- scenario_assignments.json missing, unparsable or not a JSON object; ev.lvl2_perc, or
  pv.<segment>.hosts or storage.<segment>.hosts, missing from it.
- der_sizing key missing or unknown in pipeline_config.yaml.
- A PV or storage host without a building row, or a building row without a needed
  column or value, in <STATE>_parquet_and_bldgs.csv; a host that is neither both legs
  nor a load of its own.
- A storage solve (base or measure) that does not converge or a view monitor without 96
  steps.
- A .dss copy into ModifiedCircuitData/ (or EVControl/base_solve/) fails, or the
  profiles_use_bench/<circuit>/ folder its LoadShapes.dss points at does not exist.
- An EV host has neither both _1 and _2 legs nor a load of its own in Loads.dss.
- PV shape: season not summer or winter, peak-day record or row missing, solar file,
  column or the 96 rows of the date missing.
- No peak kW for a storage or PV target.
- No yearly solve line to retarget in Master.dss.
- RuntimeError: storage objects exist but Master.dss has no Monitor m1/m2 or
  Energymeter; a DER Redirect line is missing; a monitor export CSV is missing; the
  loads of the compiled circuit differ from the monitored loads, or a load monitor
  does not match its load.
- voltage_band missing from pipeline_config.yaml; ev_control, ev_valley_base,
  ev_cars or ev_day missing or unknown; ev_home_window not true or false.
- EV cars: ev.effective_seed missing; under months season, no season_months for the
  run's season; under evwatts_sessions and session_rows, evwatts_extract_dir unset or
  without the extract file, or no census_division for the donor state.
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
# PV and storage sizes and storage control: der_sizing in pipeline_config.yaml
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
from ev_control import water_fill, plugin_order, forecast_curve, start_offsets
from der_sizing import (SEGMENTS, der_choice, der_number, der_value, annual_yield, roof_area_m2,
                        pv_kw_roof_and_use, storage_size)
from storage_control import simple_targets, tuned_targets, schedule, feeding_lines

# DER sizing from der_sizing in pipeline_config.yaml (repository root, one level above ROOT)
sys.path.insert(0, os.path.join(ROOT, '..'))
from pipeline_utils import load_config, load_mixes, peak_day_rule, ev_control, ev_valley_base, ev_home_window, ev_day
from pipeline_utils import ev_cars as ev_cars_source
sys.path.append(ROOT)
from heating_split import is_baseline_only
from ev_cars import (load_inputs, read_evwatts_pool, charging_share, read_nhts_pool, evwatts_cars,
                     nhts_cars, session_rows_cars, cars_frame, EVWATTS_EXTRACT_FILE, NHTS_EXTRACT_FILE)
from ev_cars import draw_months, rng as ev_rng
CFG = load_config()
PEAK_DAY_RULE = peak_day_rule(CFG)
EV_CONTROL = ev_control(CFG)
EV_VALLEY_BASE = ev_valley_base(CFG)
EV_CARS = ev_cars_source(CFG)
EV_HOME_WINDOW = ev_home_window(CFG)
EV_DAY = ev_day(CFG)
SIZING_CASE     = der_choice(CFG, "sizing_case")
PV_RULE         = {seg: der_choice(CFG, f"pv_rule_{seg}") for seg in SEGMENTS}
ROOF_SOURCE     = der_choice(CFG, "roof_area_source")
COVERAGE_RULE   = der_choice(CFG, "coverage_rule_commercial")
STORAGE_RULE    = der_choice(CFG, "storage_rule")
STORAGE_VIEW    = der_choice(CFG, "storage_view")
STORAGE_ORDER   = der_choice(CFG, "storage_order")
STORAGE_MEASURE = der_choice(CFG, "storage_measure")
STORAGE_LAYER   = der_choice(CFG, "storage_layer")
STORAGE_KW_PER_PEAK  = der_number(CFG, "storage_kw_per_peak_kw")
STORAGE_MIN_KW       = der_number(CFG, "storage_min_kw")
STORAGE_ENERGY_HOURS = der_number(CFG, "storage_hours")
PV_KW_PER_PEAK       = der_number(CFG, "pv_kw_per_peak_kw")
PV_MIN_KW            = der_number(CFG, "pv_min_kw")
PV_CUTIN_PCT         = der_number(CFG, "pv_cutin_pct")
PV_CUTOUT_PCT        = der_number(CFG, "pv_cutout_pct")
STORAGE_PF           = der_number(CFG, "storage_pf")
STORAGE_EFF_CHG      = der_number(CFG, "storage_eff_charge_pct")
STORAGE_EFF_DCH      = der_number(CFG, "storage_eff_discharge_pct")
STORAGE_START_PCT    = der_number(CFG, "storage_start_pct")
STORAGE_RESERVE_PCT  = der_number(CFG, "storage_reserve_pct")
SIMPLE_PEAK_FRACTION = der_number(CFG, "simple_peak_fraction")
SIMPLE_MEAN_FRACTION = der_number(CFG, "simple_mean_fraction")
ORIGINAL_KW_PER_STORAGE_KW = der_number(CFG, "original_kw_target_per_storage_kw")
ORIGINAL_MIN_KW            = der_number(CFG, "original_kw_target_min_kw")
ORIGINAL_LOW_KW            = der_number(CFG, "original_kw_target_low_kw")
STORAGE_MAX_CONTROL_ITER   = int(der_number(CFG, "storage_max_control_iter"))
STORAGE_KW_BAND_PCT        = der_number(CFG, "storage_kw_band_pct")
STORAGE_DISP_FACTOR        = der_number(CFG, "storage_disp_factor")
# Size parameters per segment, the sizing_case entry where a parameter has three
SIZE = {}
for _seg in SEGMENTS:
    SIZE[_seg] = {key: der_value(CFG, _seg, key, SIZING_CASE)
                  for key in ("roof_coverage", "annual_use_share", "module_kw_per_m2",
                              "inverter_loading_ratio", "storage_hours")}
SIZE["residential"]["roof_tilt_deg"] = der_value(CFG, "residential", "roof_tilt_deg")
SIZE["residential"]["ratio_small"] = SIZE["residential"]["ratio_large"] = \
    der_value(CFG, "residential", "storage_kw_per_pv_kw")
SIZE["commercial"]["roof_tilt_deg"] = None
SIZE["commercial"]["ratio_small"] = der_value(CFG, "commercial", "storage_kw_per_pv_kw_small")
SIZE["commercial"]["ratio_large"] = der_value(CFG, "commercial", "storage_kw_per_pv_kw_large")
LARGE_PV_KW = der_value(CFG, "commercial", "large_pv_kw")
COMSTOCK_COVERAGE = der_value(CFG, "commercial", "comstock_roof_coverage")
COMSTOCK_KW_PER_M2 = der_value(CFG, "commercial", "comstock_kw_per_m2")
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
if "lvl2_perc" not in (ASSIGN.get("ev") or {}):
    print(f"[FAIL] ev.lvl2_perc is missing from {ASSIGN_PATH}.")
    sys.exit(1)
lvl2_charger_perc = clamp01(ASSIGN["ev"]["lvl2_perc"])
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

def add_redirect_before_solve(master_path, filename, line=None):
    """Insert the one line "Redirect <filename>" (or line, when given) just before the
    first Solve line of master_path (at the end if there is no Solve line). Writes
    master_path."""
    ml = read_lines(master_path)
    idx = next((i for i, ln in enumerate(ml) if re.match(r'(?i)^\s*Solve\b', ln.strip())), len(ml))
    ml.insert(idx, line or f"Redirect {filename}\n")
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
    circuit's mix is not in the workspace copy of the mixes file.
    """
    if season not in ("summer", "winter"):
        print(f"[FAIL] scenario_assignments.json season is {season!r}; expected summer or winter.")
        sys.exit(1)
    peak_days_path = os.path.join(CFG["work_root"], "5b_profile_generation",
                                  f"{CFG['state']}_peak_days.csv")
    mix_name = None
    if PEAK_DAY_RULE == "per_circuit":
        m_mix = re.match(r"^.*_circuit_\d+_(.+)$", CIRCUIT_FOLDER)
        mixes_dir = os.path.join(CFG["work_root"], "7_circuit_instantiation")
        mixes_path = next((os.path.join(mixes_dir, f"mixes{ext}") for ext in (".yaml", ".yml", ".json")
                           if os.path.exists(os.path.join(mixes_dir, f"mixes{ext}"))),
                          os.path.join(mixes_dir, "mixes.yaml"))
        mixes = load_mixes(mixes_path) if os.path.exists(mixes_path) else {}
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
EV_INPUTS = load_inputs(os.path.join(ROOT, "data_ev_cars", "ev_inputs.yaml"), value_set=EV_DAY)
cars = []
if ACTIVATE_EV and (N_u + N_c) > 0:
    ev_season = (ASSIGN.get("season") or "").lower()
    try:
        ev_months = draw_months(EV_INPUTS, ev_season)
    except ValueError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    ev_months_text = "every month" if ev_months is None else f"{ev_season} months {ev_months}"
    print(f"EV cars -> ev_day {EV_DAY}: charging_share {EV_INPUTS['charging_share']}, months {EV_INPUTS['months']}")
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
        ev_pool = read_evwatts_pool(ev_extract_dir, EV_INPUTS["census_division"][ev_state], ev_months)
        ev_share_measured = charging_share(ev_pool, ev_months)
        ev_share = ev_share_measured if EV_INPUTS["charging_share"] == "measured" else 1.0
        print(f"EV cars -> EV WATTS pool: {len(ev_pool)} sessions of {EV_INPUTS['census_division'][ev_state]}, "
              f"{ev_months_text}, measured share of cars charging {ev_share_measured:.6f}, "
              f"share used {ev_share:.6f}")
    if EV_CARS in ("nhts_days", "session_rows"):
        ev_nhts_classes = ("i",) if EV_INPUTS["charging_share"] == "all" else ("i", "ii")
        ev_nhts_pool = read_nhts_pool(os.path.join(ROOT, "data_ev_cars", NHTS_EXTRACT_FILE.format(state=ev_state)),
                                      ev_months, ev_nhts_classes)
        print(f"EV cars -> NHTS pool: {len(ev_nhts_pool)} vehicle-days of {ev_state}, {ev_months_text}, "
              f"classes {', '.join(ev_nhts_classes)}")
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

# ---------------- PV and storage hosts and sizes (der_sizing in pipeline_config.yaml) ----------------
def segment_hosts(kind):
    """{segment: host bases} of kind (pv or storage) in scenario_assignments.json, from
    <kind>.<segment>.hosts. Stops if a list is missing."""
    out = {}
    for seg in SEGMENTS:
        hosts = ((ASSIGN.get(kind) or {}).get(seg) or {}).get("hosts")
        if not isinstance(hosts, list):
            print(f"[FAIL] {kind}.{seg}.hosts is missing from {ASSIGN_PATH}.")
            sys.exit(1)
        out[seg] = hosts
    return out

PV_HOSTS = segment_hosts("pv")
STORAGE_HOSTS = segment_hosts("storage")
HOST_SEGMENT = {b: seg for hosts_by_seg in (PV_HOSTS, STORAGE_HOSTS)
                for seg, hosts in hosts_by_seg.items() for b in hosts}
DER_HOST_LIST = list(dict.fromkeys(b for seg in SEGMENTS for b in PV_HOSTS[seg] + STORAGE_HOSTS[seg]))

BLDG_MAP_PATH = os.path.join(CFG["work_root"], "5b_profile_generation", f"{CFG['state']}_parquet_and_bldgs.csv")
# Building columns per segment. Commercial stories: in.number_of_stories, the numeric
# column (in.number_stories is a text bin such as over_25).
BLDG_COLUMNS = {
    "residential": {"floor": "in.sqft", "stories": "in.geometry_stories", "type": "in.geometry_building_type_acs",
                    "use": "out.electricity.total.energy_consumption.kwh", "roof": "out.params.roof_area_ft_2"},
    "commercial":  {"floor": "in.sqft", "stories": "in.number_of_stories", "type": "in.floor_area_category",
                    "use": "out.electricity.total.energy_consumption", "roof": "out.params.ext_roof_area..m2"},
}

def building_of(base, seg, bldg_map):
    """The building of host base: its first daily loadshape (sorted), <res|com>_kw_<n>...,
    and the row of bldg_map with Feeder = this feeder, Yearly_Type res or com and
    Yearly_Number n. Returns loadshape, bldg_id, floor area (ft2), stories, building
    type, annual electricity use (kWh) and the roof column (ft2 for homes, m2 for
    commercial). Stops if the loadshape, the row, a column or a value is missing."""
    shapes = sorted(base_to_daily.get(base, set()))
    m = re.match(r"^(res|com)_kw_(\d+)", shapes[0]) if shapes else None
    rows = bldg_map[(bldg_map["Feeder"] == CIRCUIT_NAME) & (bldg_map["Yearly_Type"] == m.group(1))
                    & (bldg_map["Yearly_Number"] == int(m.group(2)))] if m else bldg_map.iloc[0:0]
    if len(rows) != 1:
        print(f"[FAIL] {len(rows)} building rows for host {base} (loadshape {shapes[:1]}) in {BLDG_MAP_PATH}; expected 1.")
        sys.exit(1)
    r = rows.iloc[0]
    cols = BLDG_COLUMNS[seg]
    for col in ["bldg_id"] + list(cols.values()):
        if col not in r.index or pd.isna(r[col]):
            print(f"[FAIL] {col} missing for host {base} in {BLDG_MAP_PATH}.")
            sys.exit(1)
    return {"loadshape": shapes[0], "bldg_id": int(r["bldg_id"]), "floor_ft2": float(r[cols["floor"]]),
            "stories": float(r[cols["stories"]]), "building_type": str(r[cols["type"]]),
            "annual_use_kwh": float(r[cols["use"]]), "roof_column": float(r[cols["roof"]])}

def pv_annual_yield():
    """kWh per kW of array per year of the donor's solar file: the year of PV_KW_COLUMN
    / 1000 (per kW of array) summed times IRR_INTERVAL_H (der_sizing.annual_yield).
    Stops if the file or the column is missing."""
    pv_file = CFG["pv_profile_file"]
    if not os.path.exists(pv_file):
        print(f"[FAIL] PV profile file not found: {pv_file}")
        sys.exit(1)
    with open(pv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if PV_KW_COLUMN not in (reader.fieldnames or []):
            print(f"[FAIL] Column {PV_KW_COLUMN!r} not in {pv_file}")
            sys.exit(1)
        values = [float(r[PV_KW_COLUMN]) / 1000 for r in reader]
    return annual_yield(values, IRR_INTERVAL_H)

def host_sizes(base, seg, bldg, yld):
    """The der_hosts.csv row of host base of segment seg: the building's roof by
    floor_stories and by metadata, and PV kW (Pmpp), inverter kVA and storage kW, kWh
    and kVA under the segment's pv_rule (step 4 of the module docstring)."""
    p = SIZE[seg]
    roof_fs = roof_area_m2(seg, "floor_stories", bldg["floor_ft2"], bldg["stories"], bldg["roof_column"],
                           p["roof_tilt_deg"])
    roof_md = roof_area_m2(seg, "metadata", bldg["floor_ft2"], bldg["stories"], bldg["roof_column"])
    row = {"base": base, "segment": seg, "pv_host": base in PV_HOSTS[seg], "storage_host": base in STORAGE_HOSTS[seg],
           "loadshape": bldg["loadshape"], "bldg_id": bldg["bldg_id"], "floor_area_ft2": bldg["floor_ft2"],
           "stories": bldg["stories"], "building_type": bldg["building_type"],
           "roof_floor_stories_m2": roof_fs, "roof_metadata_m2": roof_md,
           "annual_use_kwh": bldg["annual_use_kwh"], "annual_yield_kwh_per_kw": yld,
           "pv_rule": PV_RULE[seg], "sizing_case": SIZING_CASE, "roof_area_source": None, "coverage_rule": None,
           "roof_used_m2": None, "pv_cap_roof_kw": None, "pv_cap_use_kw": None, "roof_binds": None,
           "peak_kw": None}
    if PV_RULE[seg] == "peak_ratio":
        pk = peak_kw_for_load(base)
        row["peak_kw"] = pk
        row["pv_kw"] = max(PV_MIN_KW, round(PV_KW_PER_PEAK * pk, 1))
        row["storage_kw"] = max(STORAGE_MIN_KW, round(STORAGE_KW_PER_PEAK * pk, 3))
        row["storage_kwh"] = round(row["storage_kw"] * STORAGE_ENERGY_HOURS, 3)
        row["pv_at_min"] = round(PV_KW_PER_PEAK * pk, 1) < PV_MIN_KW
        row["storage_at_min"] = round(STORAGE_KW_PER_PEAK * pk, 3) < STORAGE_MIN_KW
    else:
        if seg == "commercial" and COVERAGE_RULE == "comstock":
            source, coverage, kw_per_m2 = "metadata", COMSTOCK_COVERAGE, COMSTOCK_KW_PER_M2
        else:
            source, coverage, kw_per_m2 = ROOF_SOURCE, p["roof_coverage"], p["module_kw_per_m2"]
        roof = roof_fs if source == "floor_stories" else roof_md
        pv_kw, cap_roof, cap_use, binds = pv_kw_roof_and_use(roof, coverage, kw_per_m2, p["annual_use_share"],
                                                             bldg["annual_use_kwh"], yld)
        row.update({"roof_area_source": source, "coverage_rule": COVERAGE_RULE if seg == "commercial" else "lbnl",
                    "roof_used_m2": roof, "pv_cap_roof_kw": cap_roof, "pv_cap_use_kw": cap_use,
                    "roof_binds": binds, "pv_kw": pv_kw})
        row["storage_kw"], row["storage_kwh"] = storage_size(pv_kw, p["ratio_small"], p["ratio_large"],
                                                             LARGE_PV_KW, p["storage_hours"])
    row["pv_kva"] = row["pv_kw"] / p["inverter_loading_ratio"]
    row["storage_kva"] = row["storage_kw"] / STORAGE_PF
    return row

def der_units(base):
    """[(suffix, attributes, share)] of the PV or storage units of host base: one unit on
    each leg, <base>_1 and <base>_2, each with an equal share, when both are loads (where
    ev_leg_infos puts the EV legs); else one unit with the whole size on the host load
    base, on its own bus (.1.2.3 when three-phase). Stops if base is neither."""
    n1, n2 = base + "_1", base + "_2"
    if n1 in parsed_loads_map and n2 in parsed_loads_map:
        legs = [("_1", dict(parsed_loads_map[n1])), ("_2", dict(parsed_loads_map[n2]))]
        return [(suffix, info, 1.0 / len(legs)) for suffix, info in legs]
    host = parsed_loads_map.get(base)
    if host is None:
        print(f"[FAIL] PV or storage host {base} is not a load in {PATH_LOADS_DSS}.")
        sys.exit(1)
    info = dict(host)
    if info.get("ph") == "3":
        info["bus1"] = f"{info['bus1'].split('.')[0]}.1.2.3"
    return [("", info, 1.0)]

DER_ROWS = {}
if DER_HOST_LIST:
    bldg_map = pd.read_csv(BLDG_MAP_PATH, low_memory=False)
    annual_yield_kwh_per_kw = pv_annual_yield()
    print(f"Sizing -> annual yield {annual_yield_kwh_per_kw:.4f} kWh per kW from {CFG['pv_profile_file']}")
    for b in DER_HOST_LIST:
        seg = HOST_SEGMENT[b]
        DER_ROWS[b] = host_sizes(b, seg, building_of(b, seg, bldg_map), annual_yield_kwh_per_kw)
        DER_ROWS[b]["units"] = len(der_units(b))
        DER_ROWS[b]["legs"] = DER_ROWS[b]["units"] > 1
der_cols = ["base", "segment", "pv_host", "storage_host", "loadshape", "bldg_id", "floor_area_ft2", "stories",
            "building_type", "roof_floor_stories_m2", "roof_metadata_m2", "annual_use_kwh", "annual_yield_kwh_per_kw",
            "pv_rule", "sizing_case", "roof_area_source", "coverage_rule", "roof_used_m2", "pv_cap_roof_kw",
            "pv_cap_use_kw", "roof_binds", "peak_kw", "pv_kw", "pv_kva", "storage_kw", "storage_kwh", "storage_kva",
            "legs", "units"]
pd.DataFrame([DER_ROWS[b] for b in DER_HOST_LIST], columns=der_cols).to_csv(
    os.path.join(OUT_DIR, "der_hosts.csv"), index=False)
for seg in SEGMENTS:
    seg_rows = [r for r in DER_ROWS.values() if r["segment"] == seg]
    print(f"Sizing -> {seg}: PV hosts {sum(r['pv_host'] for r in seg_rows)}, storage hosts "
          f"{sum(r['storage_host'] for r in seg_rows)}, hosts with legs {sum(r['legs'] for r in seg_rows)} "
          f"of {len(seg_rows)}, pv_rule {PV_RULE[seg]}")

# ---------------- Storage (storage hosts of scenario_assignments.json) ----------------
storage_path = os.path.join(OUT_DIR, "Storage.dss")
monitor_export_lines = []
monitor_names = []       # bare monitor names (no class prefix), for the post-export existence check
STORAGE_UNITS = []       # one per Storage object: name, host, segment, kW, kWh, state monitor
n_storage = 0
n_zero_size = 0          # PV or storage hosts sized at 0 kW, written without an object

storage_host_list = [b for seg in SEGMENTS for b in STORAGE_HOSTS[seg]]
if storage_host_list:
    with open(storage_path, "w", encoding="utf-8") as f_st:
        f_st.write("! ==========================\n! STORAGE ELEMENTS (storage hosts)\n! ==========================\n\n")
        for base in storage_host_list:
            row = DER_ROWS[base]
            if row["storage_kw"] <= 0:  # a host whose PV rule gives 0 kW (no roof) gets no battery
                n_zero_size += 1
                continue
            for suffix, info, share in der_units(base):
                stg_name = f"storage_{base}{suffix}"
                kw_u, kwh_u, kva_u = row["storage_kw"] * share, row["storage_kwh"] * share, row["storage_kva"] * share
                f_st.write(
                    f"New Storage.{stg_name} phases={info['ph']} bus1={info['bus1']} kV={info['kV']} kVA={kva_u:.4f}\n"
                    f"~ kWRated={kw_u:.4f} kWhRated={kwh_u:.4f} %stored={STORAGE_START_PCT} "
                    f"%reserve={STORAGE_RESERVE_PCT} State=IDLE\n"
                    f"~ %EffCharge={STORAGE_EFF_CHG} %EffDischarge={STORAGE_EFF_DCH} Balanced=yes varFollowInverter=yes\n\n"
                )
                mon_pwr  = f"mon_{stg_name}_power"
                mon_soc  = f"mon_{stg_name}_soc"
                f_st.write(f"New Monitor.{mon_pwr} element=Storage.{stg_name} mode=1\n")
                f_st.write(f"New Monitor.{mon_soc} element=Storage.{stg_name} mode=3\n\n")
                monitor_export_lines.append(f"Export Monitors {mon_pwr}\n")
                monitor_export_lines.append(f"Export Monitors {mon_soc}\n")
                monitor_names.append(mon_pwr)
                monitor_names.append(mon_soc)
                STORAGE_UNITS.append({"name": stg_name, "host": base, "segment": row["segment"],
                                      "kw": float(f"{kw_u:.4f}"), "kwh": float(f"{kwh_u:.4f}"), "soc_monitor": mon_soc})
                n_storage += 1

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

# ---------------- PV (PV hosts of scenario_assignments.json) ----------------
pv_host_list = [b for seg in SEGMENTS for b in PV_HOSTS[seg]]
PV_PROFILE = None
n_pv = 0
if pv_host_list:
    pv_path    = os.path.join(OUT_DIR, "PVSystems.dss")
    pv_ls_path = os.path.join(OUT_DIR, "LoadShapes_PV.dss")
    with open(pv_path, "w", encoding="utf-8") as f_pv, open(pv_ls_path, "w", encoding="utf-8") as f_ls:
        f_pv.write("! PV SYSTEMS (PV hosts)\n\n")
        f_ls.write("! PV LoadShapes\n\n")
        season = (ASSIGN.get("season") or "").lower()
        # Shape on this feeder's baseline peak day of the run's season
        PV_PROFILE = pv_daily_shape(CIRCUIT_NAME, season)
        prof_str = " ".join(str(v) for v in PV_PROFILE)

        for base in pv_host_list:
            row = DER_ROWS[base]
            if row["pv_kw"] <= 0:  # no roof: no array
                n_zero_size += 1
                continue
            for suffix, info, share in der_units(base):
                ls_name = f"PVShape_{n_pv}"
                pv_name = f"pv_{base}{suffix}"
                f_ls.write(f"New Loadshape.{ls_name} npts={IRRADIANCE_NPTS} interval={IRR_INTERVAL_H} mult=({prof_str})\n")
                f_pv.write(
                    f"New PVSystem.{pv_name} phases={info['ph']} bus1={info['bus1']} kV={info['kV']} "
                    f"kVA={row['pv_kva'] * share:.4f} pmpp={row['pv_kw'] * share:.4f} pf=1 "
                    f"%Cutin={PV_CUTIN_PCT} %Cutout={PV_CUTOUT_PCT} daily={ls_name} irradiance=1\n\n"
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

print(f"Sizing -> PV or storage hosts sized at 0 kW, without an object: {n_zero_size}")
if any(PV_RULE[seg] == "peak_ratio" for seg in SEGMENTS):
    print(f"Sizing -> storage at the {STORAGE_MIN_KW} kW minimum: "
          f"{sum(1 for b in storage_host_list if DER_ROWS[b].get('storage_at_min'))} of {len(storage_host_list)}; "
          f"PV at the {PV_MIN_KW} kW minimum: {sum(1 for b in pv_host_list if DER_ROWS[b].get('pv_at_min'))} "
          f"of {len(pv_host_list)}")
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
EV_VALLEY_RULES = ("valley_fill_feeder", "valley_fill_transformer", "water_fill_feeder")

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
    and no LoadShapes_EV.dss or Monitors_LoadVoltage.dss. Under ev_valley_base after_pv
    it also holds PVSystems.dss and LoadShapes_PV.dss of ModifiedCircuitData/, and under
    storage_order before_cars those and Storage.dss (with its storage control). Master.dss
    is retargeted to the daily solve and its Redirect
    lines placed as in the main Master.dss. With transformer_names, one mode=1 Monitor
    mt_<n> per transformer (n from 1 in the given order) in Monitors_Transformers.dss,
    redirected just before the first Solve. P per step from monitor_p_kw. Stops if
    Master.dss has no yearly solve line or no Monitor m2, or the solve does not converge.
    """
    base_dir = os.path.join(EVC_DIR, "base_solve")
    os.makedirs(base_dir, exist_ok=True)
    base_master = copy_feeder_dss(base_dir, "../../../")
    if EV_VALLEY_BASE == "after_pv" or STORAGE_ORDER == "before_cars":
        for fn in ("PVSystems.dss", "LoadShapes_PV.dss") + (("Storage.dss",) if STORAGE_ORDER == "before_cars" else ()):
            if os.path.exists(os.path.join(OUT_DIR, fn)):
                shutil.copy2(os.path.join(OUT_DIR, fn), os.path.join(base_dir, fn))
    if not base_master or not retarget_master_to_daily(base_master, npts=96, stepsize="15m"):
        print(f"[FAIL] No 'Solve mode=yearly stepsize=15m number=35040' line to retarget in the base solve Master.dss of {base_dir}.")
        sys.exit(1)
    if not re.search(r'(?im)^\s*new\s+monitor\.m2\b', read_text(base_master)):
        print(f"[FAIL] {base_master} has no Monitor.m2 for the feeder-head load of the EV base solve.")
        sys.exit(1)
    ensure_redirects_before_solve(base_master)
    if STORAGE_ORDER == "before_cars" and n_storage > 0:
        add_redirect_before_solve(base_master, None, f"Set MaxControlIter={STORAGE_MAX_CONTROL_ITER}\n")
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


# ---------------- Storage control (storage_rule in der_sizing) ----------------
STC_DIR = os.path.join(CURRENT_DIR, "StorageControl")
EV_BASE_FEEDER_P = None    # feeder-head P of the EV base solve, when it runs
STORAGE_TARGET_ROWS = []   # one per Storage object, completed after the solve
STORAGE_FORECAST_DRAWS = []

def view_solve(name, layers, monitors):
    """Solve the circuit in StorageControl/<name>/ and return {key: P (96 kW)} of one
    mode=1 Monitor ms_<n> per (key, element, terminal) of monitors. The folder holds the
    .dss copies of copy_feeder_dss (buildings only); layer "pv" adds PVSystems.dss and
    LoadShapes_PV.dss of ModifiedCircuitData/, layer "cars" its Loads.dss (with the EV
    loads) and LoadShapes_EV.dss. Master.dss is retargeted to the daily solve, its
    Redirect lines placed as in the main Master.dss and Monitors_StorageViews.dss
    redirected before the first Solve. Stops if there is no yearly solve line, the solve
    does not converge or a monitor does not hold 96 steps."""
    sdir = os.path.join(STC_DIR, name)
    os.makedirs(sdir, exist_ok=True)
    smaster = copy_feeder_dss(sdir, "../../../")
    files = (["PVSystems.dss", "LoadShapes_PV.dss"] if "pv" in layers else []) + \
            ([os.path.basename(loads_ev_path), "LoadShapes_EV.dss"] if "cars" in layers else [])
    for fn in files:
        if os.path.exists(os.path.join(OUT_DIR, fn)):
            shutil.copy2(os.path.join(OUT_DIR, fn), os.path.join(sdir, fn))
    if not smaster or not retarget_master_to_daily(smaster, npts=96, stepsize="15m"):
        print(f"[FAIL] No 'Solve mode=yearly stepsize=15m number=35040' line to retarget in {sdir}.")
        sys.exit(1)
    ensure_redirects_before_solve(smaster)
    write_lines(os.path.join(sdir, "Monitors_StorageViews.dss"),
                [f"New Monitor.ms_{n} element={el} terminal={t} mode=1\n"
                 for n, (_, el, t) in enumerate(monitors, start=1)])
    add_redirect_before_solve(smaster, "Monitors_StorageViews.dss")
    engine = create_dss_engine()
    engine.AllowForms = False
    engine.Start(0)
    engine.Text.Command = f'Compile "{smaster}"'
    circuit = engine.ActiveCircuit
    if not bool(circuit.Solution.Converged):
        print(f"[FAIL] The storage {name} did not converge: {smaster}")
        sys.exit(1)
    out = {}
    for n, (key, _, _) in enumerate(monitors, start=1):
        mon = circuit.Monitors
        mon.Name = f"ms_{n}"
        p = monitor_p_kw(list(mon.Header), mon.Channel)
        if len(p) != IRRADIANCE_NPTS:
            print(f"[FAIL] Monitor ms_{n} of the storage {name} holds {len(p)} steps; expected {IRRADIANCE_NPTS}.")
            sys.exit(1)
        out[key] = np.asarray(p, dtype=float)
    return out

def storage_views():
    """Return (views, host_view, host_keys). views {key: (element, terminal)}: "feeder"
    is the element of Monitor m1/m2 of Master.dss (find_controller_anchor), terminal 1.
    Under storage_view transformer, "transformer_<t>" is Transformer.<t>, terminal 1, for
    each service transformer of a storage host (service_transformers on the host's
    leg, ev_host_leg). Under building, "building_<host>" is the Line that feeds the
    host's bus (feeding_lines), else the host's transformer. host_view {storage host:
    key}; a host without its element watches the feeder. host_keys(base) gives every
    view key whose element carries the flow of host base."""
    anchor = find_controller_anchor(master_dss_path)
    if not anchor:
        raise RuntimeError("Could not infer StorageController anchor from Master.dss. "
                           "Expected a Monitor.m1/m2 element or an Energymeter element.")
    views = {"feeder": (anchor, 1)}
    host_view = {u["host"]: "feeder" for u in STORAGE_UNITS}
    tr_map = {}
    if STORAGE_VIEW != "feeder":
        dss_texts = [read_text(os.path.join(OUT_DIR, fn)) for fn in dss_files]
        tr_map, _ = service_transformers(dss_texts, {n: i["bus1"] for n, i in parsed_loads_map.items()})
        lines = {}
        if STORAGE_VIEW == "building":
            lines = feeding_lines(dss_texts, {h: (parsed_loads_map[ev_host_leg(h)]["bus1"], tr_map.get(ev_host_leg(h)))
                                              for h in host_view})
        for h in host_view:
            t = tr_map.get(ev_host_leg(h))
            if lines.get(h):
                host_view[h] = f"building_{h}"
                views[host_view[h]] = (f"Line.{lines[h][0]}", lines[h][1])
            elif t:
                host_view[h] = f"transformer_{t}"
                views[host_view[h]] = (f"Transformer.{t}", 1)
        print(f"Storage view -> {STORAGE_VIEW}: {len(views) - 1} {STORAGE_VIEW} views, "
              f"{sum(1 for v in host_view.values() if v == 'feeder')} hosts on the feeder view")

    def host_keys(base):
        t = tr_map.get(ev_host_leg(base)) if base in parsed_loads_map or base + "_1" in parsed_loads_map else None
        return [k for k in ("feeder", f"transformer_{t}" if t else None, f"building_{base}") if k in views]
    return views, host_view, host_keys

def measured_curves(views, host_keys, with_cars):
    """{view key: measured kW (96)}: buildings, plus PV under storage_measure all_placed,
    plus the cars when with_cars and all_placed. Under storage_layer solve with a layer
    to add: view_solve("measure_solve") with the layers in. Else a buildings-only base:
    the EV base solve's feeder-head P when the only view is the feeder and that solve
    holds buildings only, otherwise view_solve("base_solve"); then each PV host adds
    min(Pmpp x shape, kVA) and each car its row to every view that carries its host."""
    pv_on = STORAGE_MEASURE == "all_placed" and n_pv > 0
    cars_on = STORAGE_MEASURE == "all_placed" and with_cars and (N_u + N_c) > 0
    keys = list(views)
    monitors = [(k, views[k][0], views[k][1]) for k in keys]
    if STORAGE_LAYER == "solve" and (pv_on or cars_on):
        return view_solve("measure_solve", [n for n, on in (("pv", pv_on), ("cars", cars_on)) if on], monitors)
    if keys == ["feeder"] and EV_BASE_FEEDER_P is not None:
        curves = {"feeder": np.asarray(EV_BASE_FEEDER_P, dtype=float).copy()}
    else:
        curves = view_solve("base_solve", [], monitors)
    if pv_on:
        shape = np.asarray(PV_PROFILE, dtype=float)
        for b in pv_host_list:
            kw = np.minimum(DER_ROWS[b]["pv_kw"] * shape, DER_ROWS[b]["pv_kva"])
            for k in host_keys(b):
                curves[k] = curves[k] - kw
    if cars_on:
        for rows, hosts in ((arr_u, json_ev_un), (arr_c, json_ev_ct)):
            for j, b in enumerate(hosts):
                for k in host_keys(b):
                    curves[k] = curves[k] + rows[j, :]
    return curves

def storage_control_step(with_cars):
    """Step 7b of the module docstring: views, measured curves and their forecasts,
    then the controller or the schedules of storage_rule, appended to Storage.dss.
    Writes StorageControl/storage_curves.csv (and storage_schedule.csv under schedule);
    STORAGE_TARGET_ROWS gets one row per battery."""
    os.makedirs(STC_DIR, exist_ok=True)
    seed = (ASSIGN.get("ev") or {}).get("effective_seed")
    if seed is None:
        print(f"[FAIL] ev.effective_seed is missing from {ASSIGN_PATH}.")
        sys.exit(1)
    views, host_view, host_keys = storage_views()
    curves = measured_curves(views, host_keys, with_cars)
    fc_model = EV_INPUTS["forecast_error"]
    dt = IRR_INTERVAL_H
    eff_c, eff_d = STORAGE_EFF_CHG / 100.0, STORAGE_EFF_DCH / 100.0
    start, reserve = STORAGE_START_PCT / 100.0, STORAGE_RESERVE_PCT / 100.0
    text = [f"\n! ==========================\n! STORAGE CONTROL (storage_rule {STORAGE_RULE}, "
            f"storage_view {STORAGE_VIEW})\n! ==========================\n\n"]
    curve_rows, sched_rows = [], []
    n_sched = 0
    for n_view, key in enumerate(views, start=1):
        units = [u for u in STORAGE_UNITS if host_view[u["host"]] == key]
        if not units:
            continue
        draw = f"forecast_storage_{key}"
        z = ev_rng(draw, seed).standard_normal(24)
        fc, err, fc_w, fc_cv = forecast_curve(curves[key], fc_model, EV_INPUTS["forecast_models"][fc_model], z)
        STORAGE_FORECAST_DRAWS.append(draw)
        element, terminal = views[key]
        for i in range(IRRADIANCE_NPTS):
            curve_rows.append({"view": key, "element": element, "terminal": terminal, "step": i + 1,
                               "measured_kw": curves[key][i], "forecast_error_kw": err[i], "forecast_kw": fc[i]})
        kw_view, kwh_view = sum(u["kw"] for u in units), sum(u["kwh"] for u in units)
        base_row = {"view": key, "element": element, "terminal": terminal, "rule": STORAGE_RULE,
                    "view_kw": kw_view, "view_kwh": kwh_view, "forecast_draw": draw,
                    "kw_target": None, "kw_target_low": None, "schedule_discharge_kwh": None}
        if STORAGE_RULE == "schedule":
            cur = fc.copy()
            for host in dict.fromkeys(u["host"] for u in units):
                h_units = [u for u in units if u["host"] == host]
                h_kw, h_kwh = sum(u["kw"] for u in h_units), sum(u["kwh"] for u in h_units)
                net, energy, x = schedule(cur, h_kw, h_kwh, start, reserve, eff_c, eff_d, dt)
                cur = cur - net
                shape = f"StoSched_{n_sched}"
                n_sched += 1
                text.append(f"New Loadshape.{shape} npts={IRRADIANCE_NPTS} interval={IRR_INTERVAL_H} "
                            f"mult=({' '.join(f'{v / h_kw:.6f}' for v in net)})\n")
                for u in h_units:
                    text.append(f"Edit Storage.{u['name']} DispMode=FOLLOW daily={shape}\n")
                    STORAGE_TARGET_ROWS.append({**base_row, "battery": u["name"], "host": host,
                                                "segment": u["segment"], "kw_rated": u["kw"], "kwh_rated": u["kwh"],
                                                "schedule_discharge_kwh": x * u["kw"] / h_kw})
                for i in range(IRRADIANCE_NPTS):
                    sched_rows.append({"view": key, "host": host, "loadshape": shape, "step": i + 1,
                                       "net_kw": net[i], "stored_kwh_start": energy[i], "stored_kwh_end": energy[i + 1]})
            text.append("\n")
            continue
        if STORAGE_RULE == "original":
            target, low = max(ORIGINAL_MIN_KW, ORIGINAL_KW_PER_STORAGE_KW * kw_view), ORIGINAL_LOW_KW
        elif STORAGE_RULE == "simple":
            target, low = simple_targets(fc, SIMPLE_PEAK_FRACTION, SIMPLE_MEAN_FRACTION)
        else:
            target, low, _, _, _ = tuned_targets(fc, kw_view, kwh_view, reserve, eff_c, eff_d, dt)
        text.append(f"New StorageController.sc_{n_view} element={element} terminal={terminal}\n"
                    f"~ modeDischarge=PeakShave kWTarget={target:.4f}\n"
                    f"~ modeCharge=PeakShaveLow kWTargetLow={low:.4f}\n"
                    f"~ %Reserve={STORAGE_RESERVE_PCT} MonPhase=AVG EventLog=yes\n"
                    f"~ %kWBand={STORAGE_KW_BAND_PCT} %kWBandLow={STORAGE_KW_BAND_PCT} "
                    f"DispFactor={STORAGE_DISP_FACTOR}\n"
                    f"~ elementList=({' '.join(u['name'] for u in units)})\n\n")
        for u in units:
            STORAGE_TARGET_ROWS.append({**base_row, "battery": u["name"], "host": u["host"], "segment": u["segment"],
                                        "kw_rated": u["kw"], "kwh_rated": u["kwh"],
                                        "kw_target": float(f"{target:.4f}"), "kw_target_low": float(f"{low:.4f}")})
    with open(storage_path, "a", encoding="utf-8") as f_st:
        f_st.writelines(text)
    pd.DataFrame(curve_rows).to_csv(os.path.join(STC_DIR, "storage_curves.csv"), index=False)
    if STORAGE_RULE == "schedule":
        pd.DataFrame(sched_rows).to_csv(os.path.join(STC_DIR, "storage_schedule.csv"), index=False)
    print(f"Storage control -> {STORAGE_RULE}, view {STORAGE_VIEW}, order {STORAGE_ORDER}, measure "
          f"{STORAGE_MEASURE}, layer {STORAGE_LAYER}: {len(STORAGE_TARGET_ROWS)} batteries, "
          f"{len(STORAGE_FORECAST_DRAWS)} views with storage")

if n_storage > 0 and STORAGE_ORDER == "before_cars":
    storage_control_step(with_cars=False)

if ACTIVATE_EV and N_c > 0 and EV_CONTROL != "uncontrolled":
    os.makedirs(EVC_DIR, exist_ok=True)
    car_curve = [""] * N_c
    starts = None
    placement_rank = [None] * N_c
    shifts = [None] * N_c
    if EV_CONTROL in EV_VALLEY_RULES:
        # Controlled cars are placed in order of plug-in time from 04:00 (plugin_order)
        order = plugin_order([c["plug_minute"] if c["charges_today"] else None for c in cars_c])
        for rank, j in enumerate(order, start=1):
            placement_rank[j] = rank
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
        if EV_VALLEY_BASE == "buildings_only" and STORAGE_ORDER != "before_cars":
            EV_BASE_FEEDER_P = feeder_p
        start_curves = {"feeder": feeder_p + unc_total}
        start_curves.update({t: trans_p[t] + unc_on[t] for t in tr_names})
        # The aggregator places cars on a forecast of each starting curve (forecast_curve)
        fc_model = EV_INPUTS["forecast_error"]
        fc_curves, fc_error, n_no_error = {}, {}, 0
        for name, curve in start_curves.items():
            z = ev_rng(f"forecast_{name}", ev_effective_seed).standard_normal(24)
            fc_curves[name], fc_error[name], fc_w, fc_cv = forecast_curve(
                curve, fc_model, EV_INPUTS["forecast_models"][fc_model], z)
            if fc_cv is None:
                n_no_error += 1
                print(f"Forecast -> {name}: W {fc_w:.4f} kW <= 0, no forecast error")
            else:
                print(f"Forecast -> {name}: {fc_model}, W {fc_w:.4f} kW, CV {fc_cv:.4f} %")
        print(f"Forecast -> curves with W <= 0 (no error): {n_no_error} of {len(start_curves)}")
        if EV_CONTROL == "valley_fill_feeder":
            arr_c, _ = valley_fill(arr_c_sessions, fc_curves["feeder"], windows_c, order)
        elif EV_CONTROL == "water_fill_feeder":
            arr_c, _ = water_fill(arr_c_sessions, fc_curves["feeder"], power_c, windows_c, order)
        else:
            keys = [c if c in tr_monitor else "feeder" for c in car_curve]
            arr_c, _ = valley_fill_curves(arr_c_sessions, fc_curves, keys, "feeder", windows_c, order)
        curve_rows = []
        for name in ["feeder"] + tr_names:
            on = [j for j in range(N_c) if name == "feeder" or car_curve[j] == name]
            base_kw = feeder_p if name == "feeder" else trans_p[name]
            unc_kw = unc_total if name == "feeder" else unc_on[name]
            ctl_kw = arr_c[on, :].sum(axis=0)
            for i in range(IRRADIANCE_NPTS):
                curve_rows.append({"curve": name, "monitor": "m2" if name == "feeder" else tr_monitor[name],
                                   "step": i + 1, "base_kw": base_kw[i], "uncontrolled_ev_kw": unc_kw[i],
                                   "controlled_ev_kw": ctl_kw[i], "forecast_error_kw": fc_error[name][i]})
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
        z_spread = ev_rng("start_spread_controlled", ev_effective_seed).standard_normal(N_c)
        shifts = start_offsets(arr_c_sessions, cheap, windows_c, z_spread, EV_INPUTS["start_spread_min"])
        print(f"Off-peak start -> start spread {EV_INPUTS['start_spread_min']} min: "
              f"{sum(d is not None for d in shifts)} of {N_c} cars with a start offset")
        arr_c, starts = offpeak_start(arr_c_sessions, cheap, power_c, windows_c, shifts)
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
            "leftover_kwh_controlled": (s_row.sum() - c_row.sum()) / 4.0,
            "placement_order": placement_rank[j], "start_offset_intervals": shifts[j]})
    cars_df = pd.DataFrame(car_rows)
    for col in ("first_interval_uncontrolled", "first_interval_controlled", "placement_order",
                "start_offset_intervals"):
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

if n_storage > 0 and STORAGE_ORDER != "before_cars":
    storage_control_step(with_cars=(STORAGE_ORDER == "after_cars"))

# patch Master
if master_dss_path:
    ensure_redirects_before_solve(master_dss_path)
    add_redirect_before_solve(master_dss_path, LV_MONITORS_FILE)
    if n_storage > 0:
        add_redirect_before_solve(master_dss_path, None, f"Set MaxControlIter={STORAGE_MAX_CONTROL_ITER}\n")
    assert_expected_redirects(
        master_dss_path,
        storage_present=(n_storage > 0),
        pv_present=(n_pv > 0),
        ev_present=(ACTIVATE_EV and (N_u + N_c) > 0),
    )

# ---------------- Compile & Solve ----------------
DSSobj   = create_dss_engine()
DSSobj.AllowForms = False
DSSobj.Start(0)
DSStext  = DSSobj.Text
DSScircuit = DSSobj.ActiveCircuit

if COMPILE_CIRCUIT and master_dss_path:
    # Compile first
    DSStext.Command = f'Compile "{master_dss_path}"'


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

    # Each battery's state monitor (mode=3): energy charged and discharged, stored energy range
    if STORAGE_TARGET_ROWS:
        soc_mon = {u["name"]: u["soc_monitor"] for u in STORAGE_UNITS}
        for row in STORAGE_TARGET_ROWS:
            mon = DSScircuit.Monitors
            mon.Name = soc_mon[row["battery"]]
            chan = {str(h).strip().lower(): i for i, h in enumerate(mon.Header, start=1)}
            kwh = np.asarray(mon.Channel(chan["kwh"]), dtype=float)
            row.update({"charged_kwh": float(np.sum(mon.Channel(chan["kwin"]))) * IRR_INTERVAL_H,
                        "discharged_kwh": float(np.sum(mon.Channel(chan["kwout"]))) * IRR_INTERVAL_H,
                        "stored_kwh_start": row["kwh_rated"] * STORAGE_START_PCT / 100.0,
                        "stored_kwh_end": float(kwh[-1]), "stored_kwh_min": float(kwh.min()),
                        "stored_kwh_max": float(kwh.max())})
    if n_storage > 0:
        pd.DataFrame(STORAGE_TARGET_ROWS).to_csv(os.path.join(STC_DIR, "storage_targets.csv"), index=False)
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
