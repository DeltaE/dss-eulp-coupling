# -*- coding: utf-8 -*-
"""
select_rep_family_v2.py  —  Dynamic, data-driven representative-building selection.

Refactor of select_rep_family_NC.py. Same inputs / outputs / invariants, but the two
hardcoded structures (per-type integer quotas and the fixed priority order) are now
DERIVED FROM THE MATCHED DATA, with a small, predictable rule:

  Every building type found in the data gets parquets PROPORTIONAL to how many of that
  type were matched -- but at least `min_per_type`, and never more than it can physically
  reach. Leftover from types that can't fill flows to the ones that can, in the same
  proportions (redistribution). Types are filled RAREST-FIRST so scarce types claim their
  shared parquets before abundant ones crowd them out. Any parquet still unassigned at the
  end is swept up by a mop-up pass (one building = one parquet always holds).

Nothing is precomputed per type. Absent types simply don't appear -> no KeyErrors.
Reproducible: a single seeded RNG drives every choice; all set iteration is sorted.

Config (optional `quota:` block in pipeline_config.yaml; sensible defaults if absent):
  quota:
    min_per_type: 1                 # floor so a present type never rounds to zero
    redistribution: proportional    # proportional | none
    commercial_order: auto          # auto (rarest-first) | [explicit, list, of, types]
    residential_order: auto         # auto (rarest-first) | [explicit, list, of, types]
"""

import os
import ast
import sys
import time
import math
import random

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_work_path

START_PROCESS = time.time()

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
DOWNLOAD_DATE = cfg.get('eulp_download_date', '20250330')
FAMILY_STR = STATE
STATE_STR = STATE
RANDOM_SEED = int(cfg.get('random_seed', 42))

# One RNG drives every random choice -> reproducible regardless of PYTHONHASHSEED.
RNG = random.Random(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

current_dir = os.path.dirname(os.path.abspath(__file__))
PHASE4_OUTPUT_DIR = resolve_work_path("4_quota_assignment")
os.makedirs(PHASE4_OUTPUT_DIR, exist_ok=True)


def phase4_csv(filename):
    return resolve_work_path("4_quota_assignment", filename)

# ------------------------------------------------------------------
# Quota settings (with defaults; overridable via cfg['quota'])
# ------------------------------------------------------------------
_q = cfg.get('quota', {}) or {}
MIN_PER_TYPE = int(_q.get('min_per_type', 1))
REDISTRIBUTION = str(_q.get('redistribution', 'proportional')).lower()
COMMERCIAL_ORDER = _q.get('commercial_order', 'auto')
RESIDENTIAL_ORDER = _q.get('residential_order', 'auto')

residential_scenario = "mid"   # which income tier fills first

# Priority lists of descriptor CSVs for residential, depending on scenario
_tiers = {
    "high": ["high", "mid", "low", "not_available"],
    "mid":  ["mid", "high", "low", "not_available"],
    "low":  ["low", "mid", "high", "not_available"],
}
residential_priority = [
    f"residential_data_SELECT_STATES_FILTERED_{t}_{FAMILY_STR}.csv"
    for t in _tiers.get(residential_scenario, _tiers["low"])
]
commercial_descriptor_file = f"commercial_data_SELECT_STATES_FILTERED_{FAMILY_STR}.csv"


# ==================================================================
# DYNAMIC ENGINE  (shared by commercial + residential)
# ==================================================================
def build_type_records(descriptor_df, type_col, bldg_to_parquets):
    """type -> list of (bldg_id, row, parquet_set). Absent types simply never appear."""
    out = {}
    for bldg_type, group in descriptor_df.groupby(type_col):
        recs = []
        for _, row in group.iterrows():
            b_id = row["bldg_id"]
            recs.append((b_id, row, bldg_to_parquets.get(b_id, set())))
        out[bldg_type] = recs
    return out


def type_stats(type_records):
    """Per type: (#unique buildings, set of reachable parquets, cap).
    cap = min(#buildings, #reachable parquets): you can't claim more parquets than you
    have buildings (one building = one parquet), nor more than your buildings can reach."""
    stats = {}
    for t, recs in type_records.items():
        ids = set(r[0] for r in recs)
        reach = set()
        for (_, _, pset) in recs:
            reach |= pset
        stats[t] = {"count": len(ids), "reach": reach, "cap": min(len(ids), len(reach))}
    return stats


def compute_quota(stats, target, min_per_type=1, redistribution="proportional"):
    """Data-driven proportional quota with a floor, capped at availability, with the
    deficit from capped types redistributed (proportionally) to types that have room.
    Returns an integer quota per type summing to min(target, total capacity)."""
    types = list(stats.keys())
    if not types:
        return {}
    total_count = sum(stats[t]["count"] for t in types) or 1
    cap = {t: stats[t]["cap"] for t in types}
    weight = {t: stats[t]["count"] / total_count for t in types}
    feasible = min(target, sum(cap.values()))

    # provisional proportional quota with floor
    q = {t: max(min_per_type, weight[t] * target) for t in types}

    if redistribution == "none":
        q = {t: min(q[t], cap[t]) for t in types}
    else:
        # iteratively clamp to cap and push the freed amount onto types with headroom
        for _ in range(100):
            over = {t: q[t] - cap[t] for t in types if q[t] > cap[t] + 1e-9}
            if not over:
                break
            deficit = sum(over.values())
            for t in over:
                q[t] = cap[t]
            room = [t for t in types if q[t] < cap[t] - 1e-9]
            if not room:
                break
            wsum = sum(weight[t] for t in room) or 1
            for t in room:
                q[t] = min(cap[t], q[t] + deficit * (weight[t] / wsum))

    # largest-remainder rounding to hit `feasible`, never exceeding caps
    floor_q = {t: min(int(math.floor(q[t])), cap[t]) for t in types}
    need = feasible - sum(floor_q.values())
    # distribute remaining units to the largest fractional parts (then by name, deterministic)
    order = sorted(types, key=lambda t: (-(q[t] - math.floor(q[t])), t))
    i = 0
    while need > 0 and any(floor_q[t] < cap[t] for t in types):
        t = order[i % len(order)]
        if floor_q[t] < cap[t]:
            floor_q[t] += 1
            need -= 1
        i += 1
    return floor_q


def resolve_order(stats, mode):
    """Rarest-first (auto) or an explicit list. Any present type missing from an explicit
    list is appended at the end (rarest-first) so nothing is ever dropped or KeyErrors."""
    present = list(stats.keys())
    rarest_first = sorted(present, key=lambda t: (stats[t]["count"], t))
    if isinstance(mode, (list, tuple)):
        ordered = [t for t in mode if t in stats]
        ordered += [t for t in rarest_first if t not in ordered]
        return ordered
    return rarest_first


def assign_pass(order, type_records, quota, assigned_parquets, assigned_count,
                selected_rows, rng, used_bldg_ids):
    """Greedy: for each type in `order`, claim its still-unassigned reachable parquets up
    to its quota. Deterministic (sorted parquets + sorted candidates, seeded choice).
    Prefers buildings not yet used (uniqueness-first); reuses one only when every
    candidate for a parquet is already taken (so coverage is never sacrificed).
    Mutates assigned_parquets / assigned_count / selected_rows / used_bldg_ids in place."""
    for bldg_type in order:
        recs = type_records.get(bldg_type, [])
        q = quota.get(bldg_type, 0)
        if not recs or q <= 0:
            continue
        parquets = set()
        for (_, _, pset) in recs:
            parquets |= pset
        for parquet_file in sorted(parquets):           # sorted -> reproducible
            if assigned_count[bldg_type] >= q:
                break
            if parquet_file in assigned_parquets:
                continue
            candidates = sorted(
                [(b_id, row) for (b_id, row, pset) in recs if parquet_file in pset],
                key=lambda c: c[0],
            )
            if not candidates:
                continue
            # uniqueness-first: choose among fresh buildings if any remain,
            # otherwise fall back to an already-used one (never leave a gap)
            fresh = [c for c in candidates if c[0] not in used_bldg_ids]
            pick_from = fresh if fresh else candidates
            b_id, row = rng.choice(pick_from)
            row_copy = row.copy()
            row_copy["Chosen_Parquet"] = parquet_file
            selected_rows.append(row_copy)
            assigned_parquets.add(parquet_file)
            assigned_count[bldg_type] += 1
            used_bldg_ids.add(b_id)


def mop_up(unassigned, exploded, type_col, selected_rows, rng,
           primary_lookup, used_bldg_ids, fallback_lookup=None):
    """Sweep any parquet still unassigned -> any reachable building. Occupied pool first,
    then (residential) the vacant pool. Prefers buildings not yet used; reuses only when
    forced. Guarantees full parquet coverage."""
    if not unassigned:
        return set()
    parquet_to_bldgs = (
        exploded[exploded["Unique_Source_Files"].isin(unassigned)]
        .groupby("Unique_Source_Files")["bldg_id"].apply(set).to_dict()
    )
    still = set()
    for parquet_file in sorted(unassigned):
        possible = parquet_to_bldgs.get(parquet_file, set())
        cand = primary_lookup[primary_lookup["bldg_id"].isin(possible)]
        pool = cand
        if cand.empty and fallback_lookup is not None:
            pool = fallback_lookup[fallback_lookup["bldg_id"].isin(possible)]
        if pool.empty:
            still.add(parquet_file)
            print(f"  [mop-up] no reachable building for {parquet_file}")
            continue
        ids = sorted(pool["bldg_id"].unique())
        fresh = [i for i in ids if i not in used_bldg_ids]
        chosen_id = rng.choice(fresh if fresh else ids)
        row = pool[pool["bldg_id"] == chosen_id].iloc[0].copy()
        row["Chosen_Parquet"] = parquet_file
        selected_rows.append(row)
        used_bldg_ids.add(chosen_id)
    return still


def report(final_df, type_col, quota, target, label):
    print(f"\n--- {label} result ---")
    if final_df.empty:
        print("  (empty)")
        return
    chosen = final_df.groupby(type_col)["Chosen_Parquet"].nunique()
    table = pd.DataFrame({"Chosen": chosen})
    table["Quota"] = table.index.map(lambda t: quota.get(t, 0))
    table = table.sort_values("Chosen", ascending=False)
    print(table.to_string())
    covered = final_df["Chosen_Parquet"].nunique()
    print(f"  TOTAL: {len(final_df)} rows | {covered}/{target} parquets covered"
          f"{'  [FULL]' if covered == target else '  [GAPS]'}")


# ==================================================================
# LOAD SOURCE MAPS
# ==================================================================
res_source_map = pd.read_csv(phase4_csv(f"residential_building_source_map_{FAMILY_STR}.csv"))
com_source_map = pd.read_csv(phase4_csv(f"commercial_building_source_map_{FAMILY_STR}.csv"))
res_source_map["Unique_Source_Files"] = res_source_map["Unique_Source_Files"].apply(ast.literal_eval)
com_source_map["Unique_Source_Files"] = com_source_map["Unique_Source_Files"].apply(ast.literal_eval)

res_exploded = res_source_map.explode("Unique_Source_Files").reset_index(drop=True)
com_exploded = com_source_map.explode("Unique_Source_Files").reset_index(drop=True)

unique_res_parquets = sorted(res_exploded["Unique_Source_Files"].unique())
unique_com_parquets = sorted(com_exploded["Unique_Source_Files"].unique())

res_bldg_ids_set = set(res_source_map["bldg_id"].unique())
com_bldg_ids_set = set(com_source_map["bldg_id"].unique())

bldg_to_parquets_res = res_exploded.groupby("bldg_id")["Unique_Source_Files"].apply(set).to_dict()
bldg_to_parquets_com = com_exploded.groupby("bldg_id")["Unique_Source_Files"].apply(set).to_dict()

print(f"Residential parquets: {len(unique_res_parquets)} | Commercial parquets: {len(unique_com_parquets)}")
print(f"Quota settings: min_per_type={MIN_PER_TYPE}, redistribution={REDISTRIBUTION}, "
      f"commercial_order={'auto' if COMMERCIAL_ORDER=='auto' else 'explicit'}, "
      f"residential_order={'auto' if RESIDENTIAL_ORDER=='auto' else 'explicit'}")


# ==================================================================
# COMMERCIAL
# ==================================================================
print("\n" + "=" * 60 + "\nCOMMERCIAL\n" + "=" * 60)
COM_TYPE = "in.comstock_building_type"

com_raw = pd.read_csv(phase4_csv(commercial_descriptor_file))
com_df = com_raw[com_raw["bldg_id"].isin(com_bldg_ids_set)]
com_df = com_df[com_df["State"] == STATE_STR]

com_type_records = build_type_records(com_df, COM_TYPE, bldg_to_parquets_com)
com_stats = type_stats(com_type_records)
com_target = len(unique_com_parquets)
com_quota = compute_quota(com_stats, com_target, MIN_PER_TYPE, REDISTRIBUTION)
com_order = resolve_order(com_stats, COMMERCIAL_ORDER)

print("Discovered types (rarest-first), quota:")
for t in com_order:
    print(f"   {t:<26} count={com_stats[t]['count']:<4} cap={com_stats[t]['cap']:<4} quota={com_quota[t]}")

com_assigned_parquets = set()
com_assigned_count = {t: 0 for t in com_type_records}
com_selected = []
com_used = set()
assign_pass(com_order, com_type_records, com_quota, com_assigned_parquets,
            com_assigned_count, com_selected, RNG, com_used)

# commercial mop-up (NEW: the original had none)
com_missing = set(unique_com_parquets) - com_assigned_parquets
com_still = mop_up(com_missing, com_exploded, COM_TYPE, com_selected, RNG, com_df, com_used)

final_commercial = pd.DataFrame(com_selected)
report(final_commercial, COM_TYPE, com_quota, com_target, "Commercial")


# ==================================================================
# RESIDENTIAL
# ==================================================================
print("\n" + "=" * 60 + "\nRESIDENTIAL\n" + "=" * 60)
RES_TYPE = "in.geometry_building_type_acs"

# Read all priority tiers; split occupied vs vacant; keep only mapped bldg_ids.
occ_frames, vac_frames = [], []
for csv_name in residential_priority:
    path = phase4_csv(csv_name)
    if not os.path.exists(path):
        print(f"Warning: {csv_name} not found. Skipping.")
        continue
    tdf = pd.read_csv(path)
    tdf = tdf[tdf["State"] == STATE_STR]
    occ = tdf[tdf["in.vacancy_status"] == "Occupied"]
    vac = tdf[tdf["in.vacancy_status"] != "Occupied"]
    occ_frames.append(occ[occ["bldg_id"].isin(res_bldg_ids_set)])
    vac_frames.append(vac[vac["bldg_id"].isin(res_bldg_ids_set)])

final_residential_raw = pd.concat(occ_frames, ignore_index=True) if occ_frames else pd.DataFrame()
final_residential_raw_vacant = pd.concat(vac_frames, ignore_index=True) if vac_frames else pd.DataFrame()

# Quota + order computed once, over the FULL occupied pool.
res_type_records_all = build_type_records(final_residential_raw, RES_TYPE, bldg_to_parquets_res)
res_stats = type_stats(res_type_records_all)
res_target = len(unique_res_parquets)
res_quota = compute_quota(res_stats, res_target, MIN_PER_TYPE, REDISTRIBUTION)
res_order = resolve_order(res_stats, RESIDENTIAL_ORDER)

print("Discovered house types (rarest-first), quota:")
for t in res_order:
    print(f"   {t:<26} count={res_stats[t]['count']:<5} cap={res_stats[t]['cap']:<4} quota={res_quota[t]}")

res_assigned_parquets = set()
res_assigned_count = {t: 0 for t in res_type_records_all}
res_selected = []
res_used = set()

# Scenario-priority OUTER loop: a parquet is filled by the highest-priority tier that can.
for csv_name in residential_priority:
    if len(res_assigned_parquets) >= res_target:
        break
    path = phase4_csv(csv_name)
    if not os.path.exists(path):
        continue
    tdf = pd.read_csv(path)
    tdf = tdf[(tdf["State"] == STATE_STR) & (tdf["in.vacancy_status"] == "Occupied")]
    tdf = tdf[tdf["bldg_id"].isin(res_bldg_ids_set)]
    if tdf.empty:
        continue
    scenario_records = build_type_records(tdf, RES_TYPE, bldg_to_parquets_res)
    assign_pass(res_order, scenario_records, res_quota, res_assigned_parquets,
                res_assigned_count, res_selected, RNG, res_used)
    print(f">>> after {os.path.basename(csv_name)}: "
          f"{len(res_assigned_parquets)}/{res_target} parquets assigned")

# residential mop-up: occupied pool first, then vacant fallback
res_missing = set(unique_res_parquets) - res_assigned_parquets
res_still = mop_up(res_missing, res_exploded, RES_TYPE, res_selected, RNG,
                   final_residential_raw, res_used, fallback_lookup=final_residential_raw_vacant)

final_residential = pd.DataFrame(res_selected)
report(final_residential, RES_TYPE, res_quota, res_target, "Residential")


# ==================================================================
# OUTPUT
# ==================================================================
COPY_FILE_BOOL = False  # parquet copying handled downstream; kept off as in original

final_commercial_csv = f"{FAMILY_STR}_final_commercial.csv"
final_residential_csv = f"{FAMILY_STR}_final_residential.csv"
final_commercial.to_csv(phase4_csv(final_commercial_csv), index=False)
final_residential.to_csv(phase4_csv(final_residential_csv), index=False)
print(f"\nSaved {final_commercial_csv}  ({len(final_commercial)} rows)")
print(f"Saved {final_residential_csv}  ({len(final_residential)} rows)")

print(f"\n{time.time() - START_PROCESS:.2f} seconds")
