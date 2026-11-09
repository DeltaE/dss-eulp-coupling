# -*- coding: utf-8 -*-
"""
instantiate_circuits.py  (procedural; mixes with EV split)
---------------------------------------------------------
- Discovers feeders from feeder_registry.json
- For each feeder × mix:
    * Copies feeder into <substation>_circuit_<idx>_<mix_name>/
    * Rewrites LoadShapes.dss to consolidated ../profiles_use_bench/<circuit>/
    * Normalizes Loads.dss (yearly->daily; kW and kvar = the line's share of its customer's
      SMART-DS kW and kvar, heating_split.line_shares); a loadshape without CSVs stops the run
    * Assigns EV/PV/Storage:
         - EV hosts drawn among residential loads (heating_split.load_segment)
         - EV split into *uncontrolled* and *controlled* disjoint sets
         - PV and storage hosts drawn per segment (residential, commercial) with the
           der_sizing switches and storage_hosts rule (deployer_modules/der_sizing.py)
         - min-one for EV/Storage/PV when their perc > 0 and eligibles exist
         - a mix without ev_lvl2_perc, pv_res_perc, pv_com_perc, storage_res_perc or
           storage_com_perc stops the run
    * Writes scenario_assignments.json:
         - ev_loads_uncontrolled, ev_loads_controlled, ev_split
         - pv and storage hosts per segment, storage_targets, pv_targets, season, etc.
    * Patches the runner. Phase 7c (run_circuits.py) runs it.

Keeps the procedural style and your working behaviors.
"""

import os, re, sys, time, json, shutil, csv, hashlib
from pathlib import Path
from typing import Optional, Iterable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import (heating_label_unit, load_config, load_feeder_registry, load_mixes,
                            peak_day_rule, resolve_work_path)
from heating_split import is_baseline_only, line_shares, load_segment, split_heating
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'deployer_modules'))
from der_sizing import SEGMENTS, der_choice, der_switch, pick_hosts, segment_count

# ==== GLOBAL COLLECTORS (heating assignments across all circuits/mixes) ====
# Toggle if you want the very detailed per-loadshape file (can be large)
COLLECT_ASSIGN_FULL = True

ASSIGN_SUMMARY_ROWS = []   # one row per (circuit folder × mix)
ASSIGN_FULL_ROWS    = []   # one row per (circuit folder × mix × daily_name)

START_PROCESS = time.time()
cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
registry = load_feeder_registry()
feeder_to_circuit = registry["circuit_name_map"]
SKIP_CIRCUITS = {int(n) for n in cfg.get('skip_circuits', [])}

FORCE_NPTS = 96
FORCE_INTERVAL = 0.25

# -----------------------
# === USER CONFIG ===
# -----------------------
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent


def resolve_config_path(path_value):
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _stable_seed_offset(key: str) -> int:
    """Deterministic replacement for hash(...) % 10_000_000.

    Python's hash() is randomized per-process for str/bytes (PYTHONHASHSEED)
    from 3.3 onward, so seeding RNGs with it makes runs non-reproducible.
    sha256 is stable across processes/machines/Python versions.
    """
    digest = hashlib.sha256(key.encode()).digest()[:8]
    return int.from_bytes(digest, "big") % 10_000_000

BOOL_PASS_ON_EXISTING_FOLDER = False  # True → skip if exists; False → delete/replace

SMARTDS_ROOT = resolve_config_path(cfg['smart_ds_root'])
HP_BASELINE_ROOT = Path(resolve_work_path("7_circuit_instantiation", STATE + '_4_profhp'))
HP_DM_ROOT       = Path(resolve_work_path("7_circuit_instantiation", STATE + '_6_profhp_dm'))
HP_UN_ROOT       = Path(resolve_work_path("7_circuit_instantiation", STATE + '_7_profhp_un'))
# peak_day_rule (pipeline_config.yaml): with per_circuit, a circuit whose mix is not
# 100 % baseline reads the three profhp roots under <work_root>/mix_days/<mix>/
# (phase mix_days) instead.
PEAK_DAY_RULE = peak_day_rule(cfg)
# heating_label_unit (pipeline_config.yaml): building or customer, the unit the heating
# split counts (heating_split.split_heating).
HEATING_LABEL_UNIT = heating_label_unit(cfg)

PROFILES_USE_BENCH_DIR = Path(resolve_work_path("7_circuit_instantiation", "profiles_use_bench"))
PROFILES_USE_BENCH_DIR.mkdir(exist_ok=True)

RUNNER_BASENAME = 'power_flow_sim_daily_EV_STO_DG_deploy.py'  # we will patch+run this one

# Limit feeders for testing (None = all)
MAX_FEEDERS = cfg.get('max_feeders')
if MAX_FEEDERS is not None:
    MAX_FEEDERS = int(MAX_FEEDERS)

# PV and storage switches per segment and the storage host rule (der_sizing)
PV_ON  = {seg: der_switch(cfg, f"pv_{seg}") for seg in SEGMENTS}
STO_ON = {seg: der_switch(cfg, f"storage_{seg}") for seg in SEGMENTS}
STORAGE_HOSTS = der_choice(cfg, "storage_hosts")
MIX_KEYS_REQUIRED = ("ev_lvl2_perc", "pv_res_perc", "pv_com_perc", "storage_res_perc", "storage_com_perc")

# State/Season used to build bucket name: "<STATE>_<circuit_n>_<SEASON>"

# Optional: default split between controlled vs uncontrolled EVs when a mix omits it
EV_SPLIT_CTL_DEFAULT = float(os.environ.get('EV_SPLIT_CONTROLLED', '0.5'))  # 0..1

# The mixes file, copied there by Phase 7a with its extension kept
MIXES_DIR = Path(resolve_work_path("7_circuit_instantiation"))
MIXES_FILE = next((MIXES_DIR / f"mixes{ext}" for ext in (".yaml", ".yml", ".json")
                   if (MIXES_DIR / f"mixes{ext}").is_file()), MIXES_DIR / "mixes.yaml")
MIXES = load_mixes(MIXES_FILE)

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
    circ = feeder_to_circuit.get(feeder_name)
    if not circ:
        return None
    return f"{state}_{circ}_{season}"

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

def has_required_dss_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        names = {nm.lower() for nm in os.listdir(path)}
    except PermissionError:
        return False
    return "loads.dss" in names and "loadshapes.dss" in names

def circuit_num_from_tag(circ_tag: Optional[str], fallback: Optional[int] = None) -> Optional[int]:
    if not circ_tag:
        return fallback
    try:
        return int(circ_tag.split('_')[-1])
    except Exception:
        return fallback

# =========================================
# === Discover nested SMART-DS feeders  ===
# =========================================
feeders = []
skipped = []
missing_registry_paths = []
if not SMARTDS_ROOT.exists():
    print(f"⚠️ SMART-DS root not found: {SMARTDS_ROOT}")
    sys.exit(1)

for entry in registry["feeders"]:
    child = SMARTDS_ROOT / Path(entry["original_path"])
    if not has_required_dss_files(child):
        missing_registry_paths.append(str(child))
        continue

    feeder_name = entry["feeder_name"]
    circ_num = int(entry["circuit_id"])
    if circ_num in SKIP_CIRCUITS:
        skipped.append((feeder_name, circ_num))
        continue

    feeders.append(child)

print(f'🔎 Found {len(feeders)} feeders under {SMARTDS_ROOT}')
if skipped:
    print(f'⏭️  Skipped {len(skipped)} feeders by SKIP_CIRCUITS:')
    for nm, n in skipped:
        print(f'   - {nm}  → circuit_{n}')

if missing_registry_paths:
    print(f"Registry entries missing valid DSS files: {len(missing_registry_paths)}")
    for p in missing_registry_paths:
        print(f"   - {p}")

if MAX_FEEDERS is not None:
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

    # parse Loads for bases and daily mapping
    unique_bases  = set()
    base_to_daily = {}
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
        missing_keys = [k for k in MIX_KEYS_REQUIRED if k not in mix_cfg]
        if missing_keys:
            print(f"[FAIL] mix {mix_name} in {MIXES_FILE} has no {', '.join(missing_keys)}.")
            sys.exit(1)
        shares        = mix_cfg['shares']
        heating_seed  = int(mix_cfg.get('heating_seed', 123))
        ev_perc       = float(mix_cfg.get('ev_perc', 0.0))
        ev_lvl2       = float(mix_cfg['ev_lvl2_perc'])
        ev_seed       = int(mix_cfg.get('ev_seed', heating_seed))
        storage_perc  = {'residential': float(mix_cfg['storage_res_perc']),
                         'commercial':  float(mix_cfg['storage_com_perc'])}
        storage_seed  = int(mix_cfg.get('storage_seed', heating_seed))
        pv_perc       = {'residential': float(mix_cfg['pv_res_perc']),
                         'commercial':  float(mix_cfg['pv_com_perc'])}
        pv_seed       = int(mix_cfg.get('pv_seed', heating_seed))

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

        circ_tag = feeder_to_circuit.get(feeder_name)
        circ_num = circuit_num_from_tag(circ_tag, circuit_counter)

        # Use the mapped circuit number in the folder name
        dst_folder_name = f"{substation_name}_circuit_{circ_num}_{mix_name}"

        dst_folder      = Path(resolve_work_path("7_circuit_instantiation", dst_folder_name))
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
            print(f"[FAIL] {EV_DATA_SRC} not found. The EV generator in "
                  f"{RUNNER_BASENAME} needs data_ev/ in every circuit folder.")
            sys.exit(1)

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
        hp_baseline_root, hp_dm_root, hp_un_root = HP_BASELINE_ROOT, HP_DM_ROOT, HP_UN_ROOT
        if PEAK_DAY_RULE == "per_circuit" and not is_baseline_only(shares):
            mix_phase7 = Path(resolve_work_path("mix_days", mix_name, "7_circuit_instantiation"))
            hp_baseline_root = mix_phase7 / (STATE + '_4_profhp')
            hp_dm_root       = mix_phase7 / (STATE + '_6_profhp_dm')
            hp_un_root       = mix_phase7 / (STATE + '_7_profhp_un')
            print(f"  - peak_day_rule per_circuit: profiles from {mix_phase7}")
            for root in (hp_baseline_root, hp_dm_root, hp_un_root):
                if not (root / "daily_csvs" / (bucket_name or "")).is_dir():
                    print(f"[FAIL] {root / 'daily_csvs' / (bucket_name or '')} not found. "
                          f"Run phase mix_days with peak_day_rule: per_circuit first.")
                    sys.exit(1)
        if bucket_name:
            print(f"  • Using mapped bucket: {bucket_name}")
            idx_baseline = index_csvs(hp_baseline_root, include_only={bucket_name})
            idx_dm       = index_csvs(hp_dm_root,       include_only={bucket_name})
            idx_un       = index_csvs(hp_un_root,       include_only={bucket_name})
        else:
            print("  • No map entry; indexing all daily_csvs (may risk collisions).")
            idx_baseline = index_csvs(hp_baseline_root)
            idx_dm       = index_csvs(hp_dm_root)
            idx_un       = index_csvs(hp_un_root)

        # coverage diagnostics
        cov_b = sum(1 for fn in required_csvs if fn in idx_baseline)
        cov_d = sum(1 for fn in required_csvs if fn in idx_dm)
        cov_u = sum(1 for fn in required_csvs if fn in idx_un)
        print(f"  • Coverage → baseline {cov_b}/{len(required_csvs)}, dm {cov_d}/{len(required_csvs)}, un {cov_u}/{len(required_csvs)}")

        # 1) to 5) Heating split (heating_split.py): normalized shares, exact counts
        # by largest remainder, deterministic shuffle per feeder, loadshape labels
        heat = split_heating(unique_bases, base_to_daily, shares, heating_seed,
                              substation_name, feeder_name, unit=HEATING_LABEL_UNIT)
        p_b, p_dm, p_un = heat['p_b'], heat['p_dm'], heat['p_un']
        n_b, n_dm, n_un, N = heat['n_b'], heat['n_dm'], heat['n_un'], heat['N']
        mix_seed_offset = heat['mix_seed_offset']
        bases, labels = heat['bases'], heat['labels']
        daily_to_scen = heat['daily_to_scen']

        # (Optional) quick sanity print
        print(f"Assigned counts: baseline={n_b}, dm={n_dm}, un={n_un} out of N={N}")

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

        # rewrite LoadShapes.dss and copy CSVs; a loadshape without CSVs stops the run
        profiles_dest_dir = PROFILES_USE_BENCH_DIR / dst_folder_name
        profiles_dest_dir.mkdir(parents=True, exist_ok=True)

        tracking = {"missing_files": {}, "missing_files_track": {}, "all_files_track": {},
                    "bucket_choices": {"baseline": bucket_name or "(all)", "dm": bucket_name or "(all)", "un": bucket_name or "(all)"}}

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
                        # every load runs on a building profile: no CSV is a stop
                        print(f"[FAIL] no building profile (kW or kvar CSV) for loadshape {base} "
                              f"in circuit {dst_folder_name}.")
                        sys.exit(1)
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

        # Normalize Loads.dss: each line's kW and kvar are its share of the customer's
        # SMART-DS kW and kvar (heating_split.line_shares), so a customer draws its building once
        with loads_path.open('r', encoding='utf-8') as f:
            orig = f.readlines()
        shares_kw, n_kvar_fallback = line_shares(orig)
        n_lines = {}
        for full in shares_kw:
            b = re.sub(r"_[0-9]+$", "", full)
            n_lines[b] = n_lines.get(b, 0) + 1
        by_count = {}
        for k in n_lines.values():
            by_count[k] = by_count.get(k, 0) + 1
        print(f"  • Load lines per customer ({dst_folder_name}): "
              + ", ".join(f"{k} line(s)={by_count[k]}" for k in sorted(by_count))
              + f"; kvar fallbacks={n_kvar_fallback}")
        num = r"\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
        upd = []
        for line in orig:
            if line.lower().startswith('new load.'):
                if 'yearly=' in line:
                    line = re.sub(r'yearly=', 'daily=', line, flags=re.IGNORECASE)
                m_name = re.search(r"New\s+Load\.(\S+)", line, flags=re.IGNORECASE)
                kw_share, kvar_share = shares_kw[m_name.group(1)]
                if 'kW='   in line: line = re.sub(r"kW=" + num,   f"kW={format(kw_share, '.10g')}", line)
                if 'kvar=' in line: line = re.sub(r"kvar=" + num, f"kvar={format(kvar_share, '.10g')}", line)
            upd.append(line)
        with loads_path.open('w', encoding='utf-8') as f:
            f.writelines(upd)

        # =================== EV / PV / Storage targets ===================
        def clamp01(x): return max(0.0, min(1.0, float(x)))
        ev_perc      = clamp01(ev_perc)
        storage_perc = {seg: clamp01(v) for seg, v in storage_perc.items()}
        pv_perc      = {seg: clamp01(v) for seg, v in pv_perc.items()}

        # Residential and commercial loads (heating_split.load_segment); EV hosts are homes
        segment = {b: load_segment(b, base_to_daily) for b in sorted(unique_bases)}
        residential_bases = [b for b in sorted(unique_bases) if segment[b] == 'residential']
        n_com_bases = sum(1 for v in segment.values() if v == 'commercial')
        print(f"  • Segments ({dst_folder_name}): residential={len(residential_bases)}, "
              f"commercial={n_com_bases}, unclassified={len(segment) - len(residential_bases) - n_com_bases}")

        eligible_ev  = len(residential_bases)

        # raw counts
        n_ev  = int(round(ev_perc      * eligible_ev))

        # min-one rules (only if perc>0 and eligibles exist)
        if ev_perc > 0 and eligible_ev  > 0:    n_ev  = max(1, min(n_ev,  eligible_ev))

        # If we must have both EV types and n_ev==1, bump to 2 when possible
        if n_ev == 1 and ev_perc > 0 and eligible_ev >= 2:
            print("  • Bumping EV count from 1 → 2 to realize both EV types.")
            n_ev = 2

        # deterministic picks
        def pick(seed_val, items, k):
            import random as _r
            if k <= 0 or len(items) == 0: return []
            rng = _r.Random(int(seed_val) + _stable_seed_offset(f"{substation_name}|{feeder_name}"))
            items_copy = list(items)
            rng.shuffle(items_copy)
            return items_copy[:min(k, len(items_copy))]

        ev_hosts_all = pick(ev_seed, residential_bases, n_ev)

        # split EV hosts into uncontrolled vs controlled (disjoint)
        n_ev_ctl = int(round(n_ev * split_ctl))
        n_ev_un  = n_ev - n_ev_ctl
        if n_ev >= 2:
            # ensure non-zero both sides if we asked for EVs
            if n_ev_ctl == 0: n_ev_ctl, n_ev_un = 1, n_ev - 1
            if n_ev_un  == 0: n_ev_un,  n_ev_ctl = 1, n_ev - 1
        ev_loads_un  = ev_hosts_all[:n_ev_un]
        ev_loads_ctl = ev_hosts_all[n_ev_un:]

        # PV and storage hosts per segment (der_sizing.pick_hosts): PV drawn with pv_seed
        # among the segment's bases, storage with storage_seed by storage_hosts; a
        # switched-off segment gets none. Targets are base names.
        pick_offset = _stable_seed_offset(f"{substation_name}|{feeder_name}")
        pv_seg, sto_seg = {}, {}
        for seg in SEGMENTS:
            seg_bases = [b for b in sorted(unique_bases) if segment[b] == seg]
            n_pv_seg  = segment_count(pv_perc[seg], len(seg_bases), PV_ON[seg])
            n_sto_seg = segment_count(storage_perc[seg], len(seg_bases), STO_ON[seg])
            pv_hosts, sto_hosts = pick_hosts(seg_bases, n_pv_seg, n_sto_seg, pv_seed, storage_seed,
                                             pick_offset, STORAGE_HOSTS)
            pv_seg[seg] = {"perc": pv_perc[seg], "enabled": PV_ON[seg], "n_bases": len(seg_bases),
                           "hosts": pv_hosts}
            sto_seg[seg] = {"perc": storage_perc[seg], "enabled": STO_ON[seg], "n_bases": len(seg_bases),
                            "hosts": sto_hosts}
        storage_targets = [b for seg in SEGMENTS for b in sto_seg[seg]["hosts"]]
        pv_targets      = [b for seg in SEGMENTS for b in pv_seg[seg]["hosts"]]
        assignments = {
            # seed_offset/effective_seed: sha256-derived replacement for the old
            # hash()-based offset (Task 0 determinism fix). Recorded so a referee
            # can verify which RNG state actually produced this file.
            "heating": {"seed": heating_seed, "seed_offset": mix_seed_offset,
                        "effective_seed": int(heating_seed) + mix_seed_offset},
            "ev": {"perc": ev_perc, "lvl2_perc": ev_lvl2, "seed": ev_seed,
                   "seed_offset": mix_seed_offset, "effective_seed": ev_seed + mix_seed_offset},
            "ev_split": {"controlled": split_ctl, "uncontrolled": split_un},
            "storage": {"seed": storage_seed, "seed_offset": mix_seed_offset,
                        "effective_seed": storage_seed + mix_seed_offset, "storage_hosts": STORAGE_HOSTS,
                        **sto_seg},
            "pv": {"seed": pv_seed, "seed_offset": mix_seed_offset,
                   "effective_seed": pv_seed + mix_seed_offset, **pv_seg},
            "ev_loads_uncontrolled": ev_loads_un,
            "ev_loads_controlled":   ev_loads_ctl,
            "ev_loads": ev_hosts_all,   # union (for backwards compatibility)
            "storage_targets": storage_targets,
            "pv_targets":      pv_targets,
            "season": SEASON
        }
        (dst_folder / 'scenario_assignments.json').write_text(json.dumps(assignments, indent=2), encoding='utf-8')

        # tracking['missing_files']: loadshapes without a kW/kVAr CSV. A missing CSV stops
        # the run above, so the report written here is always empty.
        (dst_folder / 'missing_files_report.json').write_text(
            json.dumps(tracking['missing_files'], indent=2), encoding='utf-8')

        print(f"  • Assigned (mix={mix_name}) "
              f"EV_unctl={len(ev_loads_un)} + EV_ctl={len(ev_loads_ctl)} (total {len(ev_hosts_all)} @ {ev_perc:.2%}), "
              f"Storage res={len(sto_seg['residential']['hosts'])} com={len(sto_seg['commercial']['hosts'])}, "
              f"PV res={len(pv_seg['residential']['hosts'])} com={len(pv_seg['commercial']['hosts'])} "
              f"(storage_hosts {STORAGE_HOSTS})")

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

        # Ensure circuit_name
        if "circuit_name = " in txt:
            txt = re.sub(r"circuit_name\s*=\s*['\"].*?['\"]", f"circuit_name = '{dst_folder_name}'", txt)

        # Patch deployer_modules path so runner finds shared modules from repo
        deployer_root = str((REPO_ROOT / "7_circuit_instantiation").resolve())
        txt = re.sub(
            r"ROOT\s*=\s*os\.path\.abspath\(os\.path\.join\(CURRENT_DIR,\s*['\"]\.\.['\"]\)\)",
            lambda m: f'ROOT = r"{deployer_root}"',
            txt
        )

        runner_path.write_text(txt, encoding='utf-8')
        print("  • Patched runner (circuit_name + deployer_modules path)")

    circuit_counter += 1

# ==== WRITE GLOBAL SUMMARY / FULL MAPS ====
try:
    # 3a) Summary CSV
    sum_path = Path(resolve_work_path("7_circuit_instantiation", "heating_assignment__SUMMARY.csv"))
    sum_fields = [
        "substation","feeder_name","circuit_folder","mix","season",
        "share_baseline","share_dm","share_un",
        "n_daily_baseline","n_daily_dm","n_daily_un","N_daily_total",
        "n_base_baseline","n_base_dm","n_base_un","N_base_total",
    ]
    with open(sum_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=sum_fields)
        w.writeheader()
        for row in ASSIGN_SUMMARY_ROWS:
            w.writerow(row)
    print(f"[audit] Wrote {len(ASSIGN_SUMMARY_ROWS)} rows → {sum_path.name}")

    # 3b) Full mapping CSV (optional, can be large)
    if COLLECT_ASSIGN_FULL:
        full_path = Path(resolve_work_path("7_circuit_instantiation", "heating_assignment__FULL.csv"))
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
        json_path = Path(resolve_work_path("7_circuit_instantiation", "heating_assignment__FULL.json"))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(compact, f, ensure_ascii=False, indent=2)
        print(f"[audit] Wrote JSON → {json_path.name}")

except Exception as e:
    print(f"[audit] Failed to write assignment audit files: {e}")

print("\n🎉 All circuits prepared (and run if enabled)!")
END_PROCESS = time.time()
print(f"⏱️  Total time: {END_PROCESS - START_PROCESS:.2f} s")
print(str(END_PROCESS - START_PROCESS) + ' s /', str((END_PROCESS - START_PROCESS)/60) + ' min.')
