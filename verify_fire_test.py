#!/usr/bin/env python
"""
verify_fire_test.py — Per-phase verification for dss-eulp-coupling pipeline

Reads configuration from pipeline_config.yaml (via pipeline_utils.load_config())
with fallback to PIPELINE_* environment variables.

Usage:
    python verify_fire_test.py --phase pre
    python verify_fire_test.py --phase 5c
    python verify_fire_test.py --phase 5c --scenario dm
    python verify_fire_test.py --all
    python verify_fire_test.py --all --scenario dm
"""

import argparse
import json
import os
import sys
import time

import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════
# Configuration — prefer pipeline_config.yaml, env var fallback
# ═══════════════════════════════════════════════════════════════════════════

def _load_pipeline_config():
    """
    Load pipeline configuration.

    Priority (pipeline_utils.load_config already merges env overrides):
      1. pipeline_config.yaml values
      2. PIPELINE_* env var overrides (handled inside load_config)
    If yaml or import fails entirely, fall back to pure env vars.
    """
    try:
        from pipeline_utils import load_config
        cfg = load_config()
    except Exception as e:
        print(f"  [WARN] Could not load pipeline_config.yaml: {e}")
        print(f"         Falling back to environment variables.\n")
        cfg = {}

    state = cfg.get("state", os.environ.get("PIPELINE_STATE", "TX"))
    season = cfg.get("season", os.environ.get("PIPELINE_SEASON", "summer"))

    # EULP download parquet root — try config keys, then env var, then default.
    # Note: smart_ds_parquet_root is a DIFFERENT path (Phase 2 matching source).
    parquet_root = (
        cfg.get("parquet_data_root")
        or cfg.get("eulp_parquet_root")
        or os.environ.get("PIPELINE_PARQUET_ROOT")
        or r"D:\lvg\parquet_data"
    )

    return {
        "state": state,
        "season": season,
        "parquet_data_root": parquet_root,
        "_raw": cfg,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Globals — set at startup, SCENARIO overridden by argparse
# ═══════════════════════════════════════════════════════════════════════════

CFG = _load_pipeline_config()
STATE = CFG["state"]
SEASON = CFG["season"]
PARQUET_ROOT = CFG["parquet_data_root"]
SCENARIO = "baseline"

_pass = 0
_fail = 0
_phase_results = []   # [{phase, passed, failed, time_s}, ...]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def check(label, condition, detail=""):
    """Record and print one pass/fail assertion."""
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  [PASS] {label}")
    else:
        _fail += 1
        print(f"  [FAIL] {label}")
    if detail:
        print(f"         {detail}")


def phase_header(name):
    """Print phase banner with active configuration."""
    print(f"\n{'='*64}")
    print(f"  Phase {name}")
    print(f"{'='*64}")
    print(f"  State={STATE}  Season={SEASON}  Scenario={SCENARIO}")


def _run_phase(phase_key, func):
    """Execute a phase function with timing and per-phase result tracking."""
    global _pass, _fail
    p0, f0 = _pass, _fail
    t0 = time.perf_counter()
    func()
    elapsed = time.perf_counter() - t0
    _phase_results.append({
        "phase":  phase_key,
        "passed": _pass - p0,
        "failed": _fail - f0,
        "time_s": elapsed,
    })
    print(f"\n  Phase {phase_key} completed in {elapsed:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# Scenario helpers
# ═══════════════════════════════════════════════════════════════════════════

def _scenario_suffix():
    """Return '' for baseline, '_dm', or '_uncontrolled'."""
    return "" if SCENARIO == "baseline" else f"_{SCENARIO}"


def _dir_matches_scenario(dirname):
    """True when *dirname* belongs to the active scenario."""
    has_dm = dirname.endswith("_dm")
    has_uc = dirname.endswith("_uncontrolled")
    if SCENARIO == "baseline":
        return not has_dm and not has_uc
    if SCENARIO == "dm":
        return has_dm
    if SCENARIO == "uncontrolled":
        return has_uc
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Phase checks
# ═══════════════════════════════════════════════════════════════════════════

def verify_pre():
    phase_header("Pre — Registry + Scan + Pivot")

    # feeder_registry.json
    exists = os.path.exists("feeder_registry.json")
    check("feeder_registry.json exists", exists)
    if exists:
        with open("feeder_registry.json", encoding="utf-8") as fh:
            reg = json.load(fh)
        feeders = reg.get("feeders", [])
        check(f"Registry has feeders (found {len(feeders)})", len(feeders) > 0)
        for fd in feeders:
            print(f"         - {fd['feeder_name']}")

    # parsed_loads.csv
    exists = os.path.exists("parsed_loads.csv")
    check("parsed_loads.csv exists", exists)
    if exists:
        df = pd.read_csv("parsed_loads.csv")
        check(f"parsed_loads.csv rows: {len(df)}", len(df) > 0)

    # parsed_loads_SUMMARY.csv
    exists = os.path.exists("parsed_loads_SUMMARY.csv")
    check("parsed_loads_SUMMARY.csv exists", exists)
    if exists:
        s = pd.read_csv("parsed_loads_SUMMARY.csv")
        check(
            f"Summary rows={s.shape[0]}, feeders={s['Feeder'].nunique()}",
            s.shape[0] > 0,
        )

    # Cross-check: every registry feeder appears in summary
    if (os.path.exists("feeder_registry.json")
            and os.path.exists("parsed_loads_SUMMARY.csv")):
        with open("feeder_registry.json", encoding="utf-8") as fh:
            reg = json.load(fh)
        s = pd.read_csv("parsed_loads_SUMMARY.csv")
        rf = {e["feeder_name"] for e in reg["feeders"]}
        sf = set(s["Feeder"].unique())
        missing = rf - sf
        check(
            "All registry feeders present in summary",
            len(missing) == 0,
            f"Missing: {missing}" if missing else "",
        )


def verify_phase1():
    phase_header("1 — EULP Metadata Generation")

    for kind in ("commercial", "residential"):
        fp = os.path.join(
            "1_data_provenance", "outputs", "pipeline_state",
            f"{kind}_data_SELECT_STATES.csv",
        )
        exists = os.path.exists(fp)
        check(f"{kind}_data_SELECT_STATES.csv exists", exists)
        if exists:
            df = pd.read_csv(fp)
            check(f"  rows={df.shape[0]}, cols={df.shape[1]}", df.shape[0] > 0)


def verify_phase2():
    phase_header("2 — Circuit Copy + Daily Lists + Parquet Matching")

    cpf = os.path.join("2_circuit_matching", "circuits_plain_format")
    if os.path.isdir(cpf):
        dirs = [d for d in os.listdir(cpf)
                if os.path.isdir(os.path.join(cpf, d))]
        check(f"Feeder dirs in circuits_plain_format: {len(dirs)}", len(dirs) > 0)
        for d in dirs:
            print(f"         - {d}")
    else:
        check("circuits_plain_format/ exists", False)

    rpm = os.path.join("2_circuit_matching", "review_parquet_matches.csv")
    check("review_parquet_matches.csv exists", os.path.exists(rpm))


def verify_phase3():
    phase_header("3 — Tolerance Matching")

    for kind in ("com", "res"):
        fp = os.path.join(
            "3_tolerance_matching", f"df_{kind}_matches_out_{STATE}.csv",
        )
        exists = os.path.exists(fp)
        check(f"df_{kind}_matches_out_{STATE}.csv exists", exists)
        if exists:
            df = pd.read_csv(fp)
            check(f"  rows={df.shape[0]}", df.shape[0] > 0)


def verify_phase4():
    phase_header("4 — Building Selection")

    for kind in ("commercial", "residential"):
        fp = os.path.join("4_quota_assignment", f"{STATE}_final_{kind}.csv")
        exists = os.path.exists(fp)
        check(f"{STATE}_final_{kind}.csv exists", exists)
        if exists:
            df = pd.read_csv(fp)
            check(f"  rows={df.shape[0]} (zero = upstream problem)", df.shape[0] > 0)


def verify_phase5a():
    phase_header("5a — EULP Parquet Downloads")

    if not os.path.isdir(PARQUET_ROOT):
        check(
            f"Parquet root exists: {PARQUET_ROOT}", False,
            "Set parquet_data_root in pipeline_config.yaml",
        )
        return

    entries = os.listdir(PARQUET_ROOT)
    pq_files = [e for e in entries if e.endswith(".parquet")]
    pq_dirs = [e for e in entries
               if os.path.isdir(os.path.join(PARQUET_ROOT, e))]

    if pq_files:
        check(f"Parquet files in {PARQUET_ROOT}: {len(pq_files)}", True)
        for p in pq_files[:5]:
            print(f"         - {p}")
        if len(pq_files) > 5:
            print(f"         ... and {len(pq_files) - 5} more")
    elif pq_dirs:
        state_dirs = [d for d in pq_dirs if STATE.lower() in d.lower()]
        check(f"{STATE} parquet dirs: {len(state_dirs)}", len(state_dirs) > 0)
        for d in state_dirs[:10]:
            print(f"         - {d}")
        if len(state_dirs) > 10:
            print(f"         ... and {len(state_dirs) - 10} more")
    else:
        check(f"Parquet content in {PARQUET_ROOT}", False,
              "Directory exists but is empty")


def verify_phase5b():
    phase_header("5b — Profile Scaling + Peak Day Extraction")

    pb = os.path.join("5b_profile_generation", f"{STATE}_parquet_and_bldgs.csv")
    exists = os.path.exists(pb)
    check(f"{STATE}_parquet_and_bldgs.csv exists", exists)
    if exists:
        df = pd.read_csv(pb)
        feeders = df["Feeder"].unique().tolist()
        check(f"  Feeders: {feeders}", len(feeders) >= 1)

    # Daily parquet dirs (scenario-filtered)
    gen_dir = os.path.join("5b_profile_generation", "daily_parquets")
    if not os.path.isdir(gen_dir):
        check("daily_parquets/ directory exists", False)
        return

    all_dirs = [
        d for d in os.listdir(gen_dir)
        if d.startswith(f"{STATE}_") and SEASON in d
        and os.path.isdir(os.path.join(gen_dir, d))
    ]
    matched = [d for d in all_dirs if _dir_matches_scenario(d)]
    check(
        f"Daily parquet dirs ({SCENARIO}, {SEASON}): {len(matched)}",
        len(matched) > 0,
    )
    for d in matched:
        print(f"         - {d}")


def verify_phase5d():
    phase_header("5d — Scenario Control CSVs")

    sd = os.path.join("5d_scenario_controls", "get_scenario_csv_controls")
    if not os.path.isdir(sd):
        check("5d control CSV directory exists", False)
        return

    controls = [
        f for f in os.listdir(sd)
        if f.endswith(".csv") and ("_dm" in f or "_uncontrolled" in f)
    ]
    check(f"Control CSVs found: {len(controls)}", len(controls) > 0)
    for c in controls:
        print(f"         - {c}")


def verify_phase5c():
    phase_header("5c — Parquet to CSV Conversion  *** KEY MILESTONE ***")

    out_dir = "5c_csv_conversion"
    if not os.path.isdir(out_dir):
        check("5c_csv_conversion/ exists", False)
        return

    suffix = _scenario_suffix()
    all_dirs = [
        d for d in os.listdir(out_dir)
        if d.startswith(f"{STATE}_") and SEASON in d
        and os.path.isdir(os.path.join(out_dir, d))
    ]
    matched = [d for d in all_dirs if _dir_matches_scenario(d)]

    # Filter out empty catch-all "unknown_circuit" dirs created by TX donor
    unknown = [d for d in matched if "unknown_circuit" in d]
    matched = [d for d in matched if "unknown_circuit" not in d]
    for u in unknown:
        print(f"  [WARN] Skipping empty catch-all dir: {u}")

    check(
        f"Output dirs ({SCENARIO}, {SEASON}): {len(matched)}",
        len(matched) > 0,
        f"Expected pattern: {STATE}_*_{SEASON}{suffix}/",
    )

    for d in matched:
        full = os.path.join(out_dir, d)
        csvs = sorted(f for f in os.listdir(full) if f.endswith(".csv"))
        check(f"  {d}: {len(csvs)} CSV files", len(csvs) > 0)

        if not csvs:
            continue

        # --- Sample BOTH commercial and residential CSVs ---------------
        com_csvs = [f for f in csvs if "commercial" in f.lower()]
        res_csvs = [f for f in csvs if "residential" in f.lower()]

        samples = []
        if com_csvs:
            samples.append(("commercial", com_csvs[0]))
        if res_csvs:
            samples.append(("residential", res_csvs[0]))
        if not samples:
            # Naming does not distinguish type — sample first + last
            samples.append(("first", csvs[0]))
            if len(csvs) > 1:
                samples.append(("last", csvs[-1]))

        for tag, csv_name in samples:
            fp = os.path.join(full, csv_name)
            df = pd.read_csv(fp, header=None)
            rows = len(df)
            check(
                f"    {tag} '{csv_name}': {rows} rows (expect 96)",
                rows == 96,
            )

    if matched:
        label = "BASELINE" if SCENARIO == "baseline" else SCENARIO.upper()
        print()
        print("  " + "*" * 54)
        print(f"  *  {label} CSV LOADSHAPES VERIFIED{' ' * (30 - len(label))}*")
        print("  " + "*" * 54)


# ═══════════════════════════════════════════════════════════════════════════
# Phase dispatch
# ═══════════════════════════════════════════════════════════════════════════

PHASES = {
    "pre": verify_pre,
    "1":   verify_phase1,
    "2":   verify_phase2,
    "3":   verify_phase3,
    "4":   verify_phase4,
    "5a":  verify_phase5a,
    "5b":  verify_phase5b,
    "5d":  verify_phase5d,
    "5c":  verify_phase5c,
}

PHASE_ORDER = ["pre", "1", "2", "3", "4", "5a", "5b", "5d", "5c"]

PHASE_NAMES = {
    "pre": "Registry + Scan + Pivot",
    "1":   "EULP Metadata",
    "2":   "Circuit Copy + Matching",
    "3":   "Tolerance Matching",
    "4":   "Building Selection",
    "5a":  "Parquet Downloads",
    "5b":  "Profile Scaling",
    "5d":  "Scenario Controls",
    "5c":  "CSV Conversion",
}


def _print_summary():
    """Print phase-by-phase summary table after --all."""
    if not _phase_results:
        return

    total_time = sum(r["time_s"] for r in _phase_results)
    total_pass = sum(r["passed"] for r in _phase_results)
    total_fail = sum(r["failed"] for r in _phase_results)

    col_phase = 24
    col_num = 8
    col_time = 10
    row_width = col_phase + col_num * 2 + col_time + 4

    print(f"\n{'='*row_width}")
    print("  SUMMARY")
    print(f"{'='*row_width}")
    header = (
        f"  {'Phase':<{col_phase}}"
        f"{'Passed':>{col_num}}"
        f"{'Failed':>{col_num}}"
        f"{'Time':>{col_time}}"
    )
    print(header)
    sep = (
        f"  {'-'*col_phase}"
        f"{'-'*col_num}"
        f"{'-'*col_num}"
        f"{'-'*col_time}"
    )
    print(sep)

    for r in _phase_results:
        status = "+" if r["failed"] == 0 else "X"
        label = f"[{status}] {r['phase']}: {PHASE_NAMES.get(r['phase'], '')}"
        print(
            f"  {label:<{col_phase}}"
            f"{r['passed']:>{col_num}}"
            f"{r['failed']:>{col_num}}"
            f"{r['time_s']:>{col_time - 1}.2f}s"
        )

    print(sep)
    print(
        f"  {'TOTAL':<{col_phase}}"
        f"{total_pass:>{col_num}}"
        f"{total_fail:>{col_num}}"
        f"{total_time:>{col_time - 1}.2f}s"
    )
    print(f"{'='*row_width}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global SCENARIO

    parser = argparse.ArgumentParser(
        description="Verify pipeline phases for dss-eulp-coupling",
    )
    parser.add_argument(
        "--phase", type=str, default=None,
        help="Phase to verify: " + ", ".join(PHASE_ORDER),
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run every phase check in order",
    )
    parser.add_argument(
        "--scenario", type=str, default="baseline",
        choices=["baseline", "dm", "uncontrolled"],
        help="Scenario to verify (default: baseline)",
    )
    args = parser.parse_args()

    SCENARIO = args.scenario

    print(f"\n  verify_fire_test.py")
    print(f"  Config: State={STATE}  Season={SEASON}  Scenario={SCENARIO}")
    print(f"  Parquet root: {PARQUET_ROOT}")

    t_total = time.perf_counter()

    if args.all:
        for p in PHASE_ORDER:
            _run_phase(p, PHASES[p])
        _print_summary()
    elif args.phase:
        key = args.phase.lower()
        if key not in PHASES:
            print(
                f"Unknown phase '{key}'. "
                f"Choose from: {', '.join(PHASE_ORDER)}"
            )
            sys.exit(1)
        _run_phase(key, PHASES[key])
    else:
        parser.print_help()
        sys.exit(0)

    elapsed_total = time.perf_counter() - t_total

    print(f"\n{'='*64}")
    print(f"  TOTAL: {_pass} passed, {_fail} failed  ({elapsed_total:.2f}s)")
    print(f"{'='*64}")

    sys.exit(1 if _fail > 0 else 0)


if __name__ == "__main__":
    main()
