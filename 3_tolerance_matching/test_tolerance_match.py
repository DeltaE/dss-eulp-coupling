# -*- coding: utf-8 -*-
"""
Correctness harness for the optimized matcher.

Strategy: re-implement the ORIGINAL nested-loop logic exactly (the oracle), generate
randomized + adversarial synthetic data, and assert the optimized 'exact' and 'fast'
methods reproduce the oracle's (matched set, tolerance) for every source file.

No real data needed -- this proves the *algorithm* is equivalent. The real-data CSV
diff on Machine 3 is then just the final seal.
"""

import importlib.util
import numpy as np
import pandas as pd

# import the optimized module by path (its data I/O is guarded under __main__)
spec = importlib.util.spec_from_file_location("opt", "/home/claude/match_smartds_parquets_NC.py")
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)

COM_TOL = opt.COM_TOLERANCES
RES_TOL = opt.RES_TOLERANCES
COM_COLS = [opt.MONTH_TO_PEAK_COL_COM[m] for m in range(1, 13)]


# ----------------------------------------------------------------------------
# ORACLE: faithful transcription of the original match_smartds_parquets_NC.py
# ----------------------------------------------------------------------------
def oracle_commercial(df_matches, df_com):
    df_mc = df_matches[df_matches["Type"] == "com"].copy()
    piv = df_mc.pivot(index="Source_File", columns="Month", values="Monthly_Peak").reset_index()
    piv.columns = ["Source_File" if c == "Source_File" else f"Peak_{c}" for c in piv.columns]

    states = sorted(set(df_com["State"].tolist()))
    expanded = pd.concat([piv.assign(State=st) for st in states], ignore_index=True)

    out = []
    for _, row in expanded.iterrows():
        sf, st = row["Source_File"], row["State"]
        dcom = df_com[df_com["State"] == st]
        final, best = [], None
        for tol in COM_TOL:
            matched = []
            for _, b in dcom.iterrows():
                ok = True
                for m in range(1, 13):
                    col = f"Peak_{m}"
                    if col not in row or pd.isna(row[col]):
                        continue
                    ref = row[col]
                    bp = b[opt.MONTH_TO_PEAK_COL_COM[m]]
                    if not (abs(bp - ref) <= (tol / 100) * ref):
                        ok = False
                        break
                if ok:
                    matched.append(b["bldg_id"])
            if matched:
                final, best = matched, tol
                break
        out.append({"Source_File": sf, "State": st, "Matched_Buildings": final, "Tolerance": best})
    return out


def oracle_residential(df_matches, df_res):
    df_mr = df_matches[df_matches["Type"] == "res"].copy()
    piv = df_mr.pivot(index="Source_File", columns="Month", values="Monthly_Peak").reset_index()
    piv.columns = ["Source_File" if c == "Source_File" else f"Peak_{c}" for c in piv.columns]

    states = sorted(set(df_res["State"].tolist()))
    expanded = pd.concat([piv.assign(State=st) for st in states], ignore_index=True)

    out = []
    for _, row in expanded.iterrows():
        sf, st = row["Source_File"], row["State"]
        dres = df_res[df_res["State"] == st]
        final, best = [], None
        for tol in RES_TOL:
            matched = []
            for _, b in dres.iterrows():
                mw = True
                for m in [12, 1, 2]:
                    col = f"Peak_{m}"
                    if col not in row or pd.isna(row[col]):
                        continue
                    ref = row[col]
                    bw = b["out.electricity.winter.peak.kw"]
                    if not (abs(bw - ref) <= (tol / 100) * ref):
                        mw = False
                        break
                ms = True
                for m in [6, 7, 8]:
                    col = f"Peak_{m}"
                    if col not in row or pd.isna(row[col]):
                        continue
                    ref = row[col]
                    bs = b["out.electricity.summer.peak.kw"]
                    if not (abs(bs - ref) <= (tol / 100) * ref):
                        ms = False
                        break
                if mw and ms:
                    matched.append(b["bldg_id"])
            if matched:
                final, best = matched, tol
                break
        out.append({"Source_File": sf, "State": st, "Matched_Buildings": final, "Tolerance": best})
    return out


# ----------------------------------------------------------------------------
# comparison
# ----------------------------------------------------------------------------
def rows_equal(a, b):
    if len(a) != len(b):
        return False, "row count"
    for ra, rb in zip(a, b):
        if (ra["Source_File"], ra["State"]) != (rb["Source_File"], rb["State"]):
            return False, f"order @ {ra['Source_File']}/{ra['State']}"
        if ra["Tolerance"] != rb["Tolerance"]:
            return False, f"tol @ {ra['Source_File']}/{ra['State']}: {ra['Tolerance']} vs {rb['Tolerance']}"
        # compare as sorted python ints (robust to numpy-int serialization differences)
        if sorted(int(x) for x in ra["Matched_Buildings"]) != sorted(int(x) for x in rb["Matched_Buildings"]):
            return False, f"set @ {ra['Source_File']}/{ra['State']}"
    return True, ""


# ----------------------------------------------------------------------------
# synthetic data generators
# ----------------------------------------------------------------------------
def make_random(rng, n_bldg, n_src, states):
    com_rows, res_rows = [], []
    bid = 0
    for st in states:
        for _ in range(n_bldg):
            peaks = rng.uniform(1, 200, size=12)
            if rng.random() < 0.05:
                peaks[rng.integers(0, 12)] = np.nan          # NaN building peak
            if rng.random() < 0.03:
                peaks[rng.integers(0, 12)] = 0.0             # zero building peak
            d = {"State": st, "bldg_id": bid}
            for m in range(1, 13):
                d[opt.MONTH_TO_PEAK_COL_COM[m]] = peaks[m - 1]
            com_rows.append(d)
            res_rows.append({"State": st, "bldg_id": bid,
                             "out.electricity.winter.peak.kw": rng.uniform(1, 200),
                             "out.electricity.summer.peak.kw": rng.uniform(1, 200)})
            bid += 1
    df_com = pd.DataFrame(com_rows)
    df_res = pd.DataFrame(res_rows)

    match_rows = []
    for kind, df_ref, anchor_cols in (("com", df_com, COM_COLS),
                                       ("res", df_res, None)):
        for s in range(n_src):
            sf = f"{kind}_src_{s}"
            # ~half the time anchor on a real building so a genuine match exists
            if rng.random() < 0.5:
                anchor = df_ref.iloc[rng.integers(0, len(df_ref))]
                if kind == "com":
                    base = {m: anchor[opt.MONTH_TO_PEAK_COL_COM[m]] for m in range(1, 13)}
                else:
                    base = {12: anchor["out.electricity.winter.peak.kw"],
                            1: anchor["out.electricity.winter.peak.kw"],
                            2: anchor["out.electricity.winter.peak.kw"],
                            6: anchor["out.electricity.summer.peak.kw"],
                            7: anchor["out.electricity.summer.peak.kw"],
                            8: anchor["out.electricity.summer.peak.kw"]}
            else:
                base = {m: rng.uniform(1, 200) for m in range(1, 13)}

            months = list(range(1, 13)) if kind == "com" else [12, 1, 2, 6, 7, 8]
            for m in months:
                if m not in base or np.isnan(base.get(m, np.nan)):
                    continue
                if rng.random() < 0.15:        # randomly drop a month (-> NaN ref)
                    continue
                val = base[m] * (1 + rng.uniform(-0.4, 0.4))   # perturb so tol varies
                match_rows.append({"Type": kind, "Source_File": sf, "Month": m, "Monthly_Peak": val})
    return df_com, df_res, pd.DataFrame(match_rows)


def make_edge_cases():
    """Hand-built adversarial cases: zero refs, exact boundaries, no-ref, no-match, NaN."""
    com = pd.DataFrame([
        {"State": "ZZ", "bldg_id": 0, **{opt.MONTH_TO_PEAK_COL_COM[m]: 100.0 for m in range(1, 13)}},
        {"State": "ZZ", "bldg_id": 1, **{opt.MONTH_TO_PEAK_COL_COM[m]: 0.0 for m in range(1, 13)}},
        {"State": "ZZ", "bldg_id": 2, **{opt.MONTH_TO_PEAK_COL_COM[m]: 110.0 for m in range(1, 13)}},  # exactly +10%
        {"State": "ZZ", "bldg_id": 3, **{opt.MONTH_TO_PEAK_COL_COM[m]: np.nan for m in range(1, 13)}},
        {"State": "ZZ", "bldg_id": 4, **{opt.MONTH_TO_PEAK_COL_COM[m]: 9999.0 for m in range(1, 13)}},  # never
    ])
    res = pd.DataFrame([
        {"State": "ZZ", "bldg_id": 0, "out.electricity.winter.peak.kw": 100.0, "out.electricity.summer.peak.kw": 100.0},
        {"State": "ZZ", "bldg_id": 1, "out.electricity.winter.peak.kw": 0.0, "out.electricity.summer.peak.kw": 0.0},
        {"State": "ZZ", "bldg_id": 2, "out.electricity.winter.peak.kw": 110.0, "out.electricity.summer.peak.kw": 100.0},
    ])
    rows = []
    # exact +10% boundary against bldg 0 (=100)
    for m in range(1, 13):
        rows.append({"Type": "com", "Source_File": "edge_boundary", "Month": m, "Monthly_Peak": 100.0})
    # zero ref -> only the all-zero building matches
    for m in range(1, 13):
        rows.append({"Type": "com", "Source_File": "edge_zeroref", "Month": m, "Monthly_Peak": 0.0})
    # impossible ref -> no match
    for m in range(1, 13):
        rows.append({"Type": "com", "Source_File": "edge_nomatch", "Month": m, "Monthly_Peak": 1.0})
    # no refs at all for this source file (everything matches at tol=5)
    # (simply emit nothing for edge_norefs... but pivot needs the source file; give it one NaN month)
    rows.append({"Type": "com", "Source_File": "edge_onemonth", "Month": 6, "Monthly_Peak": 100.0})
    # residential boundary
    for m in [12, 1, 2, 6, 7, 8]:
        rows.append({"Type": "res", "Source_File": "edge_res", "Month": m, "Monthly_Peak": 100.0})
    return com, res, pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------
def check(df_com, df_res, df_matches, tag):
    o_com = oracle_commercial(df_matches, df_com)
    o_res = oracle_residential(df_matches, df_res)
    for method in ("exact", "fast"):
        c = opt.match_commercial(df_matches, df_com, method)
        r = opt.match_residential(df_matches, df_res, method)
        ok, why = rows_equal(o_com, c)
        assert ok, f"[{tag}] commercial {method}: {why}"
        ok, why = rows_equal(o_res, r)
        assert ok, f"[{tag}] residential {method}: {why}"


def main():
    rng = np.random.default_rng(0)
    n_trials = 60
    for t in range(n_trials):
        n_bldg = int(rng.integers(20, 120))
        n_src = int(rng.integers(2, 8))
        states = ["NC"] if rng.random() < 0.7 else ["NC", "VA"]
        df_com, df_res, df_matches = make_random(rng, n_bldg, n_src, states)
        check(df_com, df_res, df_matches, f"random#{t}")
    print(f"random trials: {n_trials} PASS")

    df_com, df_res, df_matches = make_edge_cases()
    check(df_com, df_res, df_matches, "edge")
    print("edge cases: PASS")

    # report what the edge cases actually resolved to, as a sanity readout
    print("\n-- edge case readout (exact) --")
    for row in opt.match_commercial(df_matches, df_com, "exact"):
        print(f"  {row['Source_File']:<16} tol={row['Tolerance']!s:<5} matched={sorted(int(x) for x in row['Matched_Buildings'])}")
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
