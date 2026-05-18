# -*- coding: utf-8 -*-
"""
instantiate_circuits_and_runs.py  (procedural; mixes with EV split)
-------------------------------------------------------------------
- Discovers feeders under ../3_smartds/uhsX_1247/uhsX_1247--udtYYYY
- For each feeder × mix:
    * Copies feeder into <substation>_circuit_<idx>_<mix_name>/
    * Rewrites LoadShapes.dss to consolidated ../profiles_use_bench/<circuit>/
    * Normalizes Loads.dss (yearly->daily, kW=1, kvar=1), with flat-ones patch if CSVs missing
    * Assigns EV/PV/Storage:
         - EV split into *uncontrolled* and *controlled* disjoint sets
         - min-one for EV/Storage/PV when their perc > 0 and eligibles exist
    * Writes scenario_assignments.json:
         - ev_loads_uncontrolled, ev_loads_controlled, ev_split
         - storage_targets, pv_targets, disjoint_sets, season, etc.
    * Patches runner and (optionally) runs it.

Keeps the procedural style and your working behaviors.
"""

import os, re, sys, time, json, pickle, shutil, subprocess, csv
from copy import deepcopy
from pathlib import Path
from typing import Optional, Iterable
from collections import defaultdict
import math, random

# ==== GLOBAL COLLECTORS (heating assignments across all circuits/mixes) ====
# Toggle if you want the very detailed per-loadshape file (can be large)
COLLECT_ASSIGN_FULL = True

ASSIGN_SUMMARY_ROWS = []   # one row per (circuit folder × mix)
ASSIGN_FULL_ROWS    = []   # one row per (circuit folder × mix × daily_name)

'''
THIS SCRIPT WITH A FILTER IS USED AFTER DISCOVERY OF CIRCUITS WITH RUN ERRORS (THAT CAN BE FIXED) BUT RIGHT NOW BREAK THE AUTOMATION OF THE WORKFLOW.
'''
# Circuits to skip everywhere (by circuit number from REVERSE_CIRCUIT_MAP)
SKIP_CIRCUITS = {36, 12, 13}

START_PROCESS = time.time()

FORCE_NPTS = 96
FORCE_INTERVAL = 0.25

# -----------------------
# === USER CONFIG ===
# -----------------------
BASE_DIR = Path('.').resolve()

BOOL_PASS_ON_EXISTING_FOLDER = False  # True → skip if exists; False → delete/replace

# Map dashed feeder -> circuit_n
REVERSE_CIRCUIT_MAP = {
    "uhs0_1247--udt12274": "circuit_1",
    "uhs0_1247--udt14717": "circuit_2",
    "uhs0_1247--udt16115": "circuit_3",
    "uhs1_1247--udt15926": "circuit_4",
    "uhs1_1247--udt20176": "circuit_5",
    "uhs2_1247--udt10746": "circuit_6",
    "uhs2_1247--udt12473": "circuit_7",
    "uhs2_1247--udt9312": "circuit_8",
    "uhs3_1247--udt1567": "circuit_9",
    "uhs3_1247--udt1571": "circuit_10",
    "uhs3_1247--udt1582": "circuit_11",
    "uhs4_1247--p1umv7": "circuit_12",
    "uhs4_1247--p1umv8": "circuit_13",
    "uhs4_1247--udt11389": "circuit_14",
    "uhs4_1247--udt12982": "circuit_15",
    "uhs5_1247--udt159": "circuit_16",
    "uhs5_1247--udt18558": "circuit_17",
    "uhs5_1247--udt19869": "circuit_18",
    "uhs5_1247--udt20368": "circuit_19",
    "uhs6_1247--udt10788": "circuit_20",
    "uhs6_1247--udt6570": "circuit_21",
    "uhs6_1247--udt9964": "circuit_22",
    "uhs7_1247--udt15849": "circuit_23",
    "uhs7_1247--udt9662": "circuit_24",
    "uhs7_1247--udt9675": "circuit_25",
    "uhs8_1247--udt12494": "circuit_26",
    "uhs8_1247--udt7252": "circuit_27",
    "uhs9_1247--udt11456": "circuit_28",
    "uhs9_1247--udt13714": "circuit_29",
    "uhs9_1247--udt14110": "circuit_30",
    "uhs9_1247--udt16813": "circuit_31",
    "uhs9_1247--udt2508": "circuit_32",
    "uhs10_1247--udt11713": "circuit_33",
    "uhs10_1247--udt12084": "circuit_34",
    "uhs10_1247--udt13528": "circuit_35",
    "uhs11_1247--p1umv22": "circuit_36",
    "uhs11_1247--udt7105": "circuit_37",
    "uhs11_1247--udt8110": "circuit_38",
    "uhs12_1247--udt1278": "circuit_39",
    "uhs12_1247--udt15482": "circuit_40",
    "uhs12_1247--udt15805": "circuit_41",
    "uhs12_1247--udt17650": "circuit_42",
    "uhs13_1247--udt4015": "circuit_43",
    "uhs13_1247--udt4819": "circuit_44",
    "uhs14_1247--udt11665": "circuit_45",
    "uhs14_1247--udt12226": "circuit_46",
    "uhs14_1247--udt5493": "circuit_47",
    "uhs15_1247--udt19670": "circuit_48",
    "uhs15_1247--udt20824": "circuit_49",
    "uhs16_1247--udt15512": "circuit_50",
    "uhs16_1247--udt310": "circuit_51",
    "uhs17_1247--udt6592": "circuit_52",
    "uhs17_1247--udt9551": "circuit_53",
    "uhs18_1247--udt11616": "circuit_54",
    "uhs18_1247--udt13374": "circuit_55",
    "uhs18_1247--udt17294": "circuit_56",
    "uhs19_1247--udt15839": "circuit_57",
    "uhs19_1247--udt19872": "circuit_58",
    "uhs20_1247--udt5173": "circuit_59",
    "uhs20_1247--udt8894": "circuit_60",
    "uhs20_1247--udt9897": "circuit_61",
}

SMARTDS_ROOT = (BASE_DIR / '..' / '3_smartds').resolve()
HP_BASELINE_ROOT = (BASE_DIR / '..' / 'on_4_profhp').resolve()
HP_DM_ROOT       = (BASE_DIR / '..' / 'on_6_profhp_dm').resolve()
HP_UN_ROOT       = (BASE_DIR / '..' / 'on_7_profhp_un').resolve()

PROFILES_USE_BENCH_DIR = (BASE_DIR / 'profiles_use_bench').resolve()
PROFILES_USE_BENCH_DIR.mkdir(exist_ok=True)

RUNNER_BASENAME = 'power_flow_sim_daily_EV_STO_DG_deploy.py'  # we will patch+run this one

# Limit feeders for testing (None = all)
MAX_FEEDERS = None

# Defaults (used when a mix omits them)
DEFAULT_LVL2_PERC = 0.80
DEFAULT_DISJOINT  = True

# If True, launch the runner after preparing each circuit
RUN_AFTER_PREP = False # True

# State/Season used to build bucket name: "<STATE>_<circuit_n>_<SEASON>"
STATE  = os.environ.get('STATE', 'MI')
SEASON = os.environ.get('SEASON', 'winter')

# Optional: default split between controlled vs uncontrolled EVs when a mix omits it
EV_SPLIT_CTL_DEFAULT = float(os.environ.get('EV_SPLIT_CONTROLLED', '0.5'))  # 0..1

# Path to your DOE-generated mixes file
MIXES_FILE = Path("mixes_lhs.json")   # or mixes_sobol.json

with MIXES_FILE.open("r", encoding="utf-8") as f:
    MIXES = json.load(f)

# print('Check the mixes')
# sys.exit()

# -----------------------
# Small helpers
# -----------------------
def force_loadshape_daily_96(line: str, npts: int = FORCE_NPTS, interval: float = FORCE_INTERVAL) -> str:
    """
    Normalize a 'New Loadshape...' line to daily 96 pts:
    - remove sinterval=...
    - set/replace npts=96 and interval=0.25
    - set useactual=no if present
    """
    # remove any sinterval=...
    line = re.sub(r'(?i)\bsinterval\s*=\s*\S+', '', line)
    # normalize 'useactual'
    if re.search(r'(?i)\buseactual\s*=', line):
        line = re.sub(r'(?i)\buseactual\s*=\s*\w+', 'useactual=no', line)
    # npts
    if re.search(r'(?i)\bnpts\s*=', line):
        line = re.sub(r'(?i)\bnpts\s*=\s*\d+', f'npts={npts}', line)
    else:
        line = line.rstrip() + f' npts={npts}'
    # interval
    if re.search(r'(?i)\binterval\s*=', line):
        line = re.sub(r'(?i)\binterval\s*=\s*[\d\.]+', f'interval={interval}', line)
    else:
        line = line.rstrip() + f' interval={interval}'
    # light whitespace cleanup
    line = re.sub(r'\s{2,}', ' ', line)
    return line

def bucket_from_map(feeder_name: str, state: str, season: str) -> Optional[str]:
    circ = REVERSE_CIRCUIT_MAP.get(feeder_name)
    if not circ:
        return None
    return f"{state}_{circ}_{season}"  # e.g. "NC_circuit_1_summer"

def parse_means_for_daily(loads_original_path: Path):
    """Return (per_daily_mean: dict[name]=(mean_kw, mean_kvar), global_means=(kw,kvar))."""
    sums = defaultdict(lambda: [0.0, 0.0, 0])
    sum_kw_all = 0.0; sum_kvar_all = 0.0; cnt_all = 0
    if not loads_original_path.exists():
        return {}, (1.0, 0.0)
    with loads_original_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line.lower().startswith("new load."):
                continue
            m_daily = re.search(r'\b(?:yearly|daily)=(\S+)', line, flags=re.IGNORECASE)
            m_kw    = re.search(r'\bkW=\s*([0-9]*\.?[0-9]+)', line, flags=re.IGNORECASE)
            m_kvar  = re.search(r'\bkvar=\s*([0-9]*\.?[0-9]+)', line, flags=re.IGNORECASE)
            if not m_daily: 
                continue
            nm   = m_daily.group(1)
            kw   = float(m_kw.group(1))   if m_kw   else 0.0
            kvar = float(m_kvar.group(1)) if m_kvar else 0.0
            sums[nm][0] += kw; sums[nm][1] += kvar; sums[nm][2] += 1
            sum_kw_all  += kw; sum_kvar_all += kvar; cnt_all += 1
    per = {nm: (s[0]/s[2], s[1]/s[2]) for nm, s in sums.items() if s[2]}
    glob = ((sum_kw_all/cnt_all) if cnt_all else 1.0,
            (sum_kvar_all/cnt_all) if cnt_all else 0.0)
    return per, glob

def make_ones_list(npts: int) -> str:
    return " ".join(["1"] * int(npts))

def index_csvs(root: Path, include_only: Optional[Iterable[str]] = None) -> dict:
    """Index CSVs ONLY under <root>/daily_csvs[/<bucket>...]"""
    mapping = {}
    daily = root / "daily_csvs"
    if not daily.exists():
        return mapping
    buckets = [d for d in daily.iterdir() if d.is_dir()]
    if include_only:
        allowed = {str(x) for x in include_only}
        buckets = [d for d in buckets if d.name in allowed]
    for bucket in buckets:
        for dirpath, _, filenames in os.walk(bucket):
            for fn in filenames:
                if fn.lower().endswith(".csv"):
                    mapping.setdefault(fn, Path(dirpath) / fn)
    return mapping

# =========================================
# === Discover nested SMART-DS feeders  ===
# =========================================
'''
This part changes significantly in this version because it must skip some folders.
'''
feeders = []
skipped = []
if not SMARTDS_ROOT.exists():
    print(f"⚠️ SMART-DS root not found: {SMARTDS_ROOT}")
    sys.exit(1)

for sub in sorted(SMARTDS_ROOT.iterdir()):
    if not sub.is_dir() or not sub.name.startswith('uhs'):
        continue
    for child in sorted(sub.iterdir()):
        if not child.is_dir():
            continue
        has_loads  = any(nm.lower() == 'loads.dss'      for nm in os.listdir(child))
        has_shapes = any(nm.lower() == 'loadshapes.dss' for nm in os.listdir(child))
        #if has_loads and has_shapes:
        #    feeders.append(child)
        if not (has_loads and has_shapes):
            continue

        # --- NEW: map feeder -> circuit_n and apply SKIP_CIRCUITS
        feeder_name = child.name  # e.g., 'uhs0_1247--udt12274'
        circ_tag = REVERSE_CIRCUIT_MAP.get(feeder_name)  # 'circuit_1', etc.
        if circ_tag:
            try:
                circ_num = int(circ_tag.split('_')[-1])
            except Exception:
                circ_num = None
        else:
            circ_num = None

        if circ_num is not None and circ_num in SKIP_CIRCUITS:
            skipped.append((feeder_name, circ_num))
            continue

        feeders.append(child)

print(f'🔎 Found {len(feeders)} feeders under {SMARTDS_ROOT}')
if skipped:
    print(f'⏭️  Skipped {len(skipped)} feeders by SKIP_CIRCUITS:')
    for nm, n in skipped:
        print(f'   - {nm}  → circuit_{n}')

if MAX_FEEDERS:
    feeders = feeders[:MAX_FEEDERS]
print(f'🔎 Found {len(feeders)} feeders under {SMARTDS_ROOT}')

# ===============================
# === Main procedural runner  ===
# ===============================
circuit_counter = 1
for feeder in feeders:
    substation_name = feeder.parent.name
    feeder_name     = feeder.name

    #print('check this out')
    # sys.exit()

    # locate Loads/LoadShapes
    loads_src = None; lshp_src = None
    for nm in os.listdir(feeder):
        if nm.lower() == 'loads.dss':       loads_src = feeder / nm
        if nm.lower() == 'loadshapes.dss':  lshp_src  = feeder / nm
    if not (loads_src and lshp_src):
        print(f"⚠️ Skipping feeder (missing DSS): {feeder}")
        continue

    # parse Loads for bases, daily mapping, and phases
    unique_bases  = set()
    base_to_daily = {}
    parsed_map    = {}  # full -> {'phases': '1'|'3'}
    with loads_src.open('r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line.lower().startswith('new load.'): 
                continue
            m_name = re.search(r"New\s+Load\.(\S+)", line, flags=re.IGNORECASE)
            if not m_name: continue
            full = m_name.group(1)
            base = re.sub(r"_[0-9]+$", "", full)
            if base != 'load':
                unique_bases.add(base)
            m_daily = re.search(r"\byearly=(\S+)", line, flags=re.IGNORECASE)
            if m_daily:
                base_to_daily.setdefault(base, set()).add(m_daily.group(1).strip())
            # print('stop here')
            # sys.exit()
            m_ph = re.search(r"\bphases=(\d+)", line, flags=re.IGNORECASE)
            parsed_map[full] = {'phases': m_ph.group(1) if m_ph else None}

    three_phase_full = [nm for nm, info in parsed_map.items() if info.get('phases') == '3']
    three_phase_base = sorted(set([re.sub(r"_[0-9]+$", "", nm) for nm in three_phase_full]))

    # collect the CSV names needed by LoadShapes.dss
    required_bases = set()
    with lshp_src.open("r", encoding="utf-8") as _f:
        for _line in _f:
            if _line.strip().lower().startswith("new loadshape") and "file=" in _line.lower():
                _m = re.search(r"New\s+Loadshape\.(\S+)\s", _line, flags=re.IGNORECASE)
                if _m:
                    required_bases.add(_m.group(1))
    required_csvs = set()
    for b in required_bases:
        kw_csv   = f"{b}.csv"
        kvar_csv = kw_csv.replace("_kw_", "_kvar_")
        required_csvs.update([kw_csv, kvar_csv])

    # ===== Process each mix =====
    for mix_name, mix_cfg in MIXES.items():
        shares        = mix_cfg['shares']
        heating_seed  = int(mix_cfg.get('heating_seed', 123))
        ev_perc       = float(mix_cfg.get('ev_perc', 0.0))
        ev_lvl2       = float(mix_cfg.get('ev_lvl2_perc', DEFAULT_LVL2_PERC))
        ev_seed       = int(mix_cfg.get('ev_seed', heating_seed))
        storage_perc  = float(mix_cfg.get('storage_perc_3ph', 0.0))
        storage_seed  = int(mix_cfg.get('storage_seed', heating_seed))
        pv_perc       = float(mix_cfg.get('pv_perc_3ph', 0.0))
        pv_seed       = int(mix_cfg.get('pv_seed', heating_seed))
        disjoint_sets = bool(mix_cfg.get('disjoint_sets', DEFAULT_DISJOINT))

        # EV split (controlled/uncontrolled)
        split = mix_cfg.get('ev_split', {})
        split_ctl = float(split.get('controlled', EV_SPLIT_CTL_DEFAULT))
        split_un  = float(split.get('uncontrolled', 1.0 - split_ctl))
        if split_ctl < 0: split_ctl = 0.0
        if split_un  < 0: split_un  = 0.0
        norm = split_ctl + split_un
        if norm <= 0:
            split_ctl, split_un = 0.5, 0.5
        else:
            split_ctl /= norm; split_un = 1.0 - split_ctl

        # dst_folder_name = f"{substation_name}_circuit_{circuit_counter}_{mix_name}"

        # Determine the canonical circuit number from the map
        circ_tag = REVERSE_CIRCUIT_MAP.get(feeder_name)   # e.g. 'circuit_60'
        if circ_tag:
            try:
                circ_num = int(circ_tag.split('_')[-1])
            except Exception:
                circ_num = circuit_counter   # safe fallback
        else:
            # If feeder not in map, fallback to the counter (or you can sys.exit here)
            circ_num = circuit_counter

        # Use the mapped circuit number in the folder name
        dst_folder_name = f"{substation_name}_circuit_{circ_num}_{mix_name}"

        dst_folder      = BASE_DIR / dst_folder_name
        dst_feeder_sub  = dst_folder / feeder_name

        if dst_folder.exists() and BOOL_PASS_ON_EXISTING_FOLDER:
            print(f"🔁 Already exists: {dst_folder_name}, skipping.")
            continue
        if not BOOL_PASS_ON_EXISTING_FOLDER:
            print(f"🗑️ Removing existing: {dst_folder_name}")
            shutil.rmtree(dst_folder, ignore_errors=True)

        # copy feeder into destination
        try:
            shutil.copytree(feeder, dst_feeder_sub)
        except Exception as e:
            print(f"❌ Copy failed {feeder} -> {dst_feeder_sub}: {e}")
            continue
        print(f"\n✅ Created: {dst_folder_name}")

        # ensure EV base data is present
        EV_DATA_SRC = BASE_DIR / "data_ev"
        if EV_DATA_SRC.exists():
            shutil.copytree(EV_DATA_SRC, dst_folder / "data_ev", dirs_exist_ok=True)
            print("  • Copied data_ev/ into circuit folder")
        else:
            print("  • data_ev/ not found at repo root; EV generator will use defaults")

        # paths
        loads_path = None; lshp_path = None
        for nm in os.listdir(dst_feeder_sub):
            if nm.lower() == 'loads.dss':       loads_path = dst_feeder_sub / nm
            if nm.lower() == 'loadshapes.dss':  lshp_path  = dst_feeder_sub / nm

        # backups
        for path in [loads_path, lshp_path]:
            if path is None: continue
            bkp = path.with_name(path.stem + '_original.dss')
            if bkp.exists(): bkp.unlink()
            shutil.copy2(path, bkp)

        # per-bucket indexing (state/season)
        bucket_name = bucket_from_map(feeder_name, STATE, SEASON)
        if bucket_name:
            print(f"  • Using mapped bucket: {bucket_name}")
            idx_baseline = index_csvs(HP_BASELINE_ROOT, include_only={bucket_name})
            idx_dm       = index_csvs(HP_DM_ROOT,       include_only={bucket_name})
            idx_un       = index_csvs(HP_UN_ROOT,       include_only={bucket_name})
        else:
            print("  • No map entry; indexing all daily_csvs (may risk collisions).")
            idx_baseline = index_csvs(HP_BASELINE_ROOT)
            idx_dm       = index_csvs(HP_DM_ROOT)
            idx_un       = index_csvs(HP_UN_ROOT)

        # means for flat-ones patch
        loads_original = loads_path.with_name('Loads_original.dss')
        per_daily_mean, global_mean = parse_means_for_daily(loads_original)

        # coverage diagnostics
        cov_b = sum(1 for fn in required_csvs if fn in idx_baseline)
        cov_d = sum(1 for fn in required_csvs if fn in idx_dm)
        cov_u = sum(1 for fn in required_csvs if fn in idx_un)
        print(f"  • Coverage → baseline {cov_b}/{len(required_csvs)}, dm {cov_d}/{len(required_csvs)}, un {cov_u}/{len(required_csvs)}")

        '''
        # heating assignment (daily -> baseline/dm/un via shares)
        p_b = float(shares.get('baseline', 0.0))
        p_dm= float(shares.get('dm', 0.0))
        p_un= float(shares.get('un', 0.0))

        ttl = p_b + p_dm + p_un
        if ttl <= 0: p_b, p_dm, p_un = 1.0, 0.0, 0.0
        else:        p_b, p_dm, p_un = [x/ttl for x in (p_b, p_dm, p_un)]

        import random
        random.seed(int(heating_seed) + hash((substation_name, feeder_name)) % 10_000_000)

        daily_to_scen = {}
        for base in sorted(unique_bases):
            r = random.random()
            scen = 'baseline' if r < p_b else ('dm' if r < p_b + p_dm else 'un')
            for ls in base_to_daily.get(base, []):
                daily_to_scen[ls] = scen
        '''

        # 1) Normalize shares
        p_b  = float(shares.get('baseline', 0.0))
        p_dm = float(shares.get('dm',       0.0))
        p_un = float(shares.get('un',       0.0))
        tot = p_b + p_dm + p_un
        if tot <= 0:
            p_b, p_dm, p_un = 1.0, 0.0, 0.0
        else:
            p_b, p_dm, p_un = (p_b/tot, p_dm/tot, p_un/tot)

        # 2) Exact counts via largest‑remainder rounding
        bases = list(unique_bases)
        N = len(bases)
        raw = {'baseline': p_b*N, 'dm': p_dm*N, 'un': p_un*N}
        cnt = {k: int(math.floor(v)) for k, v in raw.items()}
        need = N - sum(cnt.values())
        frac = sorted(((raw[k] - cnt[k], k) for k in raw), reverse=True)
        for i in range(need):
            cnt[frac[i % len(frac)][1]] += 1

        # Optional: ensure min‑one for any category with positive share (keeps sum=N)
        if p_b > 0 and cnt['baseline'] == 0:
            donor = max((d for d in ('dm','un') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
            if donor: cnt[donor] -= 1; cnt['baseline'] += 1
        if p_dm > 0 and cnt['dm'] == 0:
            donor = max((d for d in ('baseline','un') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
            if donor: cnt[donor] -= 1; cnt['dm'] += 1
        if p_un > 0 and cnt['un'] == 0:
            donor = max((d for d in ('dm','baseline') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
            if donor: cnt[donor] -= 1; cnt['un'] += 1

        n_b, n_dm, n_un = cnt['baseline'], cnt['dm'], cnt['un']  # totals sum exactly to N

        # 3) Deterministic RNG per feeder (random look, reproducible)
        rng = random.Random(int(heating_seed) + hash((substation_name, feeder_name)) % 10_000_000)

        # 4) Build randomized labels with exact counts, and randomized base order
        labels = (['baseline'] * n_b) + (['dm'] * n_dm) + (['un'] * n_un)
        rng.shuffle(labels)
        rng.shuffle(bases)

        # 5) Map daily loadshape names to scenarios
        daily_to_scen = {}
        for base, scen in zip(bases, labels):
            for ls in base_to_daily.get(base, []):
                daily_to_scen[ls] = scen

        # (Optional) quick sanity print
        print(f"Assigned counts: baseline={n_b}, dm={n_dm}, un={n_un} out of N={N}")
        '''
        n_b  = int(round(p_b  * N))
        n_dm = int(round(p_dm * N))
        # ensure the remainder goes to 'un'
        n_un = max(0, N - n_b - n_dm)

        bases = list(sorted(unique_bases))
        random.seed(int(heating_seed) + hash((substation_name, feeder_name)) % 10_000_000)
        random.shuffle(bases)

        B_set  = set(bases[:n_b])
        DM_set = set(bases[n_b:n_b+n_dm])
        UN_set = set(bases[n_b+n_dm:])

        daily_to_scen = {}
        for base in bases:
            scen = 'baseline' if base in B_set else ('dm' if base in DM_set else 'un')
            for ls in base_to_daily.get(base, []):
                daily_to_scen[ls] = scen
        '''

        # ----- STORE ASSIGNMENT for auditing -----
        # If you also want base-level counts, keep base_to_scen while you build daily_to_scen
        # (If you already have 'bases' and 'labels' from your exact-share code, use them)
        base_to_scen = {}
        # If you created 'bases' and 'labels' earlier, do it this way:
        # for base, scen in zip(bases, labels):
        #     base_to_scen[base] = scen
        #     for ls in base_to_daily.get(base, []):
        #         daily_to_scen[ls] = scen

        # If not, infer base_to_scen from the first daily name per base:
        if not base_to_scen:
            for base in sorted(unique_bases):
                # find one representative daily name for this base
                dnames = list(base_to_daily.get(base, []))
                if not dnames:
                    continue
                scen = daily_to_scen.get(dnames[0], 'baseline')
                base_to_scen[base] = scen

        # --- counts by daily-name (what LoadShapes.dss actually references) ---
        n_b_daily  = sum(1 for v in daily_to_scen.values() if v == 'baseline')
        n_dm_daily = sum(1 for v in daily_to_scen.values() if v == 'dm')
        n_un_daily = sum(1 for v in daily_to_scen.values() if v == 'un')
        N_daily    = n_b_daily + n_dm_daily + n_un_daily

        # --- counts by base (one vote per logical base) ---
        n_b_base   = sum(1 for v in base_to_scen.values() if v == 'baseline')
        n_dm_base  = sum(1 for v in base_to_scen.values() if v == 'dm')
        n_un_base  = sum(1 for v in base_to_scen.values() if v == 'un')
        N_base     = n_b_base + n_dm_base + n_un_base

        # record a summary row (utf‑8‑sig so Excel opens it nicely)
        ASSIGN_SUMMARY_ROWS.append({
            "substation":       substation_name,
            "feeder_name":      feeder_name,
            "circuit_folder":   dst_folder_name,
            "mix":              str(mix_name),
            "season":           SEASON,
            "share_baseline":   p_b,
            "share_dm":         p_dm,
            "share_un":         p_un,
            "n_daily_baseline": n_b_daily,
            "n_daily_dm":       n_dm_daily,
            "n_daily_un":       n_un_daily,
            "N_daily_total":    N_daily,
            "n_base_baseline":  n_b_base,
            "n_base_dm":        n_dm_base,
            "n_base_un":        n_un_base,
            "N_base_total":     N_base,
        })

        # collect the full mapping (can be large; toggle with COLLECT_ASSIGN_FULL)
        if COLLECT_ASSIGN_FULL:
            for dname, scen in daily_to_scen.items():
                ASSIGN_FULL_ROWS.append((
                    substation_name,
                    feeder_name,
                    dst_folder_name,
                    str(mix_name),
                    SEASON,
                    dname,
                    scen
                ))

        # print('get until here')
        # sys.exit()

        # rewrite LoadShapes.dss, copy CSVs, or use flat-ones patch
        profiles_dest_dir = PROFILES_USE_BENCH_DIR / dst_folder_name
        profiles_dest_dir.mkdir(parents=True, exist_ok=True)

        tracking = {"missing_files": {}, "missing_files_track": {}, "all_files_track": {},
                    "bucket_choices": {"baseline": bucket_name or "(all)", "dm": bucket_name or "(all)", "un": bucket_name or "(all)"}}
        missing_bases_used_flat = set()

        with lshp_path.open('r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            if line.strip().lower().startswith('new loadshape') and 'file=' in line.lower():
                m = re.search(r"New\s+Loadshape\.(\S+)\s", line, flags=re.IGNORECASE)
                if m:
                    base = m.group(1)
                    kw_csv   = f"{base}.csv"
                    kvar_csv = kw_csv.replace('_kw_', '_kvar_')
                    scen     = daily_to_scen.get(base, 'baseline')

                    if scen == 'baseline':
                        src_kw = idx_baseline.get(kw_csv); src_kvar = idx_baseline.get(kvar_csv)
                    elif scen == 'dm':
                        src_kw = idx_dm.get(kw_csv);       src_kvar = idx_dm.get(kvar_csv)
                    else:
                        src_kw = idx_un.get(kw_csv);       src_kvar = idx_un.get(kvar_csv)

                    if src_kw is None or src_kvar is None:
                        # fallback to baseline indexes
                        src_kw = src_kw   or idx_baseline.get(kw_csv)
                        src_kvar = src_kvar or idx_baseline.get(kvar_csv)

                    if src_kw is None or src_kvar is None:
                        # flat-ones patch
                        npts = 96
                        ones = make_ones_list(npts)
                        line = re.sub(r"mult\s*=\s*\(file=.*?\)",  f"mult=({ones})",  line, flags=re.IGNORECASE)
                        line = re.sub(r"qmult\s*=\s*\(file=.*?\)", f"qmult=({ones})", line, flags=re.IGNORECASE)
                        line = force_loadshape_daily_96(line, FORCE_NPTS, FORCE_INTERVAL)
                        missing_bases_used_flat.add(base)
                        tracking['missing_files'].setdefault(base, []).append(kw_csv)
                    else:
                        shutil.copy2(src_kw,   profiles_dest_dir / kw_csv)
                        shutil.copy2(src_kvar, profiles_dest_dir / kvar_csv)
                        rel = f"../profiles_use_bench/{dst_folder_name}/"
                        line = re.sub(r"mult\s*=\s*\(file=.*?\)",  f"mult=(file={rel}{kw_csv})",   line, flags=re.IGNORECASE)
                        line = re.sub(r"qmult\s*=\s*\(file=.*?\)", f"qmult=(file={rel}{kvar_csv})", line, flags=re.IGNORECASE)
                        line = force_loadshape_daily_96(line, FORCE_NPTS, FORCE_INTERVAL)
                        tracking['all_files_track'][base] = kw_csv
            new_lines.append(line)
        with lshp_path.open('w', encoding='utf-8') as f:
            f.writelines(new_lines)

        # Normalize Loads.dss (and preserve magnitude for flat-ones bases)
        with loads_path.open('r', encoding='utf-8') as f:
            orig = f.readlines()
        upd = []
        for line in orig:
            if line.lower().startswith('new load.'):
                if 'yearly=' in line:
                    line = re.sub(r'yearly=', 'daily=', line, flags=re.IGNORECASE)
                m_daily = re.search(r'\bdaily=(\S+)', line, flags=re.IGNORECASE)
                daily_name = m_daily.group(1) if m_daily else None
                if daily_name and daily_name in missing_bases_used_flat:
                    est_kw, est_kvar = per_daily_mean.get(daily_name, global_mean)
                    if 'kW=' in line:   line = re.sub(r"kW=\s*[0-9]*\.?[0-9]+", f"kW={est_kw:.6f}",   line, flags=re.IGNORECASE)
                    else:               line = line.rstrip() + f" kW={est_kw:.6f}"
                    if 'kvar=' in line: line = re.sub(r"kvar=\s*[0-9]*\.?[0-9]+", f"kvar={est_kvar:.6f}", line, flags=re.IGNORECASE)
                    else:               line = line.rstrip() + f" kvar={est_kvar:.6f}"
                else:
                    if 'kW='   in line: line = re.sub(r"kW=\s*\d+(\.\d+)?",   "kW=1", line)
                    if 'kvar=' in line: line = re.sub(r"kvar=\s*\d+(\.\d+)?", "kvar=1", line)
            upd.append(line)
        with loads_path.open('w', encoding='utf-8') as f:
            f.writelines(upd)

        # =================== EV / PV / Storage targets ===================
        def clamp01(x): return max(0.0, min(1.0, float(x)))
        ev_perc      = clamp01(ev_perc)
        storage_perc = clamp01(storage_perc)
        pv_perc      = clamp01(pv_perc)

        eligible_ev  = len(unique_bases)
        eligible_3ph = len(three_phase_base)

        # raw counts
        n_ev  = int(round(ev_perc      * eligible_ev))
        n_sto = int(round(storage_perc * eligible_3ph))
        n_pv  = int(round(pv_perc      * eligible_3ph))

        # min-one rules (only if perc>0 and eligibles exist)
        if ev_perc > 0 and eligible_ev  > 0:    n_ev  = max(1, min(n_ev,  eligible_ev))
        if storage_perc > 0 and eligible_3ph > 0:n_sto = max(1, min(n_sto, eligible_3ph))
        if pv_perc > 0 and eligible_3ph > 0:     n_pv  = max(1, min(n_pv,  eligible_3ph))

        # If we must have both EV types and n_ev==1, bump to 2 when possible
        if n_ev == 1 and ev_perc > 0 and eligible_ev >= 2:
            print("  • Bumping EV count from 1 → 2 to realize both EV types.")
            n_ev = 2

        # deterministic picks
        def pick(seed_val, items, k):
            import random as _r
            if k <= 0 or len(items) == 0: return []
            rng = _r.Random(int(seed_val) + hash(dst_folder_name) % 10_000_000)
            items_copy = list(items)
            rng.shuffle(items_copy)
            return items_copy[:min(k, len(items_copy))]

        ev_hosts_all = pick(ev_seed, sorted(unique_bases), n_ev)

        # split EV hosts into uncontrolled vs controlled (disjoint)
        n_ev_ctl = int(round(n_ev * split_ctl))
        n_ev_un  = n_ev - n_ev_ctl
        if n_ev >= 2:
            # ensure non-zero both sides if we asked for EVs
            if n_ev_ctl == 0: n_ev_ctl, n_ev_un = 1, n_ev - 1
            if n_ev_un  == 0: n_ev_un,  n_ev_ctl = 1, n_ev - 1
        ev_loads_un  = ev_hosts_all[:n_ev_un]
        ev_loads_ctl = ev_hosts_all[n_ev_un:]

        # Storage / PV on 3φ bases
        '''
        THIS IS ANOTHER CHANGE NEEDED IN THE SYSTEM
        sto_base  = pick(storage_seed, three_phase_base, n_sto)
        remaining = [b for b in three_phase_base if b not in sto_base] if disjoint_sets else list(three_phase_base)
        if n_pv > 0 and len(remaining) == 0 and len(three_phase_base) > 0:
            remaining = list(three_phase_base)  # relax disjointness to satisfy min-one PV
        pv_base   = pick(pv_seed, remaining, n_pv)

        storage_targets = [b + '_1' for b in sto_base]
        pv_targets      = [b + '_1' for b in pv_base]
        '''
        # Eligible 3-phase bases chosen for storage
        sto_base  = pick(storage_seed, three_phase_base, n_sto)

        # Respect disjointness for PV if requested
        remaining = [b for b in three_phase_base if b not in sto_base] if disjoint_sets else list(three_phase_base)

        # If disjoint is enforced but storage consumed all eligibles, relax so PV isn't forced to zero
        if n_pv > 0 and len(remaining) == 0 and len(three_phase_base) > 0:
            remaining = list(three_phase_base)

        # Choose PV bases from the remaining pool
        pv_base   = pick(pv_seed, remaining, n_pv)

        # Build a map base -> available full names actually present in Loads.dss
        base_to_full3 = {}
        for ff in three_phase_full:
            b = re.sub(r"_[0-9]+$", "", ff)
            base_to_full3.setdefault(b, []).append(ff)

        # For each selected base, pick the first available full name
        storage_targets = [base_to_full3[b][0] for b in sto_base if base_to_full3.get(b)]
        pv_targets      = [base_to_full3[b][0] for b in pv_base   if base_to_full3.get(b)]
        '''
        up until here
        '''
        assignments = {
            "ev": {"perc": ev_perc, "lvl2_perc": ev_lvl2, "seed": ev_seed},
            "ev_split": {"controlled": split_ctl, "uncontrolled": split_un},
            "storage": {"perc_3ph": storage_perc, "seed": storage_seed},
            "pv": {"perc_3ph": pv_perc, "seed": pv_seed},
            "disjoint_sets": disjoint_sets,
            "ev_loads_uncontrolled": ev_loads_un,
            "ev_loads_controlled":   ev_loads_ctl,
            "ev_loads": ev_hosts_all,   # union (for backwards compatibility)
            "storage_targets": storage_targets,
            "pv_targets":      pv_targets,
            "season": SEASON
        }
        (dst_folder / 'scenario_assignments.json').write_text(json.dumps(assignments, indent=2), encoding='utf-8')

        print(f"  • Assigned (mix={mix_name}) "
              f"EV_unctl={len(ev_loads_un)} + EV_ctl={len(ev_loads_ctl)} (total {len(ev_hosts_all)} @ {ev_perc:.2%}), "
              f"Storage={len(storage_targets)} ({storage_perc:.2%}), PV={len(pv_targets)} ({pv_perc:.2%})")

        # ================= patch runner & optionally run ==================
        runner_path = dst_folder / RUNNER_BASENAME
        if not runner_path.exists():
            src_runner = BASE_DIR / RUNNER_BASENAME
            if src_runner.exists():
                shutil.copy2(src_runner, runner_path)
                print("  • Copied runner into circuit folder")
            else:
                print(f"  ! Runner {RUNNER_BASENAME} not found at base. Skipping run.")
                continue

        txt = runner_path.read_text(encoding='utf-8')
        if 'import json' not in txt:
            txt = txt.replace('import sys', 'import sys\nimport json')

        # Patch EV percentages textually (best-effort)
        txt = re.sub(r"(ev_perc\s*=\s*)([0-9]*\.?[0-9]+)",          rf"\g<1>{ev_perc}", txt)
        txt = re.sub(r"(lvl2_charger_perc\s*=\s*)([0-9]*\.?[0-9]+)", rf"\g<1>{ev_lvl2}", txt)

        # Ensure circuit_name
        if "circuit_name = " in txt:
            txt = re.sub(r"circuit_name\s*=\s*['\"].*?['\"]", f"circuit_name = '{dst_folder_name}'", txt)

        runner_path.write_text(txt, encoding='utf-8')
        print("  • Patched runner (EV % + circuit_name)")

        if RUN_AFTER_PREP:
            print(f"  🚀 Running {RUNNER_BASENAME} in {dst_folder_name} ...")
            subprocess.run(['python', RUNNER_BASENAME], cwd=str(dst_folder))

    circuit_counter += 1

# ==== WRITE GLOBAL SUMMARY / FULL MAPS ====
try:
    # 3a) Summary CSV
    sum_path = BASE_DIR / "heating_assignment__SUMMARY.csv"
    sum_fields = [
        "substation","feeder_name","circuit_folder","mix","season",
        "share_baseline","share_dm","share_un",
        "n_daily_baseline","n_daily_dm","n_daily_un","N_daily_total",
        "n_base_baseline","n_base_dm","n_base_un","N_base_total",
    ]
    import csv, json
    with open(sum_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=sum_fields)
        w.writeheader()
        for row in ASSIGN_SUMMARY_ROWS:
            w.writerow(row)
    print(f"[audit] Wrote {len(ASSIGN_SUMMARY_ROWS)} rows → {sum_path.name}")

    # 3b) Full mapping CSV (optional, can be large)
    if COLLECT_ASSIGN_FULL:
        full_path = BASE_DIR / "heating_assignment__FULL.csv"
        with open(full_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["substation","feeder_name","circuit_folder","mix","season","daily_name","scenario"])
            w.writerows(ASSIGN_FULL_ROWS)
        print(f"[audit] Wrote {len(ASSIGN_FULL_ROWS)} rows → {full_path.name}")

    # 3c) (Optional) one compact JSON for programmatic use
    #     { circuit_folder → { mix → { daily_name → scenario } } }
    compact = {}
    for sub, fed, cf, mix, season, dname, scen in ASSIGN_FULL_ROWS if COLLECT_ASSIGN_FULL else []:
        compact.setdefault(cf, {}).setdefault(mix, {})[dname] = scen
    if compact:
        json_path = BASE_DIR / "heating_assignment__FULL.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(compact, f, ensure_ascii=False, indent=2)
        print(f"[audit] Wrote JSON → {json_path.name}")

except Exception as e:
    print(f"[audit] Failed to write assignment audit files: {e}")

print("\n🎉 All circuits prepared (and run if enabled)!")
END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} s")
print(str(END_PROCESS - START_PROCESS) + ' s /', str((END_PROCESS - START_PROCESS)/60) + ' min.')
