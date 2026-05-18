# -*- coding: utf-8 -*-
"""
power_flow_sim_daily_EV_STO_DG_deploy.py
----------------------------------------
Single-scenario deploy runner for a prepared circuit folder.
- Mixes *both* EV types (uncontrolled + controlled) in one scenario.
- Uses ev_loads_uncontrolled / ev_loads_controlled from scenario_assignments.json.
- Replicates EV rows if generator yields fewer than requested loads.
- Storage/PV sized vs target load peak and added once.

Run from inside a prepared circuit folder: ./<STATE>_circuit_<n>_<mix>/
"""

import os, re, sys, csv, time, json, math, shutil, random, cmath
import numpy as np, pandas as pd
import comtypes.client as cc
from copy import deepcopy

# -----------------------
# Knobs
# -----------------------
DEFAULT_EV_PERC      = 0.10
DEFAULT_EV_L2_PERC   = 0.80
EV_NOMINAL_POWER_KW  = 7.36
EV_MAX_EVENTS        = 2
EV_ERROR_TOL         = 1e-6

# Storage sizing vs load peak
STORAGE_KW_PER_PEAK  = 0.75
STORAGE_ENERGY_HOURS = 4.0
STORAGE_PF           = 0.90
STORAGE_RESERVE_PCT  = 20
STORAGE_EFF_CHG      = 95.0
STORAGE_EFF_DCH      = 95.0

# PV sizing vs load peak
PV_KW_PER_PEAK       = 0.30
IRRADIANCE_NPTS      = 96
IRR_INTERVAL_H       = 0.25

ACTIVATE_EV          = True
COMPILE_CIRCUIT      = True

# -----------------------
# Helpers
# -----------------------
def read_text(p):  return open(p,'r',encoding='utf-8').read()
def write_text(p,t): open(p,'w',encoding='utf-8').write(t)
def read_lines(p): return open(p,'r',encoding='utf-8').readlines()
def write_lines(p,ls): open(p,'w',encoding='utf-8').writelines(ls)
def try_float(x, default=None):
    try: return float(x)
    except Exception: return default
def clamp01(x): return max(0.0, min(1.0, float(x)))

# Fixed irradiance (96 points)
irradiance_winter_padded = [0.0]*30 + [0.0889,0.13254,0.17853,0.12173,0.05258,0.04381,0.03429,0.04749,0.06053,0.07725,0.09377,0.09119,0.08877,0.09676,0.10466,0.11636,0.12792,0.1476,0.16692,0.18,0.19282,0.20862,0.2245,0.2171,0.2098,0.25007,0.28447,0.31986,0.34005,0.31685,0.28823,0.24886,0.20951,0.16926,0.1312,0.09432,0.06385,0.04184,0.03615,0.03066,0.02312,0.00845]+[0.0]*25
irradiance_summer_padded = [0.0]*25 + [0.09904,0.16947,0.2279,0.29098,0.34296,0.39615,0.44168,0.48566,0.52159,0.55551,0.58447,0.61212,0.63157,0.65283,0.66968,0.68472,0.69552,0.70443,0.71021,0.71404,0.71482,0.71364,0.70865,0.70175,0.69187,0.68011,0.66613,0.65034,0.63108,0.61013,0.58641,0.56116,0.53425,0.50397,0.46959,0.43362,0.39509,0.35526,0.31306,0.26707,0.22195,0.17753,0.13386,0.09435,0.06009,0.03379,0.02603,0.02325,0.01879,0.01289]+[0.0]*21

# EV helpers (your modules)
CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
ROOT        = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
sys.path.insert(0, os.path.join(ROOT, 'deployer_modules'))
from pfs_parsing_misc import parse_transformers, parse_lines, parse_loads, can_add_more, update_target_sums, linear_interpolate
from pfs_file_processing import modify_master_file, modify_dss_files
from pfs_ev_modeling import generate_initial_charging_sessions, adjust_charging_sessions, balance_demand_with_zero_sessions, adjust_charging_sessions_2, count_charging_cycles
from pfs_ev_plotting import plot_calibration, plot_sessions_heatmap, plot_combined_profile_sessions
from pfs_heatpump_plotting import plot_combined_heatpump_sessions
from pfs_write_csv_1 import write_simulation_results_to_csv
from pfs_ev_base_profiles import process_vehicle_data
from pfs_hp_base_profiles import generate_heatpump_profiles

# -----------------------
# Start
# -----------------------
START_TIME     = time.time()
CIRCUIT_FOLDER = os.path.basename(CURRENT_DIR)
PROFILES_PATH  = os.path.join('..', 'profiles_use_bench', CIRCUIT_FOLDER)

# feeder subfolder (starts with 'uhs')
subs = [d for d in os.listdir(CURRENT_DIR) if os.path.isdir(os.path.join(CURRENT_DIR,d)) and d.startswith('uhs')]
if not subs:
    print("❌ No feeder subfolder (uhs*) found under this circuit folder.")
    sys.exit(1)
CIRCUIT_NAME = subs[0]
CIRCUIT_DIR  = os.path.join(CURRENT_DIR, CIRCUIT_NAME)

# assignments JSON
ASSIGN_PATH = os.path.join(CURRENT_DIR, "scenario_assignments.json")
ASSIGN = {}
if os.path.exists(ASSIGN_PATH):
    try:
        ASSIGN = json.loads(read_text(ASSIGN_PATH))
        print(f"✅ Loaded scenario assignments: {ASSIGN_PATH}")
    except Exception as e:
        print(f"⚠️ Could not parse scenario_assignments.json: {e}")

# EV params
ev_perc           = clamp01(ASSIGN.get("ev", {}).get("perc", DEFAULT_EV_PERC))
lvl2_charger_perc = clamp01(ASSIGN.get("ev", {}).get("lvl2_perc", DEFAULT_EV_L2_PERC))
print(f"EV params → perc={ev_perc:.2f}, L2 share={lvl2_charger_perc:.2f}")

# Read Loads.dss (for bases + daily mapping)
PATH_LOADS_DSS       = os.path.join(CIRCUIT_DIR, 'Loads.dss')
PATH_LOADS_DSS_ORIG  = os.path.join(CIRCUIT_DIR, 'Loads_original.dss')
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
for line in read_lines(os.path.join(CIRCUIT_DIR, "Loads.dss")):
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
    Make sure our added redirects are placed BEFORE the first Solve:
      - After 'Redirect LoadShapes.dss':  LoadShapes_EV.dss, LoadShapes_PV.dss (if exist)
      - After 'Redirect Loads.dss':      Storage.dss, PVSystems.dss (if exist)
    If anchors aren't found, insert blocks just before the first Solve.
    Removes existing duplicates of these redirects to keep Master clean.
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

        # After LoadShapes.dss → shapes
        if (not inserted_shapes) and re.search(r'(?i)\bRedirect\s+LoadShapes\.dss\b', ln):
            if block_shapes:
                out.extend(block_shapes)
            inserted_shapes = True

        # After Loads.dss → objects (storage/pv)
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

def find_controller_anchor(master_path):
    """
    Return the element string to monitor (e.g., 'Line.l(r:udt14717-uhs0_1247)') by
    reading Master.dss. Prefer monitor m1/m2; if missing, fall back to Energymeter.
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
    Replace only a 'Solve mode=yearly stepsize=15m number=35040' line with
    'Solve mode=daily stepsize=15m number=96'. Case-insensitive, order-insensitive.
    Leaves all other lines untouched.
    Returns True if a replacement was made, else False.
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

def peak_kw_for_load(full_name):
    """Try consolidated CSV (peak of daily), else original kW, else tiny fallback."""
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
            if f"New Load.{full_name}" in line:
                m_kw = re.search(r"\bkW=([0-9\.Ee+-]+)", line)
                if m_kw: 
                    v = try_float(m_kw.group(1), None)
                    if v is not None: return v
    return 10.0

# ---------------- EV profiles (both types) ----------------
if ACTIVATE_EV:
    # base EV demand input (from ./data_ev copied at instantiate)
    avg_15 = process_vehicle_data(CURRENT_DIR, ev_profile_version='without_pif', test_compare_ev_input_profiles=True)

    def generate_ev_profiles(avg_demand, load_number_resi, ev_p, l2_p, nominal_power, max_events, err_tol):
        avg_demand = np.array(deepcopy(avg_demand))
        N = int(load_number_resi * ev_p * l2_p)
        min_power = nominal_power * 0.9
        T = len(avg_demand)
        sessions = generate_initial_charging_sessions(N, T, nominal_power, min_power, max_events, avg_demand)
        sessions = adjust_charging_sessions(sessions, avg_demand, N, nominal_power, T, err_tol)
        sessions = adjust_charging_sessions_2(sessions, avg_demand, N, nominal_power, T, err_tol, max_events, min_power)
        # Fill completely zero rows if any (simple equal-energy fill on available intervals)
        zero_rows = np.where(np.all(sessions == 0, axis=1))[0]
        if len(zero_rows) > 0:
            avg_profile = np.mean(sessions, axis=0)
            nz = np.flatnonzero(avg_profile)
            for idx in zero_rows:
                if nz.size > 0:
                    sessions[idx, nz] = (avg_profile[nz].sum() / len(nz))
        return sessions

    # Generate base set (uncontrolled); make a controlled version by equal-energy reshaping
    arr_ev_all_unctl = generate_ev_profiles(avg_15, len(unique_loads_list), ev_perc, lvl2_charger_perc,
                                           EV_NOMINAL_POWER_KW, EV_MAX_EVENTS, EV_ERROR_TOL)

    def equal_energy_realloc(profiles):
        P = profiles.copy()
        out = np.zeros_like(P)
        for i in range(P.shape[0]):
            row = P[i, :]
            nz  = np.flatnonzero(row)
            if len(nz) == 0:
                continue
            e = row.sum()
            out[i, nz] = e / len(nz)
        return out

    arr_ev_all_ctl = equal_energy_realloc(arr_ev_all_unctl)
else:
    arr_ev_all_unctl = np.zeros((0, IRRADIANCE_NPTS))
    arr_ev_all_ctl   = np.zeros((0, IRRADIANCE_NPTS))

# ---------------- EV host lists from JSON ----------------
json_ev_un = ASSIGN.get("ev_loads_uncontrolled", []) if isinstance(ASSIGN, dict) else []
json_ev_ct = ASSIGN.get("ev_loads_controlled",   []) if isinstance(ASSIGN, dict) else []

# If missing, fallback to ev_loads + even split
if (not json_ev_un) and (not json_ev_ct):
    all_ev = ASSIGN.get("ev_loads", [])
    half = len(all_ev)//2
    json_ev_un = all_ev[:half]
    json_ev_ct = all_ev[half:]

N_u = len(json_ev_un)
N_c = len(json_ev_ct)

# If instantiate bumped to 2 EVs (to get both types), we may need to replicate profiles
def ensure_rows(mat, N_target):
    if mat.shape[0] >= N_target:
        return mat[:N_target, :]
    if mat.shape[0] == 0:
        return np.zeros((N_target, IRRADIANCE_NPTS))
    # replicate rows as needed
    reps = int(np.ceil(N_target / mat.shape[0]))
    tiled = np.tile(mat, (reps, 1))
    return tiled[:N_target, :]

arr_u = ensure_rows(arr_ev_all_unctl, N_u)
arr_c = ensure_rows(arr_ev_all_ctl,   N_c)

# ---------------- Prepare scenario dir ----------------
OUT_DIR = os.path.join(CURRENT_DIR, "ModifiedCircuitData")
os.makedirs(OUT_DIR, exist_ok=True)

# Copy DSS base files and fix LoadShapes path relative to scenario dir
dss_files = ['Buscoords.dss','Capacitors.dss','Lines.dss','Loads.dss',
             'Master.dss','Transformers.dss','LoadShapes.dss','LineCodes.dss']
master_dss_path = None
for fn in dss_files:
    src = os.path.join(CIRCUIT_DIR, fn)
    dst = os.path.join(OUT_DIR, fn)
    try:
        shutil.copy2(src, dst)
    except Exception:
        pass
    if fn == 'Master.dss':
        master_dss_path = dst
    if fn == 'LoadShapes.dss':
        lines = read_lines(dst)
        upd = []
        needle = f"file=../profiles_use_bench/{CIRCUIT_FOLDER}/"
        repl   = f"file=../../profiles_use_bench/{CIRCUIT_FOLDER}/"
        for ln in lines:
            upd.append(ln.replace(needle, repl))
        write_lines(dst, upd)

# ---------------- Write EV shapes & loads ----------------
loads_ev_path      = os.path.join(OUT_DIR, "Loads.dss")          # append into existing
loadshapes_ev_path = os.path.join(OUT_DIR, "LoadShapes_EV.dss")  # new EV shapes file

if ACTIVATE_EV and (N_u + N_c) > 0:
    # EV loadshapes: uncontrolled → EVu_i, controlled → EVc_i
    with open(loadshapes_ev_path, "w") as f_ls:
        f_ls.write("! EV LoadShapes (uncontrolled + controlled)\n\n")
        for i in range(N_u):
            row = arr_u[i, :]
            f_ls.write(f"New Loadshape.EVu_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")
        for i in range(N_c):
            row = arr_c[i, :]
            f_ls.write(f"New Loadshape.EVc_{i} npts={row.size} interval=0.25 mult=({' '.join(f'{v:.4f}' for v in row)})\n")

    # Append EV loads (two legs _1/_2) using attributes from parsed_loads_map
    with open(loads_ev_path, "a") as f_ld:
        f_ld.write("\n! EV Loads (mixed types)\n\n")
        # uncontrolled
        for i, base in enumerate(json_ev_un):
            n1 = base + "_1"; n2 = base + "_2"
            if n1 not in parsed_loads_map or n2 not in parsed_loads_map:
                # fallback: try any 1φ load
                candidates = [n for n,a in parsed_loads_map.items() if a.get("ph") == "1"]
                if not candidates:
                    continue
                n1 = candidates[0]
                stem = re.sub(r"_[0-9]+$", "", n1)
                n2   = stem + "_2" if stem + "_2" in parsed_loads_map else n1
            for suff, info in zip(("_1","_2"), (parsed_loads_map[n1], parsed_loads_map[n2])):
                ev_load_name = f"EVu_{base}{suff}"
                f_ld.write(
                    f"New Load.{ev_load_name} conn={info['conn']} bus1={info['bus1']} kV={info['kV']} "
                    f"Vminpu=0.8 Vmaxpu=1.2 model=1 phases={info['ph']} "
                    f"kW=0.5 pf=1 daily=EVu_{i}\n"
                )
        # controlled
        for i, base in enumerate(json_ev_ct):
            n1 = base + "_1"; n2 = base + "_2"
            if n1 not in parsed_loads_map or n2 not in parsed_loads_map:
                candidates = [n for n,a in parsed_loads_map.items() if a.get("ph") == "1"]
                if not candidates:
                    continue
                n1 = candidates[0]
                stem = re.sub(r"_[0-9]+$", "", n1)
                n2   = stem + "_2" if stem + "_2" in parsed_loads_map else n1
            for suff, info in zip(("_1","_2"), (parsed_loads_map[n1], parsed_loads_map[n2])):
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
            if "Redirect LoadShapes.dss" in ln and not inserted:
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
# Controller sizing knobs (override with env if desired)
SC_KW_TARGET_FACTOR = float(os.environ.get("SC_KW_TARGET_FACTOR", "0.8"))  # fraction of total storage kW
SC_KW_TARGET_LOW    = float(os.environ.get("SC_KW_TARGET_LOW",  "0.0"))    # charge threshold
SC_RESERVE_PCT      = float(os.environ.get("SC_RESERVE_PCT",    "20"))     # %Reserve

storage_names = []       # DSS object names without class prefix (e.g., 'storage_busA')
storage_objnames = []    # Full class-qualified ('Storage.storage_busA')
storage_objnames_2 = []
total_storage_kW = 0.0
n_storage = 0

if storage_targets:
    with open(storage_path, "w", encoding="utf-8") as f_st:
        f_st.write("! ==========================\n! STORAGE ELEMENTS (from JSON targets)\n! ==========================\n\n")
        for full in storage_targets:
            info = parsed_loads_map.get(full)
            if not info:
                continue

            pk = peak_kw_for_load(full)  # your existing helper
            kWRated  = max(5.0, round(STORAGE_KW_PER_PEAK * pk, 3))
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

            storage_names.append(stg_name)
            storage_objnames.append(f"Storage.{stg_name}")
            storage_objnames_2.append(f"{stg_name}")
            total_storage_kW += kWRated
            n_storage += 1

        # --- Controller (only if we created storages) ---
        if n_storage > 0:
            anchor_elem = find_controller_anchor(master_dss_path) or "Line.l(r:udt12274-uhs0_1247)"
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
    if n_storage > 0 and not any("Redirect Storage.dss" in ln for ln in ml):
        new_ml.append("\n! Added Storage file\nRedirect Storage.dss\n")
    if monitor_export_lines:
        new_ml.append("\n! Export monitor data for storage\n")
        new_ml.extend(monitor_export_lines)
    write_lines(master_dss_path, new_ml)

# ---------------- PV (from JSON targets) ----------------
pv_targets      = ASSIGN.get("pv_targets", [])      if isinstance(ASSIGN, dict) else []
n_pv = 0
if PV_KW_PER_PEAK > 0.0 and pv_targets:
    pv_path    = os.path.join(OUT_DIR, "PVSystems.dss")
    pv_ls_path = os.path.join(OUT_DIR, "LoadShapes_PV.dss")
    with open(pv_path, "w") as f_pv, open(pv_ls_path, "w") as f_ls:
        f_pv.write("! PV SYSTEMS (from JSON targets)\n\n")
        f_ls.write("! PV LoadShapes\n\n")
        season = (ASSIGN.get("season") or "summer").lower()
        profile = irradiance_summer_padded if season == "summer" else irradiance_winter_padded
        prof_str = " ".join(str(v) for v in profile)

        for idx, full in enumerate(pv_targets):
            info = parsed_loads_map.get(full)
            if not info:
                continue
            pk = peak_kw_for_load(full)
            pv_kw   = max(10.0, round(PV_KW_PER_PEAK * pk, 1))
            busname = info["bus1"].split('.')[0]
            ph      = info.get("ph", "1")
            bus_str = f"{busname}.1.2.3" if ph == "3" else info["bus1"]
            ls_name = f"PVShape_{idx}"
            pv_name = f"pv_{full}"
            f_ls.write(f"New Loadshape.{ls_name} npts={IRRADIANCE_NPTS} interval={IRR_INTERVAL_H} mult=({prof_str})\n")
            f_pv.write(
                f"New PVSystem.{pv_name} phases={ph} bus1={bus_str} kV={info['kV']} "
                f"kVA={pv_kw*1.1:.1f} pmpp={pv_kw:.1f} pf=1 %Cutin=0.1 %Cutout=0.1 effcurve=myEff "
                f"daily={ls_name} irradiance=1\n\n"
            )
            n_pv += 1

    # Ensure Master includes these redirects
    if master_dss_path:
        ml = read_lines(master_dss_path)
        new_ml = ml[:]
        if n_pv > 0 and not any("Redirect LoadShapes_PV.dss" in ln for ln in ml):
            new_ml.append("\n! Added PV loadshape\nRedirect LoadShapes_PV.dss\n")
        if n_pv > 0 and not any("Redirect PVSystems.dss" in ln for ln in ml):
            new_ml.append("\n! Added PV items\nRedirect PVSystems.dss\n")
        write_lines(master_dss_path, new_ml)

# Finally, force Master to a DAILY run (96×15m), and (optionally) comment plot lines
retarget_master_to_daily(master_dss_path, npts=96, stepsize="15m")

# patch Master
if master_dss_path:
    # --- Finalize Master to a DAILY run (96×15m) ---
    retarget_master_to_daily(master_dss_path, npts=96, stepsize="15m")
    ensure_redirects_before_solve(master_dss_path)
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
DSSobj   = cc.CreateObject("OpenDSSEngine.DSS")
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
    # Force DAILY time-series: 96 × 15-minute steps
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
    print(f"Converged? {DSScircuit.Solution.Converged}")


print("✅ Finished single-scenario deploy.")
print(f"Time taken: {time.time() - START_TIME:.2f} s")
sys.exit(0)
