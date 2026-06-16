"""
MethodsX paper figure generation script (v2 — fully data-driven).
Produces three publication-quality figures (300 dpi, embedded metadata).

Required inputs:
  1. aggregate_m2_combined.csv     — time-series + summary rows from OpenDSS campaign
  2. circuit_summary_combined.csv  — per-run metadata (xfmr ratings, DER counts)
  3. Commercial matching CSVs      — one per state, from Stage 3B pipeline

Province-to-state mapping: ab→MT, bc→WA, on→MI, qc→VT.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════
# Expected layout:
#   dist/
#   ├── ab_3b/df_com_matches_out_MT.csv
#   ├── bc_3b/df_com_matches_out_WA.csv
#   ├── on_3b/df_com_matches_out_MI.csv
#   ├── qc_3b/df_com_matches_out_VT.csv
#   └── 9_results_analysis/
#       ├── aggregate_m2_combined.csv
#       ├── circuit_summary_combined.csv
#       └── methodsx_figures/          ← this script lives here
#           └── figure_generation_methodsx.py

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = BASE
DIST_DIR = os.path.normpath(os.path.join(BASE, ".."))

AGGREGATE_CSV = os.path.join(RESULTS_DIR, "aggregate_m2_combined.csv")
CIRCUIT_SUMMARY_CSV = os.path.join(RESULTS_DIR, "circuit_summary_combined.csv")

# Stage 3B commercial matching outputs (one per state).
# Each must have at least: a Tolerance column and one row per matched load.
MATCHING_FILES = {
    STATE: os.path.join(DIST_DIR, "3_tolerance_matching", f"df_com_matches_out_{STATE}.csv"),
}

OUT_DIR = BASE

# ══════════════════════════════════════════════════════════════════════
# PROVINCE → STATE MAPPING & VARIANT LABELS
# ══════════════════════════════════════════════════════════════════════
PROV_TO_STATE = {STATE.lower(): STATE, STATE: STATE}
STATES_ORDER = [STATE]
STATE_COLOURS = {STATE: "#1f77b4"}

SCENARIO_LABELS = {
    0: "Scenario 0 — high EV, uncontrolled",
    1: "Scenario 1 — mixed DER, controlled",
    2: "Scenario 2 — baseline (near-zero)",
}
SCENARIO_COLOURS = {0: "#1f77b4", 1: "#d62728", 2: "#2ca02c"}

# ══════════════════════════════════════════════════════════════════════
# SHARED MATPLOTLIB STYLE
# ══════════════════════════════════════════════════════════════════════
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "legend.fontsize": 10,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

# Tolerance bins used by the matching pipeline
TOL_BINS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
TOL_LABELS = [f"{t}%" for t in TOL_BINS] + ["No match"]


# ══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════
def load_aggregate(path):
    """Load aggregate CSV, strip whitespace from column names, map states."""
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df["state"] = df["design"].map(PROV_TO_STATE)
    return df


def load_circuit_summary(path):
    """Load circuit summary with transformer ratings."""
    cs = pd.read_csv(path)
    cs.columns = cs.columns.str.strip()
    cs["state"] = cs["design"].map(PROV_TO_STATE)
    return cs


def load_matching_csvs(file_dict):
    """
    Load commercial matching CSVs from the Stage 3B pipeline.
    Expects a 'Tolerance' column (numeric %, e.g. 5, 10, …, 50)
    with NaN or a sentinel for unmatched loads.
    Returns a combined DataFrame with columns [state, tolerance].
    """
    frames = []
    missing = []
    for state, fpath in file_dict.items():
        if not os.path.exists(fpath):
            missing.append((state, fpath))
            continue
        tmp = pd.read_csv(fpath)
        tmp.columns = tmp.columns.str.strip()
        # Find the tolerance column (case-insensitive search)
        tol_col = None
        for c in tmp.columns:
            if "tolerance" in c.lower():
                tol_col = c
                break
        if tol_col is None:
            print(f"  WARNING: {fpath} has no 'Tolerance' column. Columns: {list(tmp.columns)}")
            missing.append((state, fpath))
            continue
        out = pd.DataFrame({
            "state": state,
            "tolerance": pd.to_numeric(tmp[tol_col], errors="coerce"),
        })
        frames.append(out)

    if missing:
        print(f"\n  ⚠  Missing or invalid matching files:")
        for st, fp in missing:
            print(f"     {st}: {fp}")

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════
# FIGURE A — Substation head power flow (single feeder, single season)
# ══════════════════════════════════════════════════════════════════════
def figure_a(df, feeder="circuit_52", state="MI", season="winter"):
    """
    96-timestep power flow profile comparing scenarios.
    Plots P (kW) solid and S (kVA) dashed for each scenario present.
    """
    data = df[df["row_type"] == "data"].copy()
    mask = (
        (data["feeder"] == feeder)
        & (data["state"] == state)
        & (data["season"] == season)
    )
    sub = data[mask].copy()

    if sub.empty:
        print(f"  ERROR: No data for {feeder} / {state} / {season}. Skipping Figure A.")
        return

    scenarios = sorted(sub["scenario"].unique())
    fig, ax = plt.subplots(figsize=(8, 4.5))

    for scen in scenarios:
        s = sub[sub["scenario"] == scen].sort_values("timestep")
        hours = s["hour"].values + (s["timestep"].values % 4) * 0.25
        colour = SCENARIO_COLOURS.get(scen, "#888888")
        label = SCENARIO_LABELS.get(scen, f"Scenario {scen}")

        ax.plot(hours, s["P_3ph (kW)"].values,
                color=colour, linewidth=1.4,
                label=f"{label} — P (kW)")
        ax.plot(hours, s["S_3ph (kVA)"].values,
                color=colour, linewidth=1.4, linestyle="--",
                label=f"{label} — S (kVA)")

    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Power (kW / kVA)")
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.set_title(f"Substation head power flow — {feeder.replace('_', ' ').title()}, "
                 f"{state} ({season})")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "figure_a_power_flow.png")
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure A saved → {out_path}")


# ══════════════════════════════════════════════════════════════════════
# FIGURE B — Commercial tolerance escalation (grouped bar)
# ══════════════════════════════════════════════════════════════════════
def figure_b(match_df):
    """
    Grouped bar chart: number of commercial loads matched at each
    tolerance level, by state.  Reads from matching pipeline CSVs.
    """
    if match_df is None:
        print("  ERROR: No matching data loaded. Skipping Figure B.")
        return

    # Bin tolerance values into the standard escalation levels
    counts = {st: [] for st in STATES_ORDER}
    for state in STATES_ORDER:
        state_df = match_df[match_df["state"] == state]
        matched = state_df["tolerance"].dropna()
        n_total = len(state_df)  # one row per commercial load (matched + unmatched)
        for tol in TOL_BINS:
            counts[state].append(int((matched == tol).sum()))
        # "No match" = total rows minus those with a valid tolerance value
        n_matched = int(matched.notna().sum())
        counts[state].append(n_total - n_matched)

    x = np.arange(len(TOL_LABELS))
    width = 0.2

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, state in enumerate(STATES_ORDER):
        ax.bar(x + i * width, counts[state], width,
               label=state, color=STATE_COLOURS[state])

    ax.set_xlabel("Tolerance level")
    ax.set_ylabel("Number of loads matched")
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels(TOL_LABELS, rotation=45, ha="right")
    ax.set_title("Commercial load matching: tolerance escalation by state")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "figure_b_tolerance.png")
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure B saved → {out_path}")


# ══════════════════════════════════════════════════════════════════════
# FIGURE C — Peak substation power by state (box-and-whisker)
# ══════════════════════════════════════════════════════════════════════
def figure_c(df):
    """
    Box-and-whisker of peak substation active power by state.
    Computes peak P_3ph per (feeder, state, season, scenario) from
    time-series data rows.

    NOTE: feeder_head_kva captures feeder-head thermal capacity from
    the monitored source line's LineCode normamps and circuit basekV.
    """
    data = df[df["row_type"] == "data"].copy()
    data["P_3ph (kW)"] = pd.to_numeric(data["P_3ph (kW)"], errors="coerce")

    # Peak per run
    peaks = (
        data.groupby(["feeder", "design", "season", "scenario"])["P_3ph (kW)"]
        .max()
        .reset_index()
        .rename(columns={"P_3ph (kW)": "peak_kW"})
    )
    peaks["state"] = peaks["design"].map(PROV_TO_STATE)

    box_data = [
        peaks.loc[peaks["state"] == s, "peak_kW"].dropna().values
        for s in STATES_ORDER
    ]

    fig, ax = plt.subplots(figsize=(6, 5))
    bp = ax.boxplot(
        box_data,
        labels=STATES_ORDER,
        patch_artist=True,
        widths=0.5,
        showfliers=True,
        flierprops=dict(marker="o", markersize=4, alpha=0.5),
    )
    for patch, state in zip(bp["boxes"], STATES_ORDER):
        patch.set_facecolor(STATE_COLOURS[state])
        patch.set_alpha(0.6)

    ax.set_xlabel("State")
    ax.set_ylabel("Peak P_3ph (kW)")
    ax.set_title("Peak substation power distribution by state")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, "figure_c_peak_loading.png")
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Figure C saved → {out_path}")


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Loading data...")

    # --- Aggregate time-series ---
    if not os.path.exists(AGGREGATE_CSV):
        sys.exit(f"FATAL: aggregate CSV not found at {AGGREGATE_CSV}")
    agg = load_aggregate(AGGREGATE_CSV)
    print(f"  aggregate: {len(agg)} rows, "
          f"{agg[agg['row_type']=='data'].shape[0]} data + "
          f"{agg[agg['row_type']=='summary'].shape[0]} summary")

    # --- Commercial matching (optional — Figure B only) ---
    print("\nLoading commercial matching files...")
    match_df = load_matching_csvs(MATCHING_FILES)
    if match_df is not None:
        print(f"  matching: {len(match_df)} total rows across "
              f"{match_df['state'].nunique()} states")

    # --- Generate figures ---
    print("\n── Figure A ──")
    figure_a(agg)

    print("\n── Figure B ──")
    figure_b(match_df)

    print("\n── Figure C ──")
    figure_c(agg)

    print(f"\nDone. All figures saved to: {OUT_DIR}")
