# -*- coding: utf-8 -*-
"""
Created on Tue Nov 11 20:35:25 2025

@author: luisfernando
"""

#!/usr/bin/env python3
# Aggregate m1/m2 CSVs and add (a) timestep column and (b) one time-independent
# summary row per circuit with counts from .dss and substation transformer kVA.
# Procedural / minimal functions approach.

import re
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# ---------- small helpers kept inline ----------
def _dephase(bus_name: str) -> str:
    # Remove phase suffixes like ".1.2.3" and parentheses, quotes
    b = bus_name.strip().strip('"').strip("'")
    b = re.split(r"[.\(]", b, maxsplit=1)[0]
    return b.lower()

# Folder pattern: e.g. uhs18_1247_circuit_54_1  -> (uhs18) (circuit_54) (1)
FOLDER_RE = re.compile(r"^(uhs\d+)_\d+_(circuit_\d+)_(\d+)$", re.IGNORECASE)

# Name hints to classify EV elements in DSS (adjust if your naming differs)
EV_HINTS = ("ev", "evse", "pev")

# --- NEW: m1/m2 detection + size threshold config ---
# Require each circuit to have at least one m1 CSV and one m2 CSV > 1 KiB.
SIZE_THRESHOLD_BYTES = 1024  # set to 1000 if you prefer decimal kB

# Token-aware matchers so we don't match "m12" as "m1"
M1_RE = re.compile(r"(?<![0-9A-Za-z])m1(?![0-9A-Za-z])", re.IGNORECASE)
M2_RE = re.compile(r"(?<![0-9A-Za-z])m2(?![0-9A-Za-z])", re.IGNORECASE)

if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent

    # Accumulators
    m1_frames = []
    m2_frames = []
    summary_rows = []
    problems = []

    matched = 0

    for circuit_dir in sorted(ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not circuit_dir.is_dir():
            continue
        m = FOLDER_RE.match(circuit_dir.name)
        if not m:
            continue  # not a circuit folder
        matched += 1

        substation = m.group(1)     # e.g., 'uhs18'
        feeder = m.group(2)         # e.g., 'circuit_54'
        scenario = m.group(3)       # e.g., '1'

        mcd = circuit_dir / "ModifiedCircuitData"
        if not mcd.is_dir():
            problems.append(f"{circuit_dir.name}  # Missing ModifiedCircuitData")
            continue

        # ---- Validate and locate required m1/m2 CSVs (> 1 KiB) ----
        csvs = [p for p in mcd.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]
        if not csvs:
            problems.append(f"{circuit_dir.name}  # No CSV files found in ModifiedCircuitData")
            continue

        m1_candidates = [p for p in csvs if M1_RE.search(p.name)]
        m2_candidates = [p for p in csvs if M2_RE.search(p.name)]

        if not m1_candidates:
            problems.append(f"{circuit_dir.name}  # No m1 CSV found")
            continue
        if not m2_candidates:
            problems.append(f"{circuit_dir.name}  # No m2 CSV found")
            continue

        m1_big = [p for p in m1_candidates if p.stat().st_size > SIZE_THRESHOLD_BYTES]
        m2_big = [p for p in m2_candidates if p.stat().st_size > SIZE_THRESHOLD_BYTES]

        if not m1_big:
            sizes = ", ".join(f"{p.name}={p.stat().st_size}B" for p in m1_candidates)
            problems.append(f"{circuit_dir.name}  # m1 CSV(s) present but none > {SIZE_THRESHOLD_BYTES} bytes ({sizes})")
            continue
        if not m2_big:
            sizes = ", ".join(f"{p.name}={p.stat().st_size}B" for p in m2_candidates)
            problems.append(f"{circuit_dir.name}  # m2 CSV(s) present but none > {SIZE_THRESHOLD_BYTES} bytes ({sizes})")
            continue

        # Choose the largest qualifying m1/m2 file if multiple qualify
        m1_path = max(m1_big, key=lambda p: p.stat().st_size)
        m2_path = max(m2_big, key=lambda p: p.stat().st_size)

        # ---- Parse DSS files for counts + substation transformer kVA ----
        dss_files = list(mcd.rglob("*.dss"))

        load_names = set()
        storage_names = set()
        pv_names = set()
        ev_names = set()

        source_buses = set()
        line_edges = set()  # undirected edges via Lines (store both directions)
        transformers = []   # list of dicts: {'buses': set([...]), 'kva': float or None}

        for dss in dss_files:
            try:
                text = dss.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = dss.read_text(errors="ignore")

            for raw in text.splitlines():
                # strip comments (// or !) and whitespace
                core = re.split(r"//|!", raw)[0].strip()
                if not core:
                    continue
                line = core.lower()

                # Count loads / storage / PV / EVs (heuristic for EV names)
                mload = re.search(r"\bnew\s+load\.([^\s=]+)", line)
                if mload:
                    nm = mload.group(1)
                    load_names.add(nm)
                    if any(h in nm for h in EV_HINTS) or any(h in line for h in EV_HINTS):
                        ev_names.add(nm)

                msto = re.search(r"\bnew\s+storage\.([^\s=]+)", line)
                if msto:
                    nm = msto.group(1)
                    storage_names.add(nm)
                    if any(h in nm for h in EV_HINTS) or any(h in line for h in EV_HINTS):
                        ev_names.add(nm)

                mpv = re.search(r"\bnew\s+pvsystem\.([^\s=]+)", line)
                if mpv:
                    pv_names.add(mpv.group(1))

                # Vsource: grab substation/source bus
                if "new vsource." in line:
                    mb1 = re.search(r"\bbus1\s*=\s*([^\s\[\],]+)", line)
                    if mb1:
                        source_buses.add(_dephase(mb1.group(1)))

                # Lines: build graph neighbors of source bus
                if "new line." in line:
                    b1 = re.search(r"\bbus1\s*=\s*([^\s\[\],]+)", line)
                    b2 = re.search(r"\bbus2\s*=\s*([^\s\[\],]+)", line)
                    if b1 and b2:
                        bb1 = _dephase(b1.group(1))
                        bb2 = _dephase(b2.group(1))
                        line_edges.add((bb1, bb2))
                        line_edges.add((bb2, bb1))

                # Transformer: collect buses + kVA
                if "new transformer." in line:
                    t_buses = set()
                    mbuses = re.search(r"\bbuses\s*=\s*\[([^\]]+)\]", line)
                    if mbuses:
                        inside = mbuses.group(1)
                        for tok in re.split(r"[,\s]+", inside.strip()):
                            if tok:
                                t_buses.add(_dephase(tok))
                    else:
                        # Try bus / bus1 / bus2 tokens
                        for key in ("bus1", "bus2", "bus"):
                            # NOTE: rf-string is correct; avoid 'rfr"' typo.
                            mkey = re.search(rf"\b{key}\s*=\s*([^\s\[\],]+)", line)
                            if mkey:
                                t_buses.add(_dephase(mkey.group(1)))

                    kva_val = None
                    mkva = re.search(r"\bkva\s*=\s*([\d\.eE\+\-]+)", line)
                    if mkva:
                        try:
                            kva_val = float(mkva.group(1))
                        except Exception:
                            pass
                    if kva_val is None:
                        mkvas = re.search(r"\bkvas\s*=\s*\[([^\]]+)\]", line)
                        if mkvas:
                            nums = [s for s in re.split(r"[,\s]+", mkvas.group(1).strip()) if s]
                            if nums:
                                try:
                                    kva_val = float(nums[0])
                                except Exception:
                                    pass

                    transformers.append({"buses": t_buses, "kva": kva_val})

        n_loads = len(load_names)
        n_storage = len(storage_names)
        n_pv = len(pv_names)
        n_evs = len(ev_names)

        # Heuristic: pick transformer connected to Vsource bus or one-hop neighbor via Lines
        xfmr_kva = None
        if source_buses:
            src = next(iter(source_buses))
            neighbors = {src}
            for a, b in line_edges:
                if a == src:
                    neighbors.add(b)

            # Prefer transformer that directly touches the source bus
            chosen = None
            for t in transformers:
                if src in t["buses"]:
                    chosen = t
                    break
            if chosen is None:
                for t in transformers:
                    if t["buses"] & neighbors:
                        chosen = t
                        break
            if chosen is None and transformers:
                # Fallback: largest kVA transformer if nothing matched
                cand = [t["kva"] for t in transformers if t["kva"] is not None]
                if cand:
                    xfmr_kva = max(cand)
            else:
                xfmr_kva = chosen["kva"] if chosen else None
        elif transformers:
            cand = [t["kva"] for t in transformers if t["kva"] is not None]
            xfmr_kva = max(cand) if cand else None

        # Record a clean, time-independent summary row for this circuit
        summary_rows.append({
            "circuit_folder": circuit_dir.name,
            "substation": substation,
            "feeder": feeder,
            "scenario": scenario,
            "n_loads": n_loads,
            "n_evs": n_evs,
            "n_storage": n_storage,
            "n_pv": n_pv,
            "substation_xfmr_kva": xfmr_kva
        })

        # ---- Load and annotate m1/m2 CSVs, add timestep + summary row ----
        try:
            df_m1 = pd.read_csv(m1_path)
            df_m2 = pd.read_csv(m2_path)

            # Add identifiers
            for df in (df_m1, df_m2):
                df["circuit_folder"] = circuit_dir.name
                df["substation"] = substation
                df["feeder"] = feeder
                df["scenario"] = scenario

            # Add timestep per circuit file (1..N)
            df_m1["timestep"] = range(1, len(df_m1) + 1)
            df_m2["timestep"] = range(1, len(df_m2) + 1)

            # === Add per-phase P/Q and 3φ totals from S & Ang (degrees) ===
            def add_pq_totals(df: pd.DataFrame) -> pd.DataFrame:
                # Handle headers with leading spaces by mapping "clean" -> actual col name
                name_map = {c.strip(): c for c in df.columns}

                def get_col(clean_key):
                    return name_map.get(clean_key)

                # Expected inputs per phase (robust to leading spaces in S headers)
                s_cols = [get_col("S1 (kVA)"), get_col("S2 (kVA)"), get_col("S3 (kVA)")]
                a_cols = [get_col("Ang1"),      get_col("Ang2"),      get_col("Ang3")     ]

                p_cols, q_cols = [], []
                for i, (scol, acol) in enumerate(zip(s_cols, a_cols), start=1):
                    if scol is None or acol is None:
                        continue  # skip phase if either S or Ang is missing
                    S = pd.to_numeric(df[scol], errors="coerce")
                    ang_rad = np.deg2rad(pd.to_numeric(df[acol], errors="coerce"))  # degrees → radians

                    p_name = f"P{i} (kW)"
                    q_name = f"Q{i} (kVAr)"
                    df[p_name] = S * np.cos(ang_rad)
                    df[q_name] = S * np.sin(ang_rad)
                    p_cols.append(p_name)
                    q_cols.append(q_name)

                # 3φ totals (vector sum via P/Q components)
                if p_cols:
                    df["P_3ph (kW)"] = sum((df[c] for c in p_cols), start=0)
                    df["Q_3ph (kVAr)"] = sum((df[c] for c in q_cols), start=0)
                    df["S_3ph (kVA)"] = np.sqrt(df["P_3ph (kW)"]**2 + df["Q_3ph (kVAr)"]**2)

                    # (Optional) also store S1+S2+S3 for comparison
                    s_present = [c for c in s_cols if c is not None]
                    if s_present:
                        df["S_sum_3ph (kVA)"] = sum((pd.to_numeric(df[c], errors="coerce") for c in s_present), start=0)

                # (Optional) reorder so each phase block is S, Ang, P, Q (keeps your other cols intact)
                desired = []
                for i, (scol, acol) in enumerate(zip(s_cols, a_cols), start=1):
                    if scol is None or acol is None:
                        continue
                    desired.extend([scol, acol, f"P{i} (kW)", f"Q{i} (kVAr)"])

                totals = ["P_3ph (kW)", "Q_3ph (kVAr)", "S_3ph (kVA)"]
                if "S_sum_3ph (kVA)" in df.columns:
                    totals.append("S_sum_3ph (kVA)")

                tail = [c for c in df.columns if c not in (desired + totals)]
                df = df.reindex(columns=desired + totals + tail)
                return df
            
            df_m1 = add_pq_totals(df_m1)
            df_m2 = add_pq_totals(df_m2)

            # Try to place 'timestep' next to a time column ('hour', 'time', 'Time', 't(sec)')
            def insert_timestep_next_to(df):
                cols = list(df.columns)
                candidates = [c for c in ["hour", "time", "Time", "t(sec)", " t(sec)"] if c in cols]
                if candidates:
                    key = candidates[0]
                    idx = cols.index(key)
                    # move 'timestep' right after the time column
                    cols = [c for c in cols if c != "timestep"]
                    cols.insert(idx + 1, "timestep")
                    df = df.reindex(columns=cols)
                return df

            df_m1 = insert_timestep_next_to(df_m1)
            df_m2 = insert_timestep_next_to(df_m2)

            # Append one time-independent summary row to each df (flag via row_type='summary')
            summary_base = {
                "circuit_folder": circuit_dir.name,
                "substation": substation,
                "feeder": feeder,
                "scenario": scenario,
                "n_loads": n_loads,
                "n_evs": n_evs,
                "n_storage": n_storage,
                "n_pv": n_pv,
                "substation_xfmr_kva": xfmr_kva,
                "row_type": "summary",
                "timestep": 0,  # clearly outside real time series
            }
            df_m1["row_type"] = "data"
            df_m2["row_type"] = "data"

            df_m1 = pd.concat([df_m1, pd.DataFrame([summary_base])], ignore_index=True)
            df_m2 = pd.concat([df_m2, pd.DataFrame([summary_base])], ignore_index=True)

            m1_frames.append(df_m1)
            m2_frames.append(df_m2)

        except Exception as e:
            problems.append(f"{circuit_dir.name}  # CSV read/annotate error: {e}")
            continue

    # ----- Write outputs -----
    out_m1 = ROOT / "aggregate_m1.csv"
    out_m2 = ROOT / "aggregate_m2.csv"
    out_summary = ROOT / "circuit_summary.csv"
    out_problems = ROOT / "problem_circuits.txt"

    if m1_frames:
        pd.concat(m1_frames, ignore_index=True).to_csv(out_m1, index=False)
    if m2_frames:
        pd.concat(m2_frames, ignore_index=True).to_csv(out_m2, index=False)
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(out_summary, index=False)
    if problems:
        out_problems.write_text("\n".join(problems) + "\n", encoding="utf-8")

    # ----- Console summary + exit code -----
    print(f"Matched circuit folders: {matched}")
    if summary_rows:
        print(f"Summary rows written: {len(summary_rows)} -> {out_summary.name}")
    if m1_frames:
        print(f"Aggregated m1  -> {out_m1.name}")
    if m2_frames:
        print(f"Aggregated m2  -> {out_m2.name}")
    if problems:
        print(f"Some folders had issues: {len(problems)} (see {out_problems.name})")
        sys.exit(1)
    else:
        print("All matching circuits processed successfully.")
        sys.exit(0)
