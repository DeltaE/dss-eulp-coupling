"""
MethodsX paper figure generation script.
Produces three publication-quality figures (300 dpi, white background).

Data source: aggregate_m2_combined.csv from SMART-DS / EULP pipeline.
Province-to-state mapping: ab→MT, bc→WA, on→MI, qc→VT.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os

# ── Paths ──────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "..", "aggregate_m2_combined.csv")
OUT_DIR = BASE

# ── Province → state mapping ──────────────────────────────────────────
PROV_TO_STATE = {"ab": "MT", "bc": "WA", "on": "MI", "qc": "VT"}

# ── Shared style ──────────────────────────────────────────────────────
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
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# ── Load data ─────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)
df.columns = df.columns.str.strip()
df["state"] = df["design"].map(PROV_TO_STATE)

# Keep only time-series rows
df = df[df["row_type"] == "data"].copy()


# ======================================================================
# FIGURE A — Substation head power flow, circuit 52, MI, winter
# ======================================================================
def figure_a():
    mask = (
        (df["feeder"] == "circuit_52")
        & (df["state"] == "MI")
        & (df["season"] == "winter")
    )
    sub = df[mask].copy()

    fig, ax = plt.subplots(figsize=(8, 4.5))

    colours = {"0": "#1f77b4", "1": "#d62728"}
    labels = {
        "0": "Scenario 0 (high EV, uncontrolled)",
        "1": "Scenario 1 (baseline)",
    }

    for scen in ["0", "1"]:
        s = sub[sub["scenario"].astype(str) == scen].sort_values("timestep")
        hours = s["hour"].values + (s["timestep"].values % 4) * 0.25
        ax.plot(hours, s["P_3ph (kW)"].values, color=colours[scen],
                linewidth=1.4, label=f"{labels[scen]} — P (kW)")
        ax.plot(hours, s["S_3ph (kVA)"].values, color=colours[scen],
                linewidth=1.4, linestyle="--",
                label=f"{labels[scen]} — S (kVA)")

    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Power (kW / kVA)")
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.set_title("Substation head power flow — Circuit 52, MI (winter)")
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "figure_a_power_flow.png"))
    plt.close(fig)
    print("Figure A saved.")


# ======================================================================
# FIGURE B — Tolerance escalation distribution (hardcoded table)
# ======================================================================
def figure_b():
    tol_labels = ["5%", "10%", "15%", "20%", "25%", "30%",
                  "35%", "40%", "45%", "50%", "No match"]
    data = {
        "MT": [0, 35, 163, 232, 155, 87, 69, 59, 37, 24, 22],
        "WA": [3, 60, 202, 293, 164, 85, 42, 26, 7, 1, 0],
        "MI": [0, 336, 182, 122, 95, 60, 38, 22, 13, 3, 2],
        "VT": [7, 75, 216, 218, 93, 101, 66, 44, 30, 12, 21],
    }

    x = np.arange(len(tol_labels))
    width = 0.2
    colours = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for i, (state, vals) in enumerate(data.items()):
        ax.bar(x + i * width, vals, width, label=state, color=colours[i])

    ax.set_xlabel("Tolerance level")
    ax.set_ylabel("Number of loads matched")
    ax.set_xticks(x + 1.5 * width)
    ax.set_xticklabels(tol_labels, rotation=45, ha="right")
    ax.set_title("Commercial load matching: tolerance escalation by state")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "figure_b_tolerance.png"))
    plt.close(fig)
    print("Figure B saved.")


# ======================================================================
# FIGURE C — Peak loading distribution by state (box-and-whisker)
# ======================================================================
def figure_c():
    # Peak P_3ph per (circuit, state, season, scenario)
    grouped = (
        df.groupby(["feeder", "state", "season", "scenario"])
        .agg(
            peak_kW=("P_3ph (kW)", "max"),
            xfmr_kva=("substation_xfmr_kva", "first"),
        )
        .reset_index()
    )

    # Compute loading % where transformer rating is available
    grouped["xfmr_kva"] = pd.to_numeric(grouped["xfmr_kva"], errors="coerce")
    has_xfmr = grouped["xfmr_kva"].notna() & (grouped["xfmr_kva"] > 0)

    if has_xfmr.sum() > 0:
        grouped.loc[has_xfmr, "loading_pct"] = (
            grouped.loc[has_xfmr, "peak_kW"]
            / grouped.loc[has_xfmr, "xfmr_kva"]
            * 100
        )
        y_col, y_label = "loading_pct", "Peak loading (%)"
        title = "Peak substation loading distribution by state"
    else:
        y_col, y_label = "peak_kW", "Peak P_3ph (kW)"
        title = "Peak substation power distribution by state"

    states_order = ["MT", "WA", "MI", "VT"]
    box_data = [
        grouped.loc[grouped["state"] == s, y_col].dropna().values
        for s in states_order
    ]

    fig, ax = plt.subplots(figsize=(6, 5))
    bp = ax.boxplot(
        box_data,
        labels=states_order,
        patch_artist=True,
        widths=0.5,
        showfliers=True,
        flierprops=dict(marker="o", markersize=4, alpha=0.5),
    )
    colours = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for patch, c in zip(bp["boxes"], colours):
        patch.set_facecolor(c)
        patch.set_alpha(0.6)

    ax.set_xlabel("State")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "figure_c_peak_loading.png"))
    plt.close(fig)
    print("Figure C saved.")


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    figure_a()
    figure_b()
    figure_c()
    print("All figures saved to:", OUT_DIR)
