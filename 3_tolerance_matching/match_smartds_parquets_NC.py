# -*- coding: utf-8 -*-
"""
Optimized tolerance matching for the SMART-DS x EULP coupling pipeline.

Drop-in replacement for match_smartds_parquets_NC.py. Produces matches identical
to the original triple-nested-loop version, but vectorized.

Two methods are provided:
  - "exact": keeps the original comparison  abs(B - ref) <= (T/100)*ref  bit-for-bit,
             vectorized over all buildings; the tolerance loop is preserved.
  - "fast" : single pass. For each building it computes the minimum tolerance it would
             need to match every constraint, then picks the smallest tolerance bucket
             at which anything matches. No tolerance loop at all.

Set MATCH_METHOD to choose which result is WRITTEN. CROSS_CHECK runs both and asserts
they agree (sorted matched ids + tolerance, per source file) before writing.

The two methods are algebraically identical for non-negative reference peaks; the only
possible divergence is floating-point rounding at an exact tolerance-bucket boundary,
which CROSS_CHECK will catch. The "exact" method is the safe default.
"""

import os
import sys
import time
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- knobs
MATCH_METHOD = "exact"   # "exact" (bit-identical, safe) or "fast" (single-pass)
CROSS_CHECK = True       # run both methods and assert agreement before writing
# ---------------------------------------------------------------------------------

COM_TOLERANCES = list(range(5, 55, 5))    # 5..50  (original commercial range)
RES_TOLERANCES = list(range(5, 100, 5))   # 5..95  (original residential range)

WINTER_MONTHS = [12, 1, 2]
SUMMER_MONTHS = [6, 7, 8]

MONTH_TO_PEAK_COL_COM = {
    1: "out.qoi.maximum_daily_peak_jan..kw",
    2: "out.qoi.maximum_daily_peak_feb..kw",
    3: "out.qoi.maximum_daily_peak_mar..kw",
    4: "out.qoi.maximum_daily_peak_apr..kw",
    5: "out.qoi.maximum_daily_peak_may..kw",
    6: "out.qoi.maximum_daily_peak_jun..kw",
    7: "out.qoi.maximum_daily_peak_jul..kw",
    8: "out.qoi.maximum_daily_peak_aug..kw",
    9: "out.qoi.maximum_daily_peak_sep..kw",
    10: "out.qoi.maximum_daily_peak_oct..kw",
    11: "out.qoi.maximum_daily_peak_nov..kw",
    12: "out.qoi.maximum_daily_peak_dec..kw",
}


# =============================================================================
# Core matcher
# =============================================================================
def match_one(ref_vals, bldg_cols, bldg_ids, tolerances, method):
    """Match one source file against a population of buildings.

    A building matches at tolerance T iff for every constraint i:
        abs(bldg_cols[:, i] - ref_vals[i]) <= (T/100) * ref_vals[i]

    Returns (matched_ids_as_python_int_list, best_tolerance_or_None).
    Matched ids preserve the row order of bldg_ids (== original iterrows order).

    ref_vals : (k,)   already NaN-filtered reference peaks (only active constraints)
    bldg_cols: (n, k)  building values aligned to each constraint
    bldg_ids : (n,)
    """
    k = ref_vals.shape[0]

    if k == 0:
        # No active constraints -> original code leaves all_months_match=True for every
        # building, so everything matches at the smallest tolerance.
        return bldg_ids.tolist(), int(tolerances[0])

    if method == "exact":
        diff = np.abs(bldg_cols - ref_vals[np.newaxis, :])      # (n, k); NaN where bldg NaN
        for T in tolerances:
            band = (T / 100.0) * ref_vals                       # (k,)
            ok = (diff <= band[np.newaxis, :]).all(axis=1)      # (n,)
            if ok.any():
                return bldg_ids[ok].tolist(), int(T)
        return [], None

    if method == "fast":
        with np.errstate(divide="ignore", invalid="ignore"):
            rel = np.abs(bldg_cols - ref_vals[np.newaxis, :]) / ref_vals[np.newaxis, :] * 100.0
        # ref == 0 -> band is 0 -> requires bldg == 0 exactly (else never matches)
        for c in np.where(ref_vals == 0)[0]:
            rel[:, c] = np.where(bldg_cols[:, c] == 0, 0.0, np.inf)
        # building NaN on a finite ref -> rel is NaN -> never matches
        rel = np.where(np.isnan(rel), np.inf, rel)
        req_tol = rel.max(axis=1)                               # min tolerance each bldg needs
        tarr = np.asarray(tolerances, dtype=float)
        ge = tarr[tarr >= req_tol.min()]
        if ge.size == 0:
            return [], None
        best_T = int(ge[0])
        ok = req_tol <= best_T
        return bldg_ids[ok].tolist(), best_T

    raise ValueError(f"unknown method: {method!r}")


# =============================================================================
# Build the per-source-file constraints and run the matcher across all rows
# =============================================================================
def _pivot_refs(df_matches, kind):
    """Pivot review_parquet_matches into (source_files, ref_matrix[n_src, 12])."""
    sub = df_matches[df_matches["Type"] == kind]
    pivot = sub.pivot(index="Source_File", columns="Month", values="Monthly_Peak")
    pivot = pivot.reindex(columns=range(1, 13))  # ensure all 12 months exist (NaN if absent)
    return pivot.index.to_numpy(), pivot.to_numpy(dtype=float)


def match_commercial(df_matches, df_com, method):
    src_files, ref_all = _pivot_refs(df_matches, "com")
    com_cols = [MONTH_TO_PEAK_COL_COM[m] for m in range(1, 13)]
    states = sorted(df_com["State"].unique().tolist())

    out = []
    for st in states:
        sub = df_com[df_com["State"] == st]
        B = sub[com_cols].to_numpy(dtype=float)        # (n, 12)
        ids = sub["bldg_id"].to_numpy()
        for i, sf in enumerate(src_files):
            r = ref_all[i]
            valid = ~np.isnan(r)
            matched, best_T = match_one(r[valid], B[:, valid], ids, COM_TOLERANCES, method)
            out.append({"Source_File": sf, "State": st,
                        "Matched_Buildings": matched, "Tolerance": best_T})
    return out


def match_residential(df_matches, df_res, method):
    src_files, ref_all = _pivot_refs(df_matches, "res")
    states = sorted(df_res["State"].unique().tolist())

    out = []
    for st in states:
        sub = df_res[df_res["State"] == st]
        Bw = sub["out.electricity.winter.peak.kw"].to_numpy(dtype=float)
        Bs = sub["out.electricity.summer.peak.kw"].to_numpy(dtype=float)
        ids = sub["bldg_id"].to_numpy()
        for i, sf in enumerate(src_files):
            r = ref_all[i]
            winter_refs = [r[m - 1] for m in WINTER_MONTHS if not np.isnan(r[m - 1])]
            summer_refs = [r[m - 1] for m in SUMMER_MONTHS if not np.isnan(r[m - 1])]
            ref_vals = np.asarray(winter_refs + summer_refs, dtype=float)
            cols = [Bw] * len(winter_refs) + [Bs] * len(summer_refs)
            bldg_cols = np.column_stack(cols) if cols else np.empty((ids.shape[0], 0))
            matched, best_T = match_one(ref_vals, bldg_cols, ids, RES_TOLERANCES, method)
            out.append({"Source_File": sf, "State": st,
                        "Matched_Buildings": matched, "Tolerance": best_T})
    return out


# =============================================================================
# Cross-check
# =============================================================================
def _assert_agree(rows_a, rows_b, label):
    assert len(rows_a) == len(rows_b), f"{label}: row count differs"
    for ra, rb in zip(rows_a, rows_b):
        assert ra["Source_File"] == rb["Source_File"] and ra["State"] == rb["State"], \
            f"{label}: row alignment differs at {ra['Source_File']}/{ra['State']}"
        assert ra["Tolerance"] == rb["Tolerance"], \
            f"{label}: tolerance differs at {ra['Source_File']}/{ra['State']}"
        assert sorted(ra["Matched_Buildings"]) == sorted(rb["Matched_Buildings"]), \
            f"{label}: matched set differs at {ra['Source_File']}/{ra['State']}"
    return len(rows_a)


# =============================================================================
# Main
# =============================================================================
def main():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from pipeline_utils import load_config, resolve_work_path

    start = time.time()
    cfg = load_config()
    state = cfg["state"]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    phase1_out = resolve_work_path("1_data_provenance", "outputs", "pipeline_state")

    def metadata_csv(filename):
        for c in (os.path.join(script_dir, filename),
                  os.path.join(phase1_out, filename),
                  os.path.join(repo_root, filename)):
            if os.path.exists(c):
                return c
        return os.path.join(phase1_out, filename)

    df_matches = pd.read_csv(resolve_work_path("3_tolerance_matching", "review_parquet_matches.csv"))
    df_com = pd.read_csv(metadata_csv("commercial_data_SELECT_STATES.csv"))
    df_res = pd.read_csv(metadata_csv("residential_data_SELECT_STATES.csv"))
    df_com = df_com.loc[df_com["State"] == state]
    df_res = df_res.loc[df_res["State"] == state]

    if CROSS_CHECK:
        t = time.time()
        com_exact = match_commercial(df_matches, df_com, "exact")
        res_exact = match_residential(df_matches, df_res, "exact")
        print(f"[exact] matching: {time.time() - t:.3f}s")

        t = time.time()
        com_fast = match_commercial(df_matches, df_com, "fast")
        res_fast = match_residential(df_matches, df_res, "fast")
        print(f"[fast ] matching: {time.time() - t:.3f}s")

        n = _assert_agree(com_exact, com_fast, "commercial")
        n += _assert_agree(res_exact, res_fast, "residential")
        print(f"cross-check: PASS ({n} source-file rows identical between exact and fast)")
        com_rows = com_exact if MATCH_METHOD == "exact" else com_fast
        res_rows = res_exact if MATCH_METHOD == "exact" else res_fast
    else:
        com_rows = match_commercial(df_matches, df_com, MATCH_METHOD)
        res_rows = match_residential(df_matches, df_res, MATCH_METHOD)

    df_com_matches_out = pd.DataFrame(com_rows)
    df_com_matches_out.to_csv(
        resolve_work_path("3_tolerance_matching", f"df_com_matches_out_{state}.csv"),
        index=False,
    )
    df_res_matches_out = pd.DataFrame(res_rows)
    df_res_matches_out.to_csv(
        resolve_work_path("3_tolerance_matching", f"df_res_matches_out_{state}.csv"),
        index=False,
    )

    # ---- summaries (same as original) ----
    total_com = df_com["bldg_id"].nunique()
    matched_com = len(set().union(*df_com_matches_out["Matched_Buildings"])) if len(df_com_matches_out) else 0
    print(f"Number of unique building IDs in df_com: {total_com}")
    print(f"Number of unique matched building IDs: {matched_com}")
    if total_com:
        print(f"That's {100.0 * matched_com / total_com:.2f}% of the commercial dataset.")

    total_res = df_res["bldg_id"].nunique()
    matched_res = len(set().union(*df_res_matches_out["Matched_Buildings"])) if len(df_res_matches_out) else 0
    print("=== Residential Matching Summary ===")
    print(f"Number of unique building IDs in df_res: {total_res}")
    print(f"Number of unique matched building IDs: {matched_res}")
    if total_res:
        print(f"That's {100.0 * matched_res / total_res:.2f}% of the residential dataset.")
    print("====================================")
    print(f"Time taken: {time.time() - start} seconds")


if __name__ == "__main__":
    main()
