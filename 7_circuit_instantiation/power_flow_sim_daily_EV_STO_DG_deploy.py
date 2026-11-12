# -*- coding: utf-8 -*-
"""
power_flow_sim_daily_EV_STO_DG_deploy.py
----------------------------------------
Build and solve one DER scenario of one prepared circuit as a 96-step daily run, or,
with horizon_days above 1 in pipeline_config.yaml, as one continuous run of 96 x
horizon_days steps over the window of days around the simulated day (section "Window
of more than one day" below). The steps below describe horizon_days 1.

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
- ev_cars, ev_home_window, ev_day and ev_work_share_case in pipeline_config.yaml: the
  source of the EV cars, whether controlled charging stays inside each car's plug-in
  window, the value set of ev_inputs.yaml (typical or stress) and the share of the
  charging cars that charge at a workplace (low, moderate or high of work_share).
- <repo>/7_circuit_instantiation/data_ev_cars/ev_inputs.yaml (the ev_day values) and,
  under nhts_days and session_rows, <STATE>_nhts2017_vehicle_days.csv there (its
  work_pieces give the work cars of nhts_days their windows).
- Under ev_cars evwatts_sessions and session_rows: PIPELINE_EVWATTS_EXTRACT_DIR
  (evwatts_extract_dir in configs/local.yaml), the folder of
  evwatts_residential_l2_weekday.csv (build_evwatts_extract.py) and, under
  evwatts_sessions with a work share above 0, of evwatts_office_l2_weekday.csv
  (build_evwatts_extract.py --venue office).
- <feeder>/Buscoords.dss (copied into ModifiedCircuitData/): the coordinates of the
  buses in EVControl/ev_places.csv.
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
  not 100 % baseline, and with given, for every circuit:
  <work_root>/mix_days/<STATE>_circuit_days.csv, the circuit's day per feeder, season
  and mix (phase mix_days: its own peak day or the given day), and the mix's shares in
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
   only. Under evwatts_sessions and nhts_days, with ev_work_share_case above low and a
   commercial load in the circuit, work_cars moves the work share of each group's
   charging cars to a workplace (ev_cars.py): each work car draws a commercial load of
   the circuit (its office) and charges its whole day's energy there, from a Business
   Office session of the EV WATTS office extract or from an NHTS weekday with a stop at
   work, whose window is the time parked at work (in pieces when the car leaves and
   returns). session_rows keeps every car at home.
2. Copies every .dss file of the feeder (except *_original*) into ModifiedCircuitData/
   and points LoadShapes.dss at ../../profiles_use_bench/<circuit>/.
3. Appends two EV loads per car (EVu_<host>_1 and _2, or EVc_, kW=0.5 each, pf=1)
   to ModifiedCircuitData/Loads.dss:
   on the host's legs <host>_1 and <host>_2 when both exist, else both on the host
   load itself with its own bus1, kV, conn and phases (a balanced three-phase EV load
   at a three-phase host). A work car's two loads are EVu_w<i>_<office>_1 and _2 (or
   EVc_w<j>_) on the office's legs or own bus in the same way, with the car's daily
   shape EVu_<i> (or EVc_<j>).
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
   its host's bus from the service transformer (storage_control.feeding_lines), one view
   for the hosts that Line feeds, the transformer or the feeder when there is none. The measured curve of a view
   (storage_measure, storage_order, storage_layer): buildings, plus PV under
   all_placed, plus the cars under all_placed and after_cars; under add_kw a
   buildings-only solve (the EV base solve when it is one and the view is the feeder,
   else StorageControl/base_solve/) plus the kW of PV (min(Pmpp x shape, kVA)) and cars
   on the view; under solve an OpenDSS solve with those layers in
   StorageControl/measure_solve/. Targets and schedules use its forecast
   (forecast_curve, forecast_error of the ev_day value set, z from
   rng(forecast_storage_<view>)). simple and tuned write one
   StorageController per view (PeakShave, PeakShaveLow, %Reserve, %kWBand and %kWBandLow
   storage_kw_band_pct, DispFactor storage_disp_factor) into Storage.dss;
   schedule writes a daily loadshape per host and sets its batteries to DispMode=FOLLOW,
   computed host by host on the view's forecast, each schedule joining it; under
   schedule_start best from the start of SCHEDULE_START_PCTS whose plan leaves the
   lowest maximum (best_start), written as the batteries' %stored.
8. Compiles Master.dss in OpenDSS (dss_engine), which runs its Solve and Export lines,
   and reads Solution.Converged.
9. When converged, reads every load Monitor through the engine (no Export lines) and
   writes the load voltage tables (per unit of the load's bus base kV), and reads each
   battery's state monitor for StorageControl/storage_targets.csv.

Window of more than one day (horizon_days above 1)
- The window: pipeline_utils.window_dates on the simulated day (day X) of the circuit,
  horizon_days consecutive dates of the 2018 calendar of the building curves, kept
  inside the season. <circuit>/window_days.csv records it (date, weekday, day_type,
  day_index, day_x, holiday). Every loadshape and every solve has 96 x horizon_days
  steps; the building profiles already hold the window (Phases 5b to 7b).
- PV: each day's shape comes from its own month and day of the solar file.
- Sizes under peak_ratio: a host's peak is that of day X's 96 values.
- EV cars (ev_cars.window_group, plan_car): the records of step 1 stay the cars of day
  X (EVControl/ev_cars.csv, ev_places.csv). Each car keeps its drawn session and
  charger; under evwatts_sessions and nhts_days it also draws one weekend session or
  vehicle-day for the Saturdays and Sundays of the window. Under charging_share
  measured a seeded draw with the measured share of the day's type decides whether the
  car charges on each day other than day X; under all every car charges every day;
  under nhts_days a car charges on every day whose vehicle-day is class (i). Day X
  keeps the draw of the one-day run, a weekday session, whatever its date. A car's
  window runs on the window's timeline: charging past midnight lands on the next day,
  and day 1 receives the part after midnight of the session of the day before the
  window. Energy that does not fit in a window is charged on the next evening without
  a drawn session; energy still owed at the end is reported in
  EVControl/ev_car_days.csv. Work cars charge at their office on weekdays and at home
  on weekend days, where they have two more loads, EVu_<host>_1 and _2 (or EVc_), with
  the shape EVu_<i>h (or EVc_<j>h).
- EV control (window_ev_control): one base solve over the window; ev_valley_day
  own_day or peak_day picks the forecast each day's cars see, and the tariff rows of
  offpeak_start follow each day's month and day type.
- Storage: simple and tuned take their targets from the whole window's forecast.
  schedule writes one loadshape of 96 x horizon_days points per host
  (storage_control.schedule_days), from the start of schedule_start: best (the start
  of the one-day rule on day X's forecast), best_window (the start that leaves the
  lowest maximum of the window) or fixed. StorageControl/storage_midnights.csv holds,
  per battery and day, the planned and the monitored stored energy at midnight.
- The per-step tables (ev_control_curves.csv, storage_curves.csv, storage_schedule.csv,
  load_voltage_steps.csv, load_voltages.parquet) get date, day_index and day_type
  after their step column; ev_control_curves.csv also gets forecast_kw.

Outputs
- ModifiedCircuitData/: copied and edited .dss files, LoadShapes_EV.dss, Storage.dss,
  PVSystems.dss, LoadShapes_PV.dss and the monitor CSVs OpenDSS exports.
- ModifiedCircuitData/Monitors_LoadVoltage.dss, load_voltages.parquet (one row per
  load, step and phase conductor), load_voltage_steps.csv (one row per step, customer
  loads only) and load_voltage_loads.csv (one row per load). The parquet and the load
  table mark EV legs in ev_leg. Columns in docs/outputs.md.
- <circuit>/EVControl/ev_cars.csv (when the circuit has EV cars): one row per car,
  with place (home or work) and place_load (the load whose bus carries the car's EV
  loads) as its last columns.
- <circuit>/EVControl/ev_places.csv (when the circuit has EV cars): one row per car in
  the order of ev_cars.csv, with the car's home host and its charging place (the host
  or the office), the load, bus and coordinates (Buscoords.dss) of each, energy_kwh,
  plug_in_interval and window_intervals. It records where each car charges on the
  simulated day; it is no record of commuting.
- <circuit>/EVControl/ (when the circuit has controlled cars and ev_control is not
  uncontrolled): ev_control_cars.csv (one row per controlled car, host its home host
  and place_load its charging place); under the valley
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
  the EV WATTS and NHTS pool sizes; the work share case, its share and the commercial
  loads of the circuit, the office pool or work-day pool, the work cars per group, and
  the bus coordinates found and the empty coordinate cells of ev_places.csv; under the
  valley rules W and CV of each forecast curve and the curves with W <= 0 (no error);
  under offpeak_start the cars with a start offset.

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
  ev_cars, ev_day or ev_work_share_case missing or unknown; ev_home_window not true or
  false.
- EV cars: ev.effective_seed missing; under months season, no season_months for the
  run's season; under evwatts_sessions and session_rows, evwatts_extract_dir unset or
  without the extract file, or no census_division for the donor state; with a work
  share above 0 and a commercial load, under evwatts_sessions the office extract
  missing from evwatts_extract_dir, under nhts_days no class (i) vehicle-day with a
  work stop in the pool.
- EV base solve: no yearly solve line or no Monitor m2 in Master.dss, no convergence,
  or a monitor without 96 steps.
- offpeak_start: the tariff file missing; without a window, a car's energy longer
  than the day at its power (ValueError).
- Uncaught exception: for example the check curve in data_ev/ missing under
  session_rows (FileNotFoundError).
- Solution.Converged is not True after Compile, or the circuit was not compiled.
- exit 0 otherwise.
"""

import os, re, sys, csv, time, json, shutil, datetime
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
                        pv_kw_roof_and_use, storage_size, standby_pct)
from storage_control import simple_targets, tuned_targets, schedule, best_start, feeding_lines

# DER sizing from der_sizing in pipeline_config.yaml (repository root, one level above ROOT)
sys.path.insert(0, os.path.join(ROOT, '..'))
from pipeline_utils import load_config, load_mixes, peak_day_rule, ev_control, ev_valley_base, ev_home_window, ev_day
from pipeline_utils import uses_mix_days
from pipeline_utils import ev_cars as ev_cars_source, ev_work_share_case
sys.path.append(ROOT)
from heating_split import is_baseline_only, load_segment
from ev_cars import (load_inputs, read_evwatts_pool, charging_share, read_nhts_pool, evwatts_cars,
                     nhts_cars, session_rows_cars, cars_frame, EVWATTS_EXTRACT_FILE, NHTS_EXTRACT_FILE)
from ev_cars import draw_months, rng as ev_rng
from ev_cars import work_cars, read_bus_coords, EVWATTS_OFFICE_EXTRACT_FILE
# The window of horizon_days days (pipeline_config.yaml): the pieces used above one day only
from pipeline_utils import (WINDOW_DAYS_COLUMNS, WINDOW_DAYS_FILE, day_type, ev_valley_day, horizon_days,
                            window_dates, window_day_rows)
from ev_cars import draw_name, event_row, fail_empty_pool, plan_car, window_group
from ev_control import forecast_days
from storage_control import best_window_start, schedule_days
from der_sizing import day_peak, loadshape_building
CFG = load_config()
HORIZON_DAYS = horizon_days(CFG)
NPTS = IRRADIANCE_NPTS * HORIZON_DAYS   # steps of the solve and of every loadshape
EV_VALLEY_DAY = ev_valley_day(CFG)
PEAK_DAY_RULE = peak_day_rule(CFG)
EV_CONTROL = ev_control(CFG)
EV_VALLEY_BASE = ev_valley_base(CFG)
EV_CARS = ev_cars_source(CFG)
EV_HOME_WINDOW = ev_home_window(CFG)
EV_DAY = ev_day(CFG)
EV_WORK_SHARE_CASE = ev_work_share_case(CFG)
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
SCHEDULE_START       = der_choice(CFG, "schedule_start")
SCHEDULE_START_STEP  = der_number(CFG, "schedule_start_step_pct")
if SCHEDULE_START_STEP <= 0:
    print(f"[FAIL] der_sizing.schedule_start_step_pct in pipeline_config.yaml is {SCHEDULE_START_STEP}; "
          "expected a number above 0.")
    sys.exit(1)
# The starts schedule_start best tries, percent of kWh: from storage_reserve_pct up to 100 in its steps
SCHEDULE_START_PCTS  = [min(100.0, STORAGE_RESERVE_PCT + k * SCHEDULE_START_STEP)
                        for k in range(int((100 - STORAGE_RESERVE_PCT) / SCHEDULE_START_STEP + 1e-9) + 1)]
SCHEDULE_STARTS      = [p / 100 for p in SCHEDULE_START_PCTS]
STANDBY_CASE         = der_choice(CFG, "storage_standby_case")
STANDBY_ELEMENT      = der_choice(CFG, "storage_standby_element")
STANDBY_W            = der_value(CFG, "residential", "storage_standby_w", STANDBY_CASE)
STANDBY_PCT_OF_KW    = der_value(CFG, "commercial", "storage_standby_pct_of_kw", STANDBY_CASE)
SIMPLE_PEAK_FRACTION = der_number(CFG, "simple_peak_fraction")
SIMPLE_MEAN_FRACTION = der_number(CFG, "simple_mean_fraction")
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
       With horizon_days above 1 the maximum is that of day X's 96 values
       (der_sizing.day_peak), so the window does not change a size.
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
                if HORIZON_DAYS > 1:  # the peak of day X, not of the window
                    return day_peak(df[0].to_numpy(), X_INDEX, IRRADIANCE_NPTS)
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
    With peak_day_rule per_circuit and a circuit mix that is not 100 % baseline, and with
    given for every circuit mix, the date is the row of the feeder, season and mix in
    <work_root>/mix_days/<STATE>_circuit_days.csv instead (pipeline_utils.uses_mix_days).
    The records hold no year. Stops if the season or the peak day is missing, or under
    per_circuit or given if the circuit's mix is not in the workspace copy of the mixes
    file.
    """
    if season not in ("summer", "winter"):
        print(f"[FAIL] scenario_assignments.json season is {season!r}; expected summer or winter.")
        sys.exit(1)
    peak_days_path = os.path.join(CFG["work_root"], "5b_profile_generation",
                                  f"{CFG['state']}_peak_days.csv")
    mix_name = None
    if PEAK_DAY_RULE in ("per_circuit", "given"):
        m_mix = re.match(r"^.*_circuit_\d+_(.+)$", CIRCUIT_FOLDER)
        mixes_dir = os.path.join(CFG["work_root"], "7_circuit_instantiation")
        mixes_path = next((os.path.join(mixes_dir, f"mixes{ext}") for ext in (".yaml", ".yml", ".json")
                           if os.path.exists(os.path.join(mixes_dir, f"mixes{ext}"))),
                          os.path.join(mixes_dir, "mixes.yaml"))
        mixes = load_mixes(mixes_path) if os.path.exists(mixes_path) else {}
        if not m_mix or m_mix.group(1) not in mixes:
            print(f"[FAIL] No mix for circuit folder {CIRCUIT_FOLDER} in {mixes_path}.")
            sys.exit(1)
        if uses_mix_days(PEAK_DAY_RULE, is_baseline_only(mixes[m_mix.group(1)]["shares"])):
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
        print(f"PV day -> peak_day_rule {PEAK_DAY_RULE}, mix {mix_name}, from {peak_days_path}")
    return int(rows[0]["Month"]), int(rows[0]["Day"])

def pv_daily_shape(feeder, season):
    """
    Return the PV daily shape of feeder for season: the IRRADIANCE_NPTS values of
    PV_KW_COLUMN divided by 1000 (rounded to 9 decimals) in the donor's SMART-DS solar file
    (PIPELINE_PV_PROFILE_FILE), on the month and day of simulated_day(feeder, season).
    With horizon_days above 1, the same for every date of the window (WINDOW_DATES),
    each day from its own month and day of the file, joined in date order.
    The file's year is ignored. Stops as simulated_day does, or if the file, the
    column or the IRRADIANCE_NPTS rows of that date are missing.
    """
    if HORIZON_DAYS == 1:
        month, day = simulated_day(feeder, season)
        dates = [(month, day)]
    else:
        dates = [(d.month, d.day) for d in WINDOW_DATES]
    pv_file = CFG["pv_profile_file"]
    if not os.path.exists(pv_file):
        print(f"[FAIL] PV profile file not found: {pv_file}")
        sys.exit(1)
    with open(pv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if PV_KW_COLUMN not in (reader.fieldnames or []):
            print(f"[FAIL] Column {PV_KW_COLUMN!r} not in {pv_file}")
            sys.exit(1)
        pv_rows = list(reader)
    values = []
    for month, day in dates:
        day_values = [round(float(r[PV_KW_COLUMN]) / 1000, 9) for r in pv_rows
                      if int(r["Month"]) == month and int(r["Day"]) == day]
        if len(day_values) != IRRADIANCE_NPTS:
            print(f"[FAIL] {len(day_values)} rows for month {month} day {day} in {pv_file}; "
                  f"expected {IRRADIANCE_NPTS}.")
            sys.exit(1)
        values.extend(day_values)
    if HORIZON_DAYS == 1:
        print(f"PV shape -> {season} peak day {month:02d}-{day:02d} of {feeder} from {pv_file}")
    else:
        print(f"PV shape -> {season} window of {HORIZON_DAYS} days, {dates[0][0]:02d}-{dates[0][1]:02d} to "
              f"{dates[-1][0]:02d}-{dates[-1][1]:02d}, of {feeder} from {pv_file}")
    return values

# ---------------- The window (horizon_days in pipeline_config.yaml above 1) ----------------
# WINDOW_DATES: the dates of the window on the calendar of the building curves, around
# the simulated day (day X) of this circuit; X_INDEX: the position of day X, from 0.
# <circuit>/window_days.csv records them (pipeline_utils.window_day_rows).
WINDOW_DATES, X_INDEX = None, 0
if HORIZON_DAYS > 1:
    _window_season = (ASSIGN.get("season") or "").lower()
    WINDOW_DATES, X_INDEX = window_dates(*simulated_day(CIRCUIT_NAME, _window_season), _window_season,
                                         HORIZON_DAYS)
    with open(os.path.join(CURRENT_DIR, WINDOW_DAYS_FILE), "w", newline="", encoding="utf-8") as f:
        _writer = csv.DictWriter(f, fieldnames=WINDOW_DAYS_COLUMNS)
        _writer.writeheader()
        _writer.writerows(window_day_rows(WINDOW_DATES, X_INDEX))
    print(f"Window -> {HORIZON_DAYS} days {WINDOW_DATES[0].isoformat()} to {WINDOW_DATES[-1].isoformat()}, "
          f"day X {WINDOW_DATES[X_INDEX].isoformat()} at position {X_INDEX + 1}")

def window_columns(df, step_col="step"):
    """df with date, day_index and day_type added after step_col (steps from 1), from the
    window day of each step, when horizon_days is above 1; df itself at horizon_days 1,
    so a one-day output keeps its columns."""
    if HORIZON_DAYS == 1:
        return df
    day = (df[step_col].to_numpy(dtype=int) - 1) // IRRADIANCE_NPTS
    at = list(df.columns).index(step_col) + 1
    df = df.copy()
    df.insert(at, "date", np.array([d.isoformat() for d in WINDOW_DATES])[day])
    df.insert(at + 1, "day_index", day + 1)
    df.insert(at + 2, "day_type", np.array([day_type(d) for d in WINDOW_DATES])[day])
    return df

def window_forecast(curve, draw, seed, peak_day=False):
    """The forecast of a curve over the window: (forecast, error, [W per day], [CV per
    day]). Each day has its own 24 draws, rng(draw) on day X as in the one-day run and
    rng(draw_d<offset>) on every other day (ev_cars.draw_name), and its own error from
    its own mean load (ev_control.forecast_days). With peak_day (ev_valley_day
    peak_day), day X's forecast and error are repeated on every day."""
    fc_model = EV_INPUTS["forecast_error"]
    coefficients = EV_INPUTS["forecast_models"][fc_model]
    if peak_day:
        x0 = X_INDEX * IRRADIANCE_NPTS
        fc, err, w, cv = forecast_curve(np.asarray(curve, dtype=float)[x0:x0 + IRRADIANCE_NPTS], fc_model,
                                        coefficients, ev_rng(draw, seed).standard_normal(24))
        return np.tile(fc, HORIZON_DAYS), np.tile(err, HORIZON_DAYS), [w] * HORIZON_DAYS, [cv] * HORIZON_DAYS
    z_days = [ev_rng(draw_name(draw, d - X_INDEX), seed).standard_normal(24) for d in range(HORIZON_DAYS)]
    return forecast_days(curve, fc_model, coefficients, z_days)

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
    # Workplace charging (work_cars): the work share of each group's charging cars charges at
    # a commercial load of the circuit instead of at home.
    ev_work_share = EV_INPUTS["work_share"][EV_WORK_SHARE_CASE]
    OFFICES = sorted(b for b in unique_bases if load_segment(b, base_to_daily) == "commercial")
    print(f"EV cars -> work share case {EV_WORK_SHARE_CASE}: share {ev_work_share}, "
          f"commercial loads {len(OFFICES)}")
    ev_office_pool = ev_work_day_pool = None
    ev_work_on = ev_work_share > 0 and EV_CARS != "session_rows" and len(OFFICES) > 0
    if ev_work_share > 0 and EV_CARS == "session_rows":
        print("EV cars -> work share not applied under ev_cars session_rows: every car charges at home")
    elif ev_work_share > 0 and not OFFICES:
        print("EV cars -> no commercial load in this circuit: every car charges at home")
    elif ev_work_on and EV_CARS == "evwatts_sessions":
        if not os.path.exists(os.path.join(ev_extract_dir, EVWATTS_OFFICE_EXTRACT_FILE)):
            print(f"[FAIL] ev_work_share_case {EV_WORK_SHARE_CASE} needs {EVWATTS_OFFICE_EXTRACT_FILE} in "
                  f"evwatts_extract_dir {ev_extract_dir!r} (build_evwatts_extract.py --venue office).")
            sys.exit(1)
        ev_office_pool = read_evwatts_pool(ev_extract_dir, EV_INPUTS["census_division"][ev_state], ev_months,
                                           file=EVWATTS_OFFICE_EXTRACT_FILE)
        print(f"EV cars -> EV WATTS office pool: {len(ev_office_pool)} sessions of "
              f"{EV_INPUTS['census_division'][ev_state]}, {ev_months_text}")
    elif ev_work_on:
        ev_work_day_pool = ev_nhts_pool[(ev_nhts_pool["day_class"] == "i")
                                        & (ev_nhts_pool["n_work_pieces"] > 0)].reset_index(drop=True)
        if ev_work_day_pool.empty:
            print(f"[FAIL] No class i vehicle-day with a work stop in the NHTS pool of {ev_state}, {ev_months_text}.")
            sys.exit(1)
        print(f"EV cars -> NHTS work-day pool: {len(ev_work_day_pool)} class i vehicle-days with a work stop")
    for group, hosts in (("uncontrolled", json_ev_un), ("controlled", json_ev_ct)):
        if EV_CARS == "evwatts_sessions":
            group_cars = evwatts_cars(group, hosts, ev_pool, ev_share, lvl2_charger_perc, EV_INPUTS, ev_effective_seed)
        elif EV_CARS == "nhts_days":
            group_cars = nhts_cars(group, hosts, ev_nhts_pool, lvl2_charger_perc, EV_INPUTS, ev_effective_seed)
        else:
            group_cars = session_rows_cars(group, hosts, ev_check_curve, ev_share, lvl2_charger_perc, EV_INPUTS,
                                           ev_effective_seed, ev_nhts_pool if group == "controlled" else None)
        if ev_work_on:
            group_cars = work_cars(group, group_cars, ev_work_share, OFFICES, EV_INPUTS, ev_effective_seed, EV_CARS,
                                   office_pool=ev_office_pool, work_day_pool=ev_work_day_pool,
                                   where=EV_INPUTS["census_division"].get(ev_state, ev_state)
                                   if EV_CARS == "evwatts_sessions" else ev_state)
        print(f"EV cars -> {EV_CARS}, {group}: {len(group_cars)} cars, Level 2 "
              f"{sum(c['level'] == 'L2' for c in group_cars)}, charging today {sum(c['charges_today'] for c in group_cars)}, "
              f"at work {sum(c['place'] == 'work' for c in group_cars)}")
        cars += group_cars
    # A window of more than one day (ev_cars.window_group): the records above stay the
    # cars of day X; each car also gets its session of each day type and its charging days.
    if HORIZON_DAYS > 1:
        # The day type of p = 0 (the day before the window) to horizon_days; day X keeps
        # the draw of the one-day run, a weekday session, whatever its date.
        EV_DAY_TYPES = [day_type(WINDOW_DATES[0] - datetime.timedelta(days=1))] + [day_type(d) for d in WINDOW_DATES]
        if EV_DAY_TYPES[X_INDEX + 1] != "weekday":
            print(f"EV cars -> day X {WINDOW_DATES[X_INDEX].isoformat()} is a {WINDOW_DATES[X_INDEX]:%A}: it keeps "
                  f"the weekday draw of the one-day run")
        EV_DAY_TYPES[X_INDEX + 1] = "weekday"
        ev_where = ev_state if EV_CARS == "nhts_days" else EV_INPUTS["census_division"][ev_state]
        ev_window_share = ev_window_pool = ev_window_work = None
        if EV_CARS in ("evwatts_sessions", "session_rows"):
            ev_weekend_file = EV_INPUTS["weekend_files"]["evwatts_residential"]
            if not os.path.exists(os.path.join(ev_extract_dir, ev_weekend_file)):
                print(f"[FAIL] horizon_days {HORIZON_DAYS} needs {ev_weekend_file} in evwatts_extract_dir "
                      f"{ev_extract_dir!r} (build_evwatts_extract.py --day-type weekend).")
                sys.exit(1)
            ev_pool_weekend = read_evwatts_pool(ev_extract_dir, ev_where, ev_months, file=ev_weekend_file)
            fail_empty_pool(ev_pool_weekend, "EV WATTS residential sessions", ev_where, "weekend")
            ev_share_weekend_measured = charging_share(ev_pool_weekend, ev_months, day_type="weekend")
            ev_window_share = {"weekday": ev_share,
                               "weekend": ev_share_weekend_measured if EV_INPUTS["charging_share"] == "measured" else 1.0}
            ev_window_pool = {"weekday": ev_pool, "weekend": ev_pool_weekend}
            print(f"EV cars -> EV WATTS weekend pool: {len(ev_pool_weekend)} sessions of {ev_where}, {ev_months_text}, "
                  f"measured share of cars charging {ev_share_weekend_measured:.6f}, "
                  f"share used {ev_window_share['weekend']:.6f}")
        if EV_CARS == "nhts_days":
            ev_nhts_weekend_path = os.path.join(ROOT, "data_ev_cars",
                                                EV_INPUTS["weekend_files"]["nhts"].format(state=ev_state))
            if not os.path.exists(ev_nhts_weekend_path):
                print(f"[FAIL] horizon_days {HORIZON_DAYS} needs {ev_nhts_weekend_path} "
                      f"(build_nhts_extract.py --day-type weekend).")
                sys.exit(1)
            ev_nhts_pool_weekend = read_nhts_pool(ev_nhts_weekend_path, ev_months, ev_nhts_classes)
            fail_empty_pool(ev_nhts_pool_weekend, "NHTS vehicle-days", ev_where, "weekend")
            ev_window_pool = {"weekday": ev_nhts_pool, "weekend": ev_nhts_pool_weekend}
            print(f"EV cars -> NHTS weekend pool: {len(ev_nhts_pool_weekend)} vehicle-days of {ev_state}, "
                  f"{ev_months_text}, classes {', '.join(ev_nhts_classes)}")
        if ev_work_on:
            ev_window_work = {"share": ev_work_share, "offices": OFFICES, "office_pool": ev_office_pool,
                              "work_day_pool": ev_work_day_pool}
        WINDOW_CARS = {}
        for group in ("uncontrolled", "controlled"):
            WINDOW_CARS[group] = window_group(
                group, [c for c in cars if c["group"] == group], EV_CARS, EV_DAY_TYPES, X_INDEX, EV_INPUTS,
                ev_effective_seed, lvl2_charger_perc, share=ev_window_share, pool=ev_window_pool,
                work=ev_window_work, curve=ev_check_curve if EV_CARS == "session_rows" else None, where=ev_where)
            print(f"EV cars -> window, {group}: {len(WINDOW_CARS[group])} cars, work cars "
                  f"{sum(w['work'] for w in WINDOW_CARS[group])}, charging days "
                  f"{[sum(w['charges'][p] for w in WINDOW_CARS[group]) for p in range(HORIZON_DAYS + 1)]} "
                  f"(the day before the window, then each day)")
cars_u = [c for c in cars if c["group"] == "uncontrolled"]
cars_c = [c for c in cars if c["group"] == "controlled"]
arr_u = np.zeros((N_u, NPTS))
arr_c_sessions = np.zeros((N_c, NPTS))  # controlled cars' own uncontrolled rows
if HORIZON_DAYS == 1:
    for j, c in enumerate(cars_u):
        arr_u[j, :] = c["row"]
    for j, c in enumerate(cars_c):
        arr_c_sessions[j, :] = c["row"]
arr_c = arr_c_sessions                               # replaced by the ev_control rule before LoadShapes_EV.dss is written
# Controlled cars' windows (None: every interval) and charging power for the ev_control rules
windows_c = [c["window"] if EV_HOME_WINDOW else None for c in cars_c]
power_c = [c["power_kw"] for c in cars_c]
# Where each car charges: its host, or its office for a work car
place_u = [c["place_load"] or c["host"] for c in cars_u]
place_c = [c["place_load"] or c["host"] for c in cars_c]
# Work cars over a window of more than one day charge at home on weekend days: the row of
# each such car at its home (home_u, home_c: the positions of those cars; empty at
# horizon_days 1). arr_u and arr_c_sessions then hold the rows at the cars' main place.
home_u, home_c = [], []
arr_uh = np.zeros((0, NPTS))
arr_ch_sessions = np.zeros((0, NPTS))
EV_EVENTS = {"uncontrolled": [], "controlled": []}   # the charging events of every car (ev_cars.plan_car)
EV_CAR_DAYS = {"uncontrolled": [], "controlled": []}  # per car, its rows of the days p = 0 to horizon_days
if HORIZON_DAYS > 1 and cars:
    for group, group_cars, rows, place in (("uncontrolled", cars_u, arr_u, place_u),
                                           ("controlled", cars_c, arr_c_sessions, place_c)):
        home, home_rows = [], []
        for j, (c, w) in enumerate(zip(group_cars, WINDOW_CARS[group])):
            events, days = plan_car([w["sessions"][EV_DAY_TYPES[p]] for p in range(HORIZON_DAYS + 1)],
                                    w["charges"], HORIZON_DAYS)
            if w["work"]:
                place[j] = w["sessions"]["weekday"]["place_load"]
                home.append(j)
                home_rows.append(np.zeros(NPTS))
            for e in events:
                e["car"] = j
                e["row"] = event_row(e, NPTS)
                e["home_part"] = bool(w["work"]) and e["place"] == "home"
                if e["home_part"]:
                    home_rows[-1] += e["row"]
                else:
                    rows[j, :] += e["row"]
            EV_EVENTS[group] += events
            EV_CAR_DAYS[group].append(days)
        if group == "uncontrolled":
            home_u, arr_uh = home, np.array(home_rows).reshape(len(home), NPTS)
        else:
            home_c, arr_ch_sessions = home, np.array(home_rows).reshape(len(home), NPTS)
arr_ch = arr_ch_sessions                             # replaced with arr_c by the ev_control rule

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
        # uncontrolled; a work car's loads are EVu_w<i>_<office>_1/_2 on the office's buses
        for i, base in enumerate(json_ev_un):
            place = place_u[i]
            for suff, info in zip(("_1","_2"), ev_leg_infos(place)):
                ev_load_name = f"EVu_{base}{suff}" if place == base else f"EVu_w{i}_{place}{suff}"
                f_ld.write(
                    f"New Load.{ev_load_name} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVu_{i}\n"
                )
        # horizon_days above 1: a work car's home loads EVu_<host>_1/_2 (weekend days), shape EVu_<i>h
        for i in home_u:
            for suff, info in zip(("_1","_2"), ev_leg_infos(json_ev_un[i])):
                f_ld.write(
                    f"New Load.EVu_{json_ev_un[i]}{suff} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVu_{i}h\n"
                )
        # controlled
        for i, base in enumerate(json_ev_ct):
            place = place_c[i]
            for suff, info in zip(("_1","_2"), ev_leg_infos(place)):
                ev_load_name = f"EVc_{base}{suff}" if place == base else f"EVc_w{i}_{place}{suff}"
                f_ld.write(
                    f"New Load.{ev_load_name} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVc_{i}\n"
                )
        # horizon_days above 1: a work car's home loads EVc_<host>_1/_2 (weekend days), shape EVc_<i>h
        for i in home_c:
            for suff, info in zip(("_1","_2"), ev_leg_infos(json_ev_ct[i])):
                f_ld.write(
                    f"New Load.EVc_{json_ev_ct[i]}{suff} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVc_{i}h\n"
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
    """The building of host base: its first daily loadshape (sorted), <res|com>_kw_<n>_pu,
    and the row of bldg_map with Feeder = this feeder, Yearly_Type res or com and
    Yearly_Number n, both read as text (der_sizing.loadshape_building: n is the whole
    part between _kw_ and _pu, all digits in SMART-DS v1.0, with text in v0.9 Full
    Texas names such as res_kw_9312-North_pu). Returns loadshape, bldg_id, floor area
    (ft2), stories, building type, annual electricity use (kWh) and the roof column
    (ft2 for homes, m2 for commercial). Stops if the loadshape, the row, a column or a
    value is missing."""
    shapes = sorted(base_to_daily.get(base, set()))
    m = loadshape_building(shapes[0]) if shapes else None
    rows = bldg_map[(bldg_map["Feeder"] == CIRCUIT_NAME) & (bldg_map["Yearly_Type"] == m[0])
                    & (bldg_map["Yearly_Number"] == m[1])] if m else bldg_map.iloc[0:0]
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
    bldg_map = pd.read_csv(BLDG_MAP_PATH, low_memory=False, dtype={"Yearly_Number": str})
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
STANDBY_LOADS = []       # under storage_standby_element load: the standby Load of each Storage object
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
            idling_pct = standby_pct(row["segment"], row["storage_kw"], STANDBY_W, STANDBY_PCT_OF_KW)
            for suffix, info, share in der_units(base):
                stg_name = f"storage_{base}{suffix}"
                kw_u, kwh_u, kva_u = row["storage_kw"] * share, row["storage_kwh"] * share, row["storage_kva"] * share
                f_st.write(
                    f"New Storage.{stg_name} phases={info['ph']} bus1={info['bus1']} kV={info['kV']} kVA={kva_u:.4f}\n"
                    f"~ kWRated={kw_u:.4f} kWhRated={kwh_u:.4f} %stored={STORAGE_START_PCT} "
                    f"%reserve={STORAGE_RESERVE_PCT} State=IDLE\n"
                    f"~ %EffCharge={STORAGE_EFF_CHG} %EffDischarge={STORAGE_EFF_DCH} Balanced=yes varFollowInverter=yes "
                    f"%IdlingkW={format(idling_pct if STANDBY_ELEMENT == 'idling' else 0, '.6g')}\n\n"
                )
                mon_pwr  = f"mon_{stg_name}_power"
                mon_soc  = f"mon_{stg_name}_soc"
                f_st.write(f"New Monitor.{mon_pwr} element=Storage.{stg_name} mode=1\n")
                f_st.write(f"New Monitor.{mon_soc} element=Storage.{stg_name} mode=3\n\n")
                if STANDBY_ELEMENT == "load":
                    f_st.write(f"New Load.standby_{stg_name} phases={info['ph']} bus1={info['bus1']} kV={info['kV']} "
                               f"conn={info['conn'] or 'wye'} kW={format(idling_pct / 100 * kw_u, '.6g')} kvar=0 "
                               f"model=1 status=fixed\n\n")
                    STANDBY_LOADS.append(f"standby_{stg_name}")
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
                f_ls.write(f"New Loadshape.{ls_name} npts={NPTS} interval={IRR_INTERVAL_H} mult=({prof_str})\n")
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

# Finally, force Master to a DAILY run (96x15m per day of the window), and (optionally) comment plot lines
if not retarget_master_to_daily(master_dss_path, npts=NPTS, stepsize="15m"):
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

if ACTIVATE_EV and (N_u + N_c) > 0:
    # ev_places.csv: where each car charges on the simulated day (its host or its office), with
    # the load, bus and coordinates (Buscoords.dss) of its home and of its place. It is no record
    # of commuting. A missing file or bus leaves the coordinate cells empty.
    try:
        bus_coords = read_bus_coords(resolve_dss_file(OUT_DIR, "Buscoords.dss"))
    except FileNotFoundError:
        bus_coords = {}
    place_rows, n_empty_coords = [], 0
    for c in cars:
        host, place = c["host"], c["place_load"] or c["host"]
        host_load, place_leg = ev_host_leg(host), ev_host_leg(place)
        host_bus = parsed_loads_map[host_load]["bus1"].split(".")[0]
        place_bus = parsed_loads_map[place_leg]["bus1"].split(".")[0]
        host_xy = bus_coords.get(host_bus.lower(), (None, None))
        place_xy = bus_coords.get(place_bus.lower(), (None, None))
        n_empty_coords += host_xy.count(None) + place_xy.count(None)
        place_rows.append({"car": c["car"], "group": c["group"], "place": c["place"], "host": host,
                           "host_load": host_load, "host_bus": host_bus, "host_lon": host_xy[0], "host_lat": host_xy[1],
                           "place_load": place, "place_leg": place_leg, "place_bus": place_bus,
                           "place_lon": place_xy[0], "place_lat": place_xy[1], "energy_kwh": c["energy_kwh"],
                           "plug_in_interval": c["plug_in_interval"], "window_intervals": c["window_intervals"]})
    places_df = pd.DataFrame(place_rows)
    for col in ("plug_in_interval", "window_intervals"):
        places_df[col] = places_df[col].astype("Int64")
    places_df.to_csv(os.path.join(EVC_DIR, "ev_places.csv"), index=False)
    print(f"EV places -> {len(place_rows)} cars, {sum(c['place'] == 'work' for c in cars)} at work, "
          f"{len(bus_coords)} bus coordinates read, {n_empty_coords} empty coordinate cells")

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
    if not base_master or not retarget_master_to_daily(base_master, npts=NPTS, stepsize="15m"):
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
        if len(p) != NPTS:
            print(f"[FAIL] Monitor {name} of the EV base solve holds {len(p)} steps; expected {NPTS}.")
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
STORAGE_PLANS = {}         # under schedule: host -> (planned stored kWh per step and at the end, host kWh)
STORAGE_MIDNIGHT_ROWS = [] # horizon_days above 1: one per Storage object and day, after the solve

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
    if not smaster or not retarget_master_to_daily(smaster, npts=NPTS, stepsize="15m"):
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
        if len(p) != NPTS:
            print(f"[FAIL] Monitor ms_{n} of the storage {name} holds {len(p)} steps; expected {NPTS}.")
            sys.exit(1)
        out[key] = np.asarray(p, dtype=float)
    return out

def storage_views():
    """Return (views, host_view, host_keys). views {key: (element, terminal)}: "feeder"
    is the element of Monitor m1/m2 of Master.dss (find_controller_anchor), terminal 1.
    Under storage_view transformer, "transformer_<t>" is Transformer.<t>, terminal 1, for
    each service transformer of a storage host (service_transformers on the host's
    leg, ev_host_leg). Under building, "building_<line>" is the Line that feeds the
    host's bus (feeding_lines), else the host's transformer; hosts fed by the same Line
    share its view. host_view {storage host: key}; a host without its element watches
    the feeder. host_keys(base) gives every view key whose element carries the flow of
    host base (a PV or car host counts in the building view of the Line that feeds its
    own bus)."""
    anchor = find_controller_anchor(master_dss_path)
    if not anchor:
        raise RuntimeError("Could not infer StorageController anchor from Master.dss. "
                           "Expected a Monitor.m1/m2 element or an Energymeter element.")
    views = {"feeder": (anchor, 1)}
    host_view = {u["host"]: "feeder" for u in STORAGE_UNITS}
    tr_map, line_of = {}, {}
    if STORAGE_VIEW != "feeder":
        dss_texts = [read_text(os.path.join(OUT_DIR, fn)) for fn in dss_files]
        tr_map, _ = service_transformers(dss_texts, {n: i["bus1"] for n, i in parsed_loads_map.items()})
        if STORAGE_VIEW == "building":
            layer_hosts = set(host_view) | set(pv_host_list) | set(place_u) | set(place_c) \
                | {json_ev_un[i] for i in home_u} | {json_ev_ct[i] for i in home_c}  # work cars' homes (window)
            line_of = feeding_lines(dss_texts, {h: (parsed_loads_map[ev_host_leg(h)]["bus1"],
                                                    tr_map.get(ev_host_leg(h))) for h in layer_hosts})
        for h in host_view:
            t = tr_map.get(ev_host_leg(h))
            if line_of.get(h):
                host_view[h] = f"building_{line_of[h][0]}"
                views[host_view[h]] = (f"Line.{line_of[h][0]}", line_of[h][1])
            elif t:
                host_view[h] = f"transformer_{t}"
                views[host_view[h]] = (f"Transformer.{t}", 1)
        print(f"Storage view -> {STORAGE_VIEW}: {len(views) - 1} {STORAGE_VIEW} views, "
              f"{sum(1 for v in host_view.values() if v == 'feeder')} hosts on the feeder view")

    def host_keys(base):
        t = tr_map.get(ev_host_leg(base)) if base in parsed_loads_map or base + "_1" in parsed_loads_map else None
        line = line_of.get(base)
        return [k for k in ("feeder", f"transformer_{t}" if t else None, f"building_{line[0]}" if line else None)
                if k in views]
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
        # with the home rows of the work cars of a window (no row at horizon_days 1)
        for rows, hosts in ((arr_u, place_u), (arr_c, place_c),
                            (arr_uh, [json_ev_un[i] for i in home_u]), (arr_ch, [json_ev_ct[i] for i in home_c])):
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
        if HORIZON_DAYS == 1:
            z = ev_rng(draw, seed).standard_normal(24)
            fc, err, fc_w, fc_cv = forecast_curve(curves[key], fc_model, EV_INPUTS["forecast_models"][fc_model], z)
        else:  # each day of the window has its own draws and its own error
            fc, err, _, _ = window_forecast(curves[key], draw, seed)
        STORAGE_FORECAST_DRAWS.append(draw)
        element, terminal = views[key]
        for i in range(NPTS):
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
                if HORIZON_DAYS > 1 and SCHEDULE_START == "fixed":
                    # The window rule (storage_control.schedule_days): each day on its own
                    # forecast, from the energy the day before left
                    net, energy, x = schedule_days(cur, h_kw, h_kwh, start, reserve, eff_c, eff_d, dt,
                                                   IRRADIANCE_NPTS)
                    h_pct, stored = STORAGE_START_PCT, ""
                elif HORIZON_DAYS > 1:
                    if SCHEDULE_START == "best":  # the start of the one-day rule on day X's forecast
                        x0 = X_INDEX * IRRADIANCE_NPTS
                        h_start = best_start(cur[x0:x0 + IRRADIANCE_NPTS], h_kw, h_kwh, reserve, eff_c, eff_d, dt,
                                             SCHEDULE_STARTS)[0]
                        net, energy, x = schedule_days(cur, h_kw, h_kwh, h_start, reserve, eff_c, eff_d, dt,
                                                       IRRADIANCE_NPTS)
                    else:  # best_window: the start that leaves the lowest maximum of the window
                        h_start, net, energy, x = best_window_start(cur, h_kw, h_kwh, reserve, eff_c, eff_d, dt,
                                                                    SCHEDULE_STARTS, IRRADIANCE_NPTS)
                    h_pct = SCHEDULE_START_PCTS[SCHEDULE_STARTS.index(h_start)]
                    stored = f" %stored={format(h_pct, '.6g')}"
                elif SCHEDULE_START in ("best", "best_window"):
                    h_start, net, energy, x = best_start(cur, h_kw, h_kwh, reserve, eff_c, eff_d, dt, SCHEDULE_STARTS)
                    h_pct = SCHEDULE_START_PCTS[SCHEDULE_STARTS.index(h_start)]
                    stored = f" %stored={format(h_pct, '.6g')}"
                else:
                    net, energy, x = schedule(cur, h_kw, h_kwh, start, reserve, eff_c, eff_d, dt)
                    h_pct, stored = STORAGE_START_PCT, ""
                cur = cur - net
                STORAGE_PLANS[host] = (energy, h_kwh)
                shape = f"StoSched_{n_sched}"
                n_sched += 1
                text.append(f"New Loadshape.{shape} npts={NPTS} interval={IRR_INTERVAL_H} "
                            f"mult=({' '.join(f'{v / h_kw:.6f}' for v in net)})\n")
                for u in h_units:
                    text.append(f"Edit Storage.{u['name']} DispMode=FOLLOW daily={shape}{stored}\n")
                    STORAGE_TARGET_ROWS.append({**base_row, "battery": u["name"], "host": host,
                                                "segment": u["segment"], "kw_rated": u["kw"], "kwh_rated": u["kwh"],
                                                "start_pct": h_pct, "schedule_discharge_kwh": x * u["kw"] / h_kw})
                for i in range(NPTS):
                    sched_rows.append({"view": key, "host": host, "loadshape": shape, "step": i + 1,
                                       "net_kw": net[i], "stored_kwh_start": energy[i], "stored_kwh_end": energy[i + 1]})
            text.append("\n")
            continue
        if STORAGE_RULE == "simple":
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
                                        "kw_rated": u["kw"], "kwh_rated": u["kwh"], "start_pct": STORAGE_START_PCT,
                                        "kw_target": float(f"{target:.4f}"), "kw_target_low": float(f"{low:.4f}")})
    with open(storage_path, "a", encoding="utf-8") as f_st:
        f_st.writelines(text)
    window_columns(pd.DataFrame(curve_rows)).to_csv(os.path.join(STC_DIR, "storage_curves.csv"), index=False)
    if STORAGE_RULE == "schedule":
        window_columns(pd.DataFrame(sched_rows)).to_csv(os.path.join(STC_DIR, "storage_schedule.csv"), index=False)
    print(f"Storage control -> {STORAGE_RULE}, view {STORAGE_VIEW}, order {STORAGE_ORDER}, measure "
          f"{STORAGE_MEASURE}, layer {STORAGE_LAYER}: {len(STORAGE_TARGET_ROWS)} batteries, "
          f"{len(STORAGE_FORECAST_DRAWS)} views with storage")

if n_storage > 0 and STORAGE_ORDER == "before_cars":
    storage_control_step(with_cars=False)

def window_ev_control():
    """The ev_control rule over a window of more than one day (horizon_days above 1).
    Returns (controlled rows at the cars' main place, controlled home rows of the work
    cars, car_curve, placement_rank, shifts), the last three one value per controlled
    car as in the one-day run.

    Every charging event of a controlled car (EV_EVENTS, ev_cars.plan_car: a drawn
    session, a top-up, or the part after midnight of the session of the day before the
    window) is one row of 96 x horizon_days kW with its own window on the timeline, and
    the rules of ev_control.py place the events as the one-day run places the cars.
    With ev_home_window false an event may use the 96 steps of the day of its first
    charging step, from that step and wrapping inside the day.
    - Valley rules: one base solve over the window (run_base_solve); the uncontrolled
      cars' kW is added; the events are placed in order of plug-in time on the timeline
      (an event without a plug-in time at the end of its day), each placed event joining
      the forecast. Under ev_valley_day own_day the forecast has a new error for each
      day (window_forecast); under peak_day it is day X's forecast, repeated on each
      day. EVControl/ev_control_curves.csv holds one row per curve and step, with
      forecast_kw, the curve the first event saw.
    - offpeak_start: the cheap steps of each day come from the tariff row of the day's
      own month (day X's month under peak_day) and of the day's type, weekday or
      weekend; each car keeps one start offset for all its events."""
    global EV_BASE_FEEDER_P
    events = EV_EVENTS["controlled"]
    n_e = len(events)
    rows_e = np.array([e["row"] for e in events]).reshape(n_e, NPTS)
    powers_e = [e["power"] for e in events]

    def day_steps(e):
        nz = np.flatnonzero(e["row"])
        first = int(nz[0]) if nz.size else (e["window"][0] if e["window"] else 0)
        d0 = (first // IRRADIANCE_NPTS) * IRRADIANCE_NPTS
        return [d0 + (first - d0 + k) % IRRADIANCE_NPTS for k in range(IRRADIANCE_NPTS)]

    windows_e = [e["window"] if EV_HOME_WINDOW else day_steps(e) for e in events]
    order = sorted(range(n_e), key=lambda i: (events[i]["plug_abs"], i))
    placement_rank, shifts = [None] * N_c, [None] * N_c
    for rank, i in enumerate(order, start=1):
        if placement_rank[events[i]["car"]] is None:
            placement_rank[events[i]["car"]] = rank
    car_curve = [""] * N_c
    if EV_CONTROL in EV_VALLEY_RULES:
        # ASSUMPTION: as in the one-day run, uncontrolled cars are added to the base curve
        # as their own kW, without the line losses they cause.
        unc_total = arr_u.sum(axis=0) + arr_uh.sum(axis=0)
        tr_names, tr_monitor, unc_on = [], {}, {}
        event_curve = ["feeder"] * n_e
        car_curve = ["feeder"] * N_c
        if EV_CONTROL == "valley_fill_transformer":
            dss_texts = [read_text(os.path.join(OUT_DIR, fn)) for fn in dss_files]
            skipped_lines = []
            tr_map, tr_status = service_transformers(dss_texts, {n: i["bus1"] for n, i in parsed_loads_map.items()},
                                                     skipped_lines)
            print(f"Service transformers -> switched-out lines (enabled=n) left out of the map: {len(skipped_lines)}")
            n_status = {s: sum(1 for v in tr_status.values() if v == s) for s in ("one", "none", "several")}
            print(f"Service transformers -> loads with one: {n_status['one']}, none: {n_status['none']}, "
                  f"several: {n_status['several']}")
            ctl_tr = [tr_map.get(ev_host_leg(b)) for b in place_c]
            car_curve = [t if t else "feeder_fallback" for t in ctl_tr]
            event_tr = [tr_map.get(ev_host_leg(e["place_load"])) for e in events]
            event_curve = [t if t else "feeder" for t in event_tr]
            tr_names = sorted({t for t in ctl_tr + event_tr if t})
            tr_monitor = {t: f"mt_{n}" for n, t in enumerate(tr_names, start=1)}
            unc_places = [(arr_u[i, :], place_u[i]) for i in range(N_u)] + \
                         [(arr_uh[k, :], json_ev_un[i]) for k, i in enumerate(home_u)]
            for t in tr_names:
                unc_on[t] = sum((row for row, b in unc_places if tr_map.get(ev_host_leg(b)) == t), np.zeros(NPTS))
            print(f"Controlled cars on the feeder curve (host without one service transformer): "
                  f"{car_curve.count('feeder_fallback')} of {N_c}")
        feeder_p, trans_p = run_base_solve(tr_names)
        if EV_VALLEY_BASE == "buildings_only" and STORAGE_ORDER != "before_cars":
            EV_BASE_FEEDER_P = feeder_p
        start_curves = {"feeder": feeder_p + unc_total}
        start_curves.update({t: trans_p[t] + unc_on[t] for t in tr_names})
        fc_curves, fc_error, n_no_error = {}, {}, 0
        for name, curve in start_curves.items():
            fc_curves[name], fc_error[name], fc_w, fc_cv = window_forecast(
                curve, f"forecast_{name}", ev_effective_seed, peak_day=EV_VALLEY_DAY == "peak_day")
            n_no_error += sum(cv is None for cv in fc_cv)
            print(f"Forecast -> {name}: {EV_INPUTS['forecast_error']}, ev_valley_day {EV_VALLEY_DAY}, W per day "
                  f"{[round(w, 4) for w in fc_w]} kW, CV per day {[None if cv is None else round(cv, 4) for cv in fc_cv]} %")
        print(f"Forecast -> curve-days with W <= 0 (no error): {n_no_error} of {len(start_curves) * HORIZON_DAYS}")
        fc_first = {name: curve.copy() for name, curve in fc_curves.items()}
        if EV_CONTROL == "valley_fill_feeder":
            placed, _ = valley_fill(rows_e, fc_curves["feeder"], windows_e, order)
        elif EV_CONTROL == "water_fill_feeder":
            placed, _ = water_fill(rows_e, fc_curves["feeder"], powers_e, windows_e, order)
        else:
            placed, _ = valley_fill_curves(rows_e, fc_curves, event_curve, "feeder", windows_e, order)
        curve_rows = []
        for name in ["feeder"] + tr_names:
            on = [i for i in range(n_e) if name == "feeder" or event_curve[i] == name]
            base_kw = feeder_p if name == "feeder" else trans_p[name]
            unc_kw = unc_total if name == "feeder" else unc_on[name]
            ctl_kw = placed[on, :].sum(axis=0)
            for i in range(NPTS):
                curve_rows.append({"curve": name, "monitor": "m2" if name == "feeder" else tr_monitor[name],
                                   "step": i + 1, "base_kw": base_kw[i], "uncontrolled_ev_kw": unc_kw[i],
                                   "controlled_ev_kw": ctl_kw[i], "forecast_error_kw": fc_error[name][i],
                                   "forecast_kw": fc_first[name][i]})
        window_columns(pd.DataFrame(curve_rows)).to_csv(os.path.join(EVC_DIR, "ev_control_curves.csv"), index=False)
    else:  # offpeak_start
        tariff_path = os.path.join(ROOT, "data_tariffs", f"{CFG['state']}_urdb_rate.json")
        if not os.path.exists(tariff_path):
            print(f"[FAIL] Tariff file not found: {tariff_path}. Run fetch_tou_rates.py first.")
            sys.exit(1)
        tariff = json.loads(read_text(tariff_path))
        cheap = []
        for d, date in enumerate(WINDOW_DATES):
            month = date.month if EV_VALLEY_DAY == "own_day" else WINDOW_DATES[X_INDEX].month
            cheap_period, cheap_day = cheap_intervals(tariff["rate"], month, EV_DAY_TYPES[d + 1])
            cheap += [d * IRRADIANCE_NPTS + i for i in cheap_day]
            print(f"Off-peak start -> {tariff['rate'].get('label')} day {d + 1} ({date.isoformat()}), month {month}, "
                  f"{EV_DAY_TYPES[d + 1]} schedule: period {cheap_period}, {len(cheap_day)} cheap intervals")
        z_spread = ev_rng("start_spread_controlled", ev_effective_seed).standard_normal(N_c)
        shifts_e = start_offsets(rows_e, cheap, windows_e, [z_spread[e["car"]] for e in events],
                                 EV_INPUTS["start_spread_min"])
        for e, d in zip(events, shifts_e):
            if d is not None and shifts[e["car"]] is None:
                shifts[e["car"]] = d
        print(f"Off-peak start -> start spread {EV_INPUTS['start_spread_min']} min: "
              f"{sum(d is not None for d in shifts)} of {N_c} cars with a start offset")
        placed, _ = offpeak_start(rows_e, cheap, powers_e, windows_e, shifts_e)
    rows_c, rows_ch = np.zeros((N_c, NPTS)), np.zeros((len(home_c), NPTS))
    for i, e in enumerate(events):
        e["controlled_kwh"] = float(placed[i, :].sum()) / 4.0
        if e["home_part"]:
            rows_ch[home_c.index(e["car"]), :] += placed[i, :]
        else:
            rows_c[e["car"], :] += placed[i, :]
    return rows_c, rows_ch, car_curve, placement_rank, shifts


if ACTIVATE_EV and N_c > 0 and EV_CONTROL != "uncontrolled":
    os.makedirs(EVC_DIR, exist_ok=True)
    car_curve = [""] * N_c
    starts = None
    placement_rank = [None] * N_c
    shifts = [None] * N_c
    if HORIZON_DAYS > 1:
        arr_c, arr_ch, car_curve, placement_rank, shifts = window_ev_control()
    elif EV_CONTROL in EV_VALLEY_RULES:
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
            ctl_tr = [tr_map.get(ev_host_leg(b)) for b in place_c]
            car_curve = [t if t else "feeder_fallback" for t in ctl_tr]
            tr_names = sorted({t for t in ctl_tr if t})
            tr_monitor = {t: f"mt_{n}" for n, t in enumerate(tr_names, start=1)}
            unc_tr = [tr_map.get(ev_host_leg(b)) for b in place_u]
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
        if j in home_c:  # a work car of a window: its office rows plus its home rows
            s_row, c_row = s_row + arr_ch_sessions[home_c.index(j), :], c_row + arr_ch[home_c.index(j), :]
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
            "placement_order": placement_rank[j], "start_offset_intervals": shifts[j],
            "place_load": place_c[j]})
    cars_df = pd.DataFrame(car_rows)
    for col in ("first_interval_uncontrolled", "first_interval_controlled", "placement_order",
                "start_offset_intervals"):
        cars_df[col] = cars_df[col].astype("Int64")
    cars_df.to_csv(os.path.join(EVC_DIR, "ev_control_cars.csv"), index=False)
    print(f"EV control -> {EV_CONTROL}: {N_c} controlled cars")

if HORIZON_DAYS > 1 and cars:
    # EVControl/ev_car_days.csv: one row per car and day, the day before the window
    # (day_index 0) and each day of the window. planned_kwh is the car's charging on the
    # run's steps before any control; delivered_kwh is what its loadshape holds (the
    # controlled result for a controlled car); owed_kwh is needed less delivered, summed
    # from day 0, so the last day's value is the energy still owed at the end.
    day_rows = []
    for group, group_cars in (("uncontrolled", cars_u), ("controlled", cars_c)):
        controlled_kwh = {(e["car"], e["p"]): e["controlled_kwh"] for e in EV_EVENTS[group] if "controlled_kwh" in e}
        for j, c in enumerate(group_cars):
            needed_sum = delivered_sum = 0.0
            for p, day in enumerate(EV_CAR_DAYS[group][j]):
                date = WINDOW_DATES[0] + datetime.timedelta(days=p - 1)
                delivered = controlled_kwh.get((j, p), day["delivered_kwh"])
                needed_sum += day["needed_kwh"]
                delivered_sum += delivered
                day_rows.append({
                    "car": c["car"], "group": group, "host": c["host"], "day_index": p, "date": date.isoformat(),
                    "day_type": EV_DAY_TYPES[p], "day_x": 1 if p == X_INDEX + 1 else 0, "charges": day["charges"],
                    "event": day["kind"], "session_id": day["source_id"], "place": day["place"],
                    "place_load": day["place_load"], "needed_kwh": day["needed_kwh"],
                    "planned_kwh": day["delivered_kwh"], "delivered_kwh": delivered,
                    "topup_kwh": delivered if day["kind"] == "top_up" else 0.0, "tail_kwh": day["tail_kwh"],
                    "backlog_kwh": day["backlog_kwh"], "owed_kwh": needed_sum - delivered_sum})
    pd.DataFrame(day_rows).to_csv(os.path.join(EVC_DIR, "ev_car_days.csv"), index=False)
    print(f"EV car days -> {len(day_rows)} rows: needed {sum(r['needed_kwh'] for r in day_rows):.4f} kWh, "
          f"delivered {sum(r['delivered_kwh'] for r in day_rows):.4f} kWh, top-up "
          f"{sum(r['topup_kwh'] for r in day_rows):.4f} kWh, owed at the end "
          f"{sum(r['owed_kwh'] for r in day_rows if r['day_index'] == HORIZON_DAYS):.4f} kWh")

if ACTIVATE_EV and (N_u + N_c) > 0:
    # EV loadshapes: uncontrolled -> EVu_i, controlled -> EVc_i
    with open(loadshapes_ev_path, "w", encoding="utf-8") as f_ls:
        f_ls.write("! EV LoadShapes (uncontrolled + controlled)\n\n")
        for i in range(N_u):
            row = arr_u[i, :]
            f_ls.write(f"New Loadshape.EVu_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")
        for k, i in enumerate(home_u):  # horizon_days above 1: the home rows of the work cars
            row = arr_uh[k, :]
            f_ls.write(f"New Loadshape.EVu_{i}h npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")
        for i in range(N_c):
            row = arr_c[i, :]
            f_ls.write(f"New Loadshape.EVc_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")
        for k, i in enumerate(home_c):
            row = arr_ch[k, :]
            f_ls.write(f"New Loadshape.EVc_{i}h npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")

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
        engine_loads = {str(n).lower() for n in DSScircuit.Loads.AllNames} - {n.lower() for n in STANDBY_LOADS}
        if engine_loads != {n.lower() for n in LV_LOADS}:
            raise RuntimeError(f"Loads in the compiled circuit ({len(engine_loads)}) differ from "
                               f"the loads with a voltage monitor ({len(LV_LOADS)}).")
        lv_frame, lv_no_base = load_voltage_frame(read_load_monitors(DSScircuit, LV_LOADS))
        # window_columns: date, day_index and day_type per step when horizon_days is above 1
        window_columns(lv_frame).to_parquet(os.path.join(OUT_DIR, "load_voltages.parquet"), index=False)
        window_columns(step_table(lv_frame, V_LOW_PU, V_HIGH_PU)).to_csv(
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
            for h in ("kwh", "kwin", "kwout", "kwtotallosses"):
                if h not in chan:
                    raise RuntimeError(f"Monitor {soc_mon[row['battery']]} has no {h} channel.")
            kwh = np.asarray(mon.Channel(chan["kwh"]), dtype=float)
            # The monitor writes each step's energy before that step acts; e_after adds step 96
            kwin = np.asarray(mon.Channel(chan["kwin"]), dtype=float)
            kwout = np.asarray(mon.Channel(chan["kwout"]), dtype=float)
            losses = np.asarray(mon.Channel(chan["kwtotallosses"]), dtype=float)
            e_after = float(kwh[-1] + (kwin[-1] - kwout[-1] - losses[-1]) * IRR_INTERVAL_H)
            row.update({"charged_kwh": float(np.sum(mon.Channel(chan["kwin"]))) * IRR_INTERVAL_H,
                        "discharged_kwh": float(np.sum(mon.Channel(chan["kwout"]))) * IRR_INTERVAL_H,
                        "stored_kwh_start": row["kwh_rated"] * row["start_pct"] / 100.0,
                        "stored_kwh_end": e_after, "stored_kwh_min": min(float(kwh.min()), e_after),
                        "stored_kwh_max": max(float(kwh.max()), e_after)})
            # horizon_days above 1: the stored energy at each midnight, from the state monitor
            # and, under schedule, from the host's plan (the battery's share of its kWh)
            plan = STORAGE_PLANS.get(row["host"])
            for d in range(HORIZON_DAYS if HORIZON_DAYS > 1 else 0):
                end = (d + 1) * IRRADIANCE_NPTS
                monitor_end = float(kwh[end]) if end < len(kwh) else e_after
                planned_end = float(plan[0][end]) * row["kwh_rated"] / plan[1] if plan else None
                STORAGE_MIDNIGHT_ROWS.append({
                    "battery": row["battery"], "host": row["host"], "view": row["view"], "rule": row["rule"],
                    "day_index": d + 1, "date": WINDOW_DATES[d].isoformat(), "day_type": day_type(WINDOW_DATES[d]),
                    "kwh_rated": row["kwh_rated"], "planned_kwh_end": planned_end, "monitor_kwh_end": monitor_end,
                    "drift_kwh": None if planned_end is None else monitor_end - planned_end})
    if n_storage > 0:
        pd.DataFrame(STORAGE_TARGET_ROWS).to_csv(os.path.join(STC_DIR, "storage_targets.csv"), index=False)
    if STORAGE_MIDNIGHT_ROWS:
        pd.DataFrame(STORAGE_MIDNIGHT_ROWS).to_csv(os.path.join(STC_DIR, "storage_midnights.csv"), index=False)
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
