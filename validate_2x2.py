#!/usr/bin/env python3
"""
Cross-case validation for the 2x2 pipeline consolidation.
Input : m2_all_cases_all_seasons.csv
Design: 4 cases x 2 seasons x 3 fire mixes x 2 feeders, 96 timesteps each.

Sections:
  1. Structural checks
  2. Per-case summary stats
  3. Donor effect (hold topology, swap EULP donor)
  4. Topology effect (hold donor, swap network)
  5. Stress ordering (baseline < mixed < stress, per feeder)
  6. Season comparison (summer vs winter peaks)
  7. Anomaly flags
"""
import sys
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}")

CSV = sys.argv[1] if len(sys.argv) > 1 else "m2_all_cases_all_seasons.csv"

PCOL, QCOL, SCOL = "P_3ph (kW)", "Q_3ph (kVAr)", "S_3ph (kVA)"
PHASE_P = ["P1 (kW)", "P2 (kW)", "P3 (kW)"]
KEYS = ["case", "topology", "donor", "season", "scenario", "feeder"]
SC_ORDER = {"fire_baseline": 0, "fire_mixed": 1, "fire_stress": 2}

EXPECT = dict(cases=4, seasons=2, scenarios=3, feeders=2, ts=96)
EXPECT_COMBOS = EXPECT["cases"] * EXPECT["seasons"] * EXPECT["scenarios"] * EXPECT["feeders"]


def rule(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def load():
    df = pd.read_csv(CSV)
    df.columns = [c.strip() for c in df.columns]
    return df


def build_peaks(data):
    g = data.groupby(KEYS, sort=False)
    peaks = g.agg(
        n_ts=(PCOL, "size"),
        peak_kW=(PCOL, "max"),
        min_kW=(PCOL, "min"),
        mean_kW=(PCOL, "mean"),
        peak_kVA=(SCOL, "max"),
        peak_kVAr=(QCOL, "max"),
        min_kVAr=(QCOL, "min"),
    ).reset_index()
    peaks["load_factor"] = peaks["mean_kW"] / peaks["peak_kW"]
    peaks["sc_rank"] = peaks["scenario"].map(SC_ORDER)
    return peaks


# ---------------------------------------------------------------------------
def sec1_structural(df, data, summ, peaks):
    rule("1. STRUCTURAL CHECKS")
    print(f"Total rows        : {len(df):,}  (expected 4,656)")
    print(f"  data rows       : {len(data):,}  (expected {EXPECT_COMBOS*EXPECT['ts']:,})")
    print(f"  summary rows    : {len(summ):,}  (expected {EXPECT_COMBOS})")

    # dimension cardinality
    print("\nDimension cardinality:")
    for col, exp in [("case", 4), ("topology", 2), ("donor", 2), ("season", 2),
                     ("scenario", 3), ("feeder", 2)]:
        got = df[col].nunique()
        print(f"  {col:9s}: {got}  (expected {exp})  {'OK' if got == exp else 'MISMATCH'}")

    # combo completeness
    print(f"\nData combos        : {len(peaks)} (expected {EXPECT_COMBOS})  "
          f"{'OK' if len(peaks)==EXPECT_COMBOS else 'MISMATCH'}")
    bad_ts = peaks[peaks.n_ts != EXPECT["ts"]]
    print(f"Combos w/ != {EXPECT['ts']} ts : {len(bad_ts)}  "
          f"{'OK' if bad_ts.empty else 'MISMATCH'}")
    if not bad_ts.empty:
        print(bad_ts[KEYS + ["n_ts"]].to_string(index=False))

    # timestep continuity inside each combo (must be 1..96, unique)
    def ts_ok(s):
        return sorted(s.tolist()) == list(range(1, EXPECT["ts"] + 1))
    cont = data.groupby(KEYS)["timestep"].apply(ts_ok)
    print(f"Combos w/ clean 1..96 timestep set: {cont.sum()}/{len(cont)}  "
          f"{'OK' if cont.all() else 'GAPS/DUPES'}")

    # duplicate (combo,timestep)
    dup = data.duplicated(subset=KEYS + ["timestep"]).sum()
    print(f"Duplicate (combo,timestep) rows   : {dup}  {'OK' if dup==0 else 'DUPES'}")

    # redundant column + mapping integrity
    bad_dd = (df["donor"] != df["design"]).sum()
    print(f"\ndonor == design on all rows       : {'OK' if bad_dd==0 else f'{bad_dd} mismatches'} "
          f"(columns are redundant)")
    ts_map = df.groupby("topology")["substation"].nunique()
    print(f"topology -> substation is 1:1     : {'OK' if (ts_map==1).all() else 'MISMATCH'}")
    cf_map = df.groupby("circuit_folder").size()
    print(f"circuit_folder values             : {df['circuit_folder'].nunique()} "
          f"(expected {EXPECT_COMBOS//EXPECT['seasons']} = subst x feeder x scenario)")

    # NaN audit
    power_cols = [PCOL, QCOL, SCOL, "hour", "timestep"]
    asset_cols = ["n_loads", "n_evs", "n_storage", "n_pv", "feeder_head_kva"]
    nan_power_data = data[power_cols].isna().sum().sum()
    nan_asset_summ = summ[asset_cols].isna().sum().sum()
    print(f"\nNaN in power/time cols of DATA rows : {nan_power_data}  "
          f"{'OK' if nan_power_data==0 else 'NULLS'}")
    print(f"NaN in asset cols of SUMMARY rows   : {nan_asset_summ}  "
          f"{'OK' if nan_asset_summ==0 else 'NULLS'}")

    # every data combo has exactly one summary and vice versa
    skeys = ["case", "season", "scenario", "feeder"]
    dset = set(map(tuple, data[skeys].drop_duplicates().values))
    sset = set(map(tuple, summ[skeys].drop_duplicates().values))
    print(f"\nData-combo set == summary-combo set : "
          f"{'OK' if dset==sset else 'MISMATCH'}  "
          f"(data {len(dset)}, summary {len(sset)})")
    summ_dup = summ.duplicated(subset=skeys).sum()
    print(f"Duplicate summary rows per combo    : {summ_dup}  {'OK' if summ_dup==0 else 'DUPES'}")


# ---------------------------------------------------------------------------
def sec2_per_case(peaks):
    rule("2. PER-CASE SUMMARY STATS  (across all season/scenario/feeder combos)")
    by_case = peaks.groupby("case").agg(
        combos=("peak_kW", "size"),
        peak_kW_max=("peak_kW", "max"),
        peak_kW_mean=("peak_kW", "mean"),
        peak_kVA_max=("peak_kVA", "max"),
        peak_kVAr_max=("peak_kVAr", "max"),
        min_kW_min=("min_kW", "min"),
        lf_mean=("load_factor", "mean"),
        lf_min=("load_factor", "min"),
    )
    print(by_case.to_string())
    print("\nWorst-case (max peak_kVA) combo per case:")
    idx = peaks.groupby("case")["peak_kVA"].idxmax()
    print(peaks.loc[idx, ["case", "season", "scenario", "feeder",
                          "peak_kW", "peak_kVAr", "peak_kVA", "load_factor"]]
          .to_string(index=False))


# ---------------------------------------------------------------------------
def sec3_donor(peaks):
    rule("3. DONOR EFFECT  (hold topology+feeder+season+scenario, swap EULP donor)")
    pk = peaks.copy()
    idx = ["topology", "season", "scenario", "feeder"]
    wide = pk.pivot_table(index=idx, columns="donor", values="peak_kVA")
    wide = wide.dropna()
    wide["abs_delta_TX_minus_NC"] = wide["TX"] - wide["NC"]
    wide["pct_delta"] = 100 * wide["abs_delta_TX_minus_NC"] / wide["NC"]
    print("Paired peak_kVA (TX donor vs NC donor) on identical network:")
    print(wide.to_string())
    print("\nDonor effect rolled up by topology (mean peak_kVA):")
    roll = pk.groupby(["topology", "donor"])["peak_kVA"].mean().unstack("donor")
    roll["TX_vs_NC_pct"] = 100 * (roll["TX"] - roll["NC"]) / roll["NC"]
    print(roll.to_string())


# ---------------------------------------------------------------------------
def sec4_topology(peaks):
    rule("4. TOPOLOGY EFFECT  (hold donor, swap network)")
    print("NOTE: feeder labels (circuit_1/2) are NOT the same physical feeder across "
          "topologies,\n      so this is a network-level comparison, not a paired one.\n")
    roll = peaks.groupby(["donor", "topology"]).agg(
        peak_kVA_mean=("peak_kVA", "mean"),
        peak_kVA_max=("peak_kVA", "max"),
        peak_kW_max=("peak_kW", "max"),
    )
    print(roll.to_string())
    print("\nFeeder-head peak_kVA by topology (max across everything):")
    print(peaks.groupby("topology")["peak_kVA"].agg(["min", "mean", "max"]).to_string())


# ---------------------------------------------------------------------------
def sec5_stress(peaks):
    rule("5. STRESS ORDERING  (baseline < mixed < stress, per case/season/feeder)")
    grp = ["case", "season", "feeder"]
    violations = []
    rows = []
    for key, sub in peaks.groupby(grp):
        sub = sub.sort_values("sc_rank")
        vals = sub.set_index("scenario")["peak_kVA"]
        b = vals.get("fire_baseline", np.nan)
        m = vals.get("fire_mixed", np.nan)
        s = vals.get("fire_stress", np.nan)
        mono = (b < m < s)
        rows.append((*key, b, m, s, "OK" if mono else "VIOLATION"))
        if not mono:
            violations.append((*key, b, m, s))
    out = pd.DataFrame(rows, columns=grp + ["baseline", "mixed", "stress", "monotone?"])
    print("peak_kVA by scenario (should strictly increase L->R):")
    print(out.to_string(index=False))
    print(f"\nMonotone groups: {(out['monotone?']=='OK').sum()}/{len(out)}")
    if violations:
        print("!! STRESS-ORDERING VIOLATIONS (expected in summer — HP efficiency effect):")
        for v in violations:
            print("   ", v)
    else:
        print("All feeders monotone on peak_kVA. (nested seeding holds)")

    # also check peak_kW monotonicity
    print("\nAlso checking peak_kW monotonicity:")
    bad_kw = 0
    for key, sub in peaks.groupby(grp):
        sub = sub.sort_values("sc_rank")
        if not sub["peak_kW"].is_monotonic_increasing:
            bad_kw += 1
            print("   kW non-monotone:", key, sub["peak_kW"].tolist())
    print(f"   peak_kW monotone groups: {len(out)-bad_kw}/{len(out)}")


def sec5b_asset_nesting(summ):
    rule("5b. ASSET-COUNT NESTING  (summary rows; validates nested seeding mechanism)")
    grp = ["case", "season", "feeder"]
    bad = 0
    for key, sub in summ.groupby(grp):
        sub = sub.assign(r=sub["scenario"].map(SC_ORDER)).sort_values("r")
        for col in ["n_loads", "n_evs", "n_storage", "n_pv"]:
            if not sub[col].is_monotonic_increasing:
                bad += 1
                print(f"   non-nested {col}: {key} -> {sub[col].tolist()}")
    print(f"Non-monotone asset sequences: {bad} "
          f"{'(all asset counts nest baseline<=mixed<=stress)' if bad==0 else ''}")
    print("\nAsset counts by topology x scenario (mean over feeders/seasons):")
    print(summ.groupby(["topology", "scenario"])[["n_loads", "n_evs", "n_storage", "n_pv"]]
          .mean().to_string())


# ---------------------------------------------------------------------------
def sec6_season(peaks):
    rule("6. SEASON COMPARISON  (summer vs winter peaks)")
    idx = ["case", "scenario", "feeder"]
    wide = peaks.pivot_table(index=idx, columns="season", values="peak_kVA").dropna()
    wide["winter_minus_summer"] = wide["winter"] - wide["summer"]
    wide["pct"] = 100 * wide["winter_minus_summer"] / wide["summer"]
    wide["dominant"] = np.where(wide["winter"] > wide["summer"], "WINTER", "summer")
    print("peak_kVA by season:")
    print(wide.to_string())
    print("\nWhich season drives the annual peak, by case:")
    dom = wide.reset_index().groupby("case")["dominant"].agg(
        lambda s: s.value_counts().to_dict())
    print(dom.to_string())
    print("\nMean winter-vs-summer % by topology:")
    tmp = wide.reset_index().merge(
        peaks[["case", "topology"]].drop_duplicates(), on="case")
    print(tmp.groupby("topology")["pct"].mean().to_string())


# ---------------------------------------------------------------------------
def sec7_anomalies(df, data, summ, peaks):
    rule("7. ANOMALY FLAGS")

    # a. reverse power flow / negative net load (PV backfeed or solver artifact)
    neg = data[data[PCOL] < 0]
    print(f"[a] Data rows with negative P_3ph (reverse flow): {len(neg)}")
    if not neg.empty:
        print(neg.groupby(KEYS).size().to_string())
    minkw = peaks.loc[peaks["min_kW"].idxmin()]
    print(f"    Global min P_3ph = {minkw['min_kW']:,.1f} kW "
          f"({minkw['case']}/{minkw['season']}/{minkw['scenario']}/{minkw['feeder']})")

    # b. non-positive / near-zero apparent power (non-convergence signature)
    zero_s = data[data[SCOL] <= 0]
    print(f"\n[b] Data rows with S_3ph <= 0 (non-convergence signature): {len(zero_s)}")

    # c. power-factor sanity (Q should not dwarf P)
    pf = data[PCOL] / data[SCOL].replace(0, np.nan)
    print(f"\n[c] Power-factor (P/S) range: {pf.min():.3f} .. {pf.max():.3f}")
    lowpf = (pf < 0.7).sum()
    print(f"    Rows with PF < 0.70: {lowpf}")

    # d. phase imbalance: max phase P vs mean phase P
    pp = data[PHASE_P]
    imbalance = (pp.max(axis=1) - pp.min(axis=1)) / pp.mean(axis=1).replace(0, np.nan)
    print(f"\n[d] Per-row 3-phase imbalance (max-min)/mean: "
          f"median {imbalance.median()*100:.1f}%, p95 {imbalance.quantile(.95)*100:.1f}%, "
          f"max {imbalance.max()*100:.1f}%")
    worst = data.loc[imbalance.idxmax()]
    print(f"    worst row: {worst['case']}/{worst['season']}/{worst['scenario']}/"
          f"{worst['feeder']} ts={int(worst['timestep'])}  "
          f"P1/P2/P3 = {worst['P1 (kW)']:.0f}/{worst['P2 (kW)']:.0f}/{worst['P3 (kW)']:.0f}")

    # e. S_3ph vs S_sum_3ph consistency
    if "S_sum_3ph (kVA)" in data.columns:
        diff = (data[SCOL] - data["S_sum_3ph (kVA)"]).abs()
        rel = diff / data[SCOL].replace(0, np.nan)
        print(f"\n[e] |S_3ph - S_sum_3ph| relative diff: median {rel.median()*100:.3f}%, "
              f"max {rel.max()*100:.3f}%")

    # f. feeder-head loading vs thermal capacity (UPDATED: uses feeder_head_kva)
    CAP_COL = "feeder_head_kva"
    xf = summ[["case", "season", "scenario", "feeder", CAP_COL]]
    m = peaks.merge(xf, on=["case", "season", "scenario", "feeder"], how="left")
    m["loading_pct"] = 100 * m["peak_kVA"] / m[CAP_COL]
    print(f"\n[f] Feeder-head peak_kVA vs feeder_head_kva thermal capacity:")
    print(m.groupby(["topology", "feeder"])
          .agg(feeder_head_kva=(CAP_COL, "first"),
               peak_kVA_max=("peak_kVA", "max"),
               loading_pct_max=("loading_pct", "max")).to_string())
    print("    -> loading_pct should now be realistic (50-150% range).\n"
          "       If still >> 100% everywhere, check LineCodes.dss parsing.")

    # g. outlier peaks (z-score within topology)
    print("\n[g] Peak outliers (|z| > 3 within topology, peak_kVA):")
    z = peaks.copy()
    z["z"] = z.groupby("topology")["peak_kVA"].transform(
        lambda s: (s - s.mean()) / s.std(ddof=0))
    out = z[z["z"].abs() > 3]
    print(f"    {len(out)} outliers" if not out.empty else "    none")
    if not out.empty:
        print(out[KEYS + ["peak_kVA", "z"]].to_string(index=False))

    # h. load factor sanity
    print(f"\n[h] Load factor range: {peaks['load_factor'].min():.3f} .. "
          f"{peaks['load_factor'].max():.3f}")
    odd = peaks[(peaks["load_factor"] <= 0) | (peaks["load_factor"] > 1)]
    print(f"    LF outside (0,1]: {len(odd)}  {'OK' if odd.empty else 'CHECK'}")


def main():
    df = load()
    data = df[df.row_type == "data"].copy()
    summ = df[df.row_type == "summary"].copy()
    peaks = build_peaks(data)

    sec1_structural(df, data, summ, peaks)
    sec2_per_case(peaks)
    sec3_donor(peaks)
    sec4_topology(peaks)
    sec5_stress(peaks)
    sec5b_asset_nesting(summ)
    sec6_season(peaks)
    sec7_anomalies(df, data, summ, peaks)

    # persist the derived per-combo peak table for downstream use
    peaks.drop(columns=["sc_rank"]).to_csv("peaks_per_combo.csv", index=False)
    print("\n[written] peaks_per_combo.csv  (48 rows, one per simulation combo)")


if __name__ == "__main__":
    main()
