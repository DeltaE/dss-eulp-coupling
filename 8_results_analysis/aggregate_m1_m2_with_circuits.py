# -*- coding: utf-8 -*-
"""
Created on Tue Nov 11 20:35:25 2025

@author: luisfernando
"""

#!/usr/bin/env python3
# Aggregate m1/m2 CSVs and add (a) timestep column and (b) one time-independent
# summary row per circuit with counts from .dss and feeder head thermal kVA.
# Procedural / minimal functions approach.
# With horizon_days above 1 (pipeline_config.yaml) the Phase 7 deploy writes
# <circuit>/window_days.csv, and the m1/m2 files hold 96 steps per day of the window.
# Each data row then also gets date, day_index and day_type after timestep, and the
# summary rows and circuit_summary.csv get day_x_first_step and day_x_last_step, the
# steps of the simulated peak day. Without that file (horizon_days 1) nothing is added.
# With load growth on (growth_years above 0 in growth.yaml) the deploy writes
# ModifiedCircuitData/planning_limits.csv. The summary rows and circuit_summary.csv then
# also get growth_years, limit_<limit>_over and limit_<limit>_worst for each row of that
# file (voltage_band, voltage_low, voltage_high, line, head, transformer), and
# substation_percent and substation_over, and n_loads_new, n_evs_new, n_storage_new and
# n_pv_new beside n_loads, n_evs, n_storage and n_pv: the elements of each count whose
# customer is a new customer of the run (new_counts); substation_limits.csv gets one row per mix: the
# head power of the case's circuits summed step by step against the sum of the kVA of the
# transformers in the topology's substation folder (the folder that holds the feeder
# folders), with coincident (1 when every circuit of the mix has the same window dates) and
# windows (the first date of each circuit's window), and the substation units as records
# (units_existing, unit_kva, units_in_all, units_added; network_growth.substation_units).
# With growth off nothing is added.
# With network growth on (network_growth.mode other than "off" in growth.yaml) the deploy
# may add heads to a circuit (a new feeder, a second circuit of a head line), each with
# Monitors h<k>m1 and h<k>m2. feeder_head_kva is then the sum of the ratings of the heads (the
# kVA of the first winding of each head on a regulator, the rating of each head on a line) and
# the data rows of aggregate_m1.csv and aggregate_m2.csv hold the sum over the heads
# (planning_limits.head_totals), so every reader of the data rows sees the whole circuit; one
# extra set of rows per head carries row_type head and the head's number in the column head.
# The exports of every head on a transformer lose the channels of its neutral before the sum,
# so the data rows and the head rows have the columns of a line head.
# The summary rows and circuit_summary.csv get heads and network_growth_rounds, and this
# script writes network_growth_summary.csv (one row per circuit folder: what was built, as
# quantities) and network_growth_built.yaml (the items of every circuit folder, in the format
# network_growth.carry_forward reads). The ModifiedCircuitData/round_<round>/ folders the
# deploy keeps are left out of every count.

import json
import os
import re
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import STEPS_PER_DAY, WINDOW_DAYS_FILE, resolve_work_path
from pipeline_utils import growth_on, growth_settings, load_config, load_growth, resolve_config_path
from pipeline_utils import network_growth_on

def _read_dss_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return path.read_text(errors="ignore")

def _strip_dss_comment(raw: str) -> str:
    return re.split(r"//|!", raw)[0].strip()

def _iter_dss_commands(text: str):
    current = ""
    for raw in text.splitlines():
        core = _strip_dss_comment(raw)
        if not core:
            continue
        if core.lstrip().startswith("~"):
            current = f"{current} {core.lstrip()[1:].strip()}".strip()
        else:
            if current:
                yield current
            current = core
    if current:
        yield current

def _dss_value(command: str, key: str):
    m = re.search(rf"\b{re.escape(key)}\s*=\s*(\"[^\"]+\"|'[^']+'|[^\s]+)", command, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")

def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _find_dss_file(dss_files, name: str):
    matches = [p for p in dss_files if p.name.lower() == name.lower()]
    if not matches:
        return None
    return min(matches, key=lambda p: len(str(p)))

def _feeder_head_kva(dss_files):
    """The rating of the feeder head: normamps of the LineCode of the Line that Monitor m1
    watches x base kV x sqrt(3). With more heads (the Lines of Monitors h<k>m1, network
    growth), the sum of the ratings of the heads. When Monitor m1 watches a Transformer (a
    regulator head, smartds_repairs.py), the kVA of its first winding (_head_transformer),
    plus the rating of every further head h<k>m1 of network growth: the kVA of the first
    winding of a Transformer (a copy of the head regulator) as Transformers.dss writes it,
    the rating of a Line as above, and 0.0 for a head without a rating."""
    master_path = _find_dss_file(dss_files, "Master.dss")
    lines_path = _find_dss_file(dss_files, "Lines.dss")
    linecodes_path = _find_dss_file(dss_files, "LineCodes.dss")
    if not (master_path and lines_path and linecodes_path):
        return None
    head_transformer = _head_transformer(dss_files)

    monitor_line_name = None
    more_heads = []
    further = []  # (monitor, element) of every Monitor h<k>m1, as Master.dss writes them
    base_kv = None
    for command in _iter_dss_commands(_read_dss_text(master_path)):
        if re.search(r"\bnew\s+monitor\.m1\b", command, re.IGNORECASE):
            element = _dss_value(command, "element")
            if element and element.lower().startswith("line."):
                monitor_line_name = element.split(".", 1)[1]
        more = re.search(r"\bnew\s+monitor\.(h\d+m1)\b", command, re.IGNORECASE)
        if more:
            element = _dss_value(command, "element")
            if element and element.lower().startswith("line."):
                more_heads.append(element.split(".", 1)[1])
            further.append((more.group(1), element or ""))
        if re.search(r"\bnew\s+circuit\.", command, re.IGNORECASE):
            base_kv = _float_or_none(_dss_value(command, "basekv"))
    if head_transformer is not None:
        if head_transformer["kva"] is None or not further:
            return head_transformer["kva"]

        def further_kva(monitor, element):
            if element.lower().startswith("transformer."):
                return _head_transformer(dss_files, monitor)["kva"] or 0.0
            if element.lower().startswith("line.") and base_kv is not None:
                return _head_line_kva(element.split(".", 1)[1], base_kv, lines_path, linecodes_path) or 0.0
            return 0.0
        return head_transformer["kva"] + sum(further_kva(monitor, element) for monitor, element in further)
    if not (monitor_line_name and base_kv is not None):
        return None
    first = _head_line_kva(monitor_line_name, base_kv, lines_path, linecodes_path)
    if first is None or not more_heads:
        return first
    return first + sum(_head_line_kva(name, base_kv, lines_path, linecodes_path) or 0.0 for name in more_heads)

def _head_line_kva(monitor_line_name, base_kv, lines_path, linecodes_path):
    linecode_name = None
    for command in _iter_dss_commands(_read_dss_text(lines_path)):
        m = re.search(r"\bnew\s+line\.([^\s]+)", command, re.IGNORECASE)
        if not m or m.group(1).lower() != monitor_line_name.lower():
            continue
        linecode_name = _dss_value(command, "linecode")
        break
    if not linecode_name:
        return None

    normamps = None
    for command in _iter_dss_commands(_read_dss_text(linecodes_path)):
        m = re.search(r"\bnew\s+linecode\.([^\s]+)", command, re.IGNORECASE)
        if not m or m.group(1).lower() != linecode_name.lower():
            continue
        normamps = _float_or_none(_dss_value(command, "normamps"))
        break
    if normamps is None:
        return None

    return normamps * base_kv * np.sqrt(3.0)

def _head_transformer(dss_files, monitor="m1"):
    """{"name", "phases", "kva"} of the Transformer that Monitor m1 of Master.dss watches
    (or the Monitor named monitor, h<k>m1 for head k of network growth),
    from its New Transformer statement in Transformers.dss: phases as written (None when
    the statement does not set it) and kva, the kVA of its first winding (the first value
    of kvas=, or kva= of winding 1); None when that Monitor watches no Transformer."""
    master_path = _find_dss_file(dss_files, "Master.dss")
    transformers_path = _find_dss_file(dss_files, "Transformers.dss")
    name = None
    for command in _iter_dss_commands(_read_dss_text(master_path)) if master_path else []:
        if re.search(rf"\bnew\s+monitor\.{re.escape(monitor)}\b", command, re.IGNORECASE):
            element = _dss_value(command, "element")
            if element and element.lower().startswith("transformer."):
                name = element.split(".", 1)[1]
    if name is None:
        return None
    head = {"name": name, "phases": None, "kva": None}
    for command in _iter_dss_commands(_read_dss_text(transformers_path)) if transformers_path else []:
        m = re.search(r"\bnew\s+transformer\.([^\s]+)\s*(.*)$", command, re.IGNORECASE)
        if not m or m.group(1).lower() != name.lower():
            continue
        winding = 1
        for key, value in re.findall(r"([A-Za-z%][\w%]*)\s*=\s*(\([^\)]*\)|\[[^\]]*\]|\"[^\"]*\"|'[^']*'|[^\s]+)",
                                     m.group(2)):
            key = key.lower()
            if key == "phases":
                head["phases"] = int(value)
            elif key == "wdg":
                winding = int(value)
            elif key == "kvas" and head["kva"] is None:
                head["kva"] = _float_or_none(re.split(r"[\s,]+", value.strip("()[]\"' "))[0])
            elif key == "kva" and winding == 1 and head["kva"] is None:
                head["kva"] = _float_or_none(value)
        break
    return head

def _drop_neutral_channels(df, phases):
    """df without the channels of conductor phases + 1, the grounded neutral of a head on a
    transformer of that many phases: V, VAngle, I and IAngle of a mode 0 export, S (kVA)
    and Ang of a mode 1 export. The columns are then those of a line head."""
    k = phases + 1
    neutral = {f"V{k}", f"VAngle{k}", f"I{k}", f"IAngle{k}", f"S{k} (kVA)", f"Ang{k}"}
    return df.drop(columns=[c for c in df.columns if c.strip() in neutral])

# Folder pattern: <substation>_circuit_<id>_<scenario>
FOLDER_RE = re.compile(r"^(.+)_(circuit_\d+)_(.+)$", re.IGNORECASE)

# Name hints to classify EV elements in DSS (adjust if your naming differs)
EV_HINTS = ("ev", "evse", "pev")

# --- NEW: m1/m2 detection + size threshold config ---
# Require each circuit to have at least one m1 CSV and one m2 CSV > 1 KiB.
SIZE_THRESHOLD_BYTES = 1024  # set to 1000 if you prefer decimal kB

# Token-aware matchers so we don't match "m12" as "m1"
M1_RE = re.compile(r"(?<![0-9A-Za-z])m1(?![0-9A-Za-z])", re.IGNORECASE)
M2_RE = re.compile(r"(?<![0-9A-Za-z])m2(?![0-9A-Za-z])", re.IGNORECASE)


def count_names(dss_files):
    """The element names, lower case, that the counts n_loads, n_storage, n_pv and n_evs
    count in the .dss files dss_files, as (loads, storage, pv, evs): every New Load but the
    battery standby Loads standby_storage_<unit>, every New Storage and New PVSystem, and
    as EVs the Loads and Storage whose name or statement holds a name hint of EV_HINTS."""
    load_names = set()
    storage_names = set()
    pv_names = set()
    ev_names = set()

    for dss in dss_files:
        text = _read_dss_text(dss)

        for raw in text.splitlines():
            # strip comments (// or !) and whitespace
            core = _strip_dss_comment(raw)
            if not core:
                continue
            line = core.lower()

            # Count loads / storage / PV / EVs (heuristic for EV names)
            mload = re.search(r"\bnew\s+load\.([^\s=]+)", line)
            if mload and not mload.group(1).startswith("standby_storage_"):
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
    return load_names, storage_names, pv_names, ev_names


_LEG_RE = re.compile(r"_[0-9]+$")
_EV_WORK_RE = re.compile(r"^ev([uc])_w(\d+)_")
_EV_HOME_RE = re.compile(r"^ev[uc]_(.+)_[12]$")
_DER_RE = re.compile(r"^(storage|pv)_(.+)$")


def element_customer(name, der_bases, car_hosts):
    """The customer, a load base name in lower case, of the element name (lower case) of
    count_names, mapped through the records the Phase 7 deploy writes and else by its
    naming rule:
    - storage_<base> and pv_<base>, with the leg suffix _1 or _2 when the host has legs:
      the host base of der_hosts.csv (der_bases), else the name without prefix and suffix;
    - EVu_w<i>_<office>_<leg> (EVc_w<i>_), the loads of a work car at its office: the home
      host of car EVu_<i> (EVc_<i>), car_hosts {(u or c, i): host} from
      EVControl/ev_cars.csv; None when the car is not there;
    - EVu_<host>_<leg> (EVc_), the loads of a car at home: host;
    - any other load, <base>_<n> or <base>: base, the deploy's base name (the name
      without its _<n> suffix, as peak_kw_for_load takes it)."""
    m = _DER_RE.match(name)
    if m:
        return m.group(2) if m.group(2) in der_bases else _LEG_RE.sub("", m.group(2))
    m = _EV_WORK_RE.match(name)
    if m:
        return car_hosts.get((m.group(1), int(m.group(2))))
    m = _EV_HOME_RE.match(name)
    if m:
        return m.group(1)
    return _LEG_RE.sub("", name)


def new_counts(names, new_customers, der_bases, car_hosts):
    """{n_loads_new, n_evs_new, n_storage_new, n_pv_new}: of names, the (loads, storage, pv,
    evs) of count_names, the elements whose customer (element_customer) is in
    new_customers (growth.new_customers of scenario_assignments.json, lower case)."""
    loads, storage, pv, evs = names

    def count(group):
        return sum(1 for nm in group if element_customer(nm, der_bases, car_hosts) in new_customers)

    return {"n_loads_new": count(loads), "n_evs_new": count(evs), "n_storage_new": count(storage),
            "n_pv_new": count(pv)}


def customer_records(circuit_dir):
    """(new_customers, der_bases, car_hosts) of a circuit folder, all lower case:
    growth.new_customers of scenario_assignments.json; the host bases of
    ModifiedCircuitData/der_hosts.csv (empty when absent); {(u or c, i): home host} of the
    cars of EVControl/ev_cars.csv, else of the deploy's host lists (ev_loads_uncontrolled
    and ev_loads_controlled of scenario_assignments.json, then those of its growth key)."""
    with open(circuit_dir / "scenario_assignments.json", encoding="utf-8") as f:
        assign = json.load(f)
    grown = assign.get("growth") or {}
    new_customers = {str(c).lower() for c in grown.get("new_customers", [])}
    der_path = circuit_dir / "ModifiedCircuitData" / "der_hosts.csv"
    der_bases = set(pd.read_csv(der_path, dtype=str)["base"].str.lower()) if der_path.is_file() else set()
    cars_path = circuit_dir / "EVControl" / "ev_cars.csv"
    car_hosts = {}
    if cars_path.is_file():
        cars = pd.read_csv(cars_path, dtype=str, keep_default_na=False)
        for car, host in zip(cars["car"], cars["host"]):
            m = re.match(r"(?i)^ev([uc])_(\d+)$", car)
            if m:
                car_hosts[(m.group(1).lower(), int(m.group(2)))] = host.lower()
    else:
        for group, key in (("u", "ev_loads_uncontrolled"), ("c", "ev_loads_controlled")):
            hosts = list(assign.get(key) or []) + list(grown.get(key) or [])
            car_hosts.update({(group, i): str(h).lower() for i, h in enumerate(hosts)})
    return new_customers, der_bases, car_hosts


if __name__ == "__main__":
    ROOT = Path(resolve_work_path("7_circuit_instantiation"))
    # Load growth (growth.yaml): with growth on, the planning limits of every circuit
    GROWTH = growth_settings(load_growth())
    NETWORK_GROWTH = network_growth_on(GROWTH)  # the tables and totals of network growth
    growth_summary_rows, growth_built_items = [], []
    mix_power = {}  # {mix: [(circuit folder, head kW per step, head kvar per step)]}
    mix_windows = {}  # {mix: [the dates of each circuit's window]}, in the order of mix_power
    if growth_on(GROWTH):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '7_circuit_instantiation'))
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '7_circuit_instantiation',
                                        'deployer_modules'))
        import planning_limits
        import network_growth

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

        substation = m.group(1)
        feeder = m.group(2)
        scenario = m.group(3)

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

        # ---- Parse DSS files for counts + feeder head thermal capacity ----
        dss_files = [p for p in mcd.rglob("*.dss") if not p.relative_to(mcd).parts[0].startswith("round_")]

        load_names, storage_names, pv_names, ev_names = count_names(dss_files)

        n_loads = len(load_names)
        n_storage = len(storage_names)
        n_pv = len(pv_names)
        n_evs = len(ev_names)
        # Load growth: how many of each count belong to the new customers of the run
        counts_new = {}
        if growth_on(GROWTH):
            if not (circuit_dir / "scenario_assignments.json").is_file():
                problems.append(f"{circuit_dir.name}  # No scenario_assignments.json (growth_years "
                                f"{GROWTH['growth_years']})")
                continue
            counts_new = new_counts((load_names, storage_names, pv_names, ev_names),
                                    *customer_records(circuit_dir))
        feeder_head_kva = _feeder_head_kva(dss_files)

        # The window of a horizon of more than one day (written by the Phase 7 deploy)
        window_days = None
        day_x_steps = {}
        if (circuit_dir / WINDOW_DAYS_FILE).is_file():
            window_days = pd.read_csv(circuit_dir / WINDOW_DAYS_FILE, dtype=str, keep_default_na=False)
            x_index = int(window_days.loc[window_days["day_x"] == "1", "day_index"].iloc[0])
            day_x_steps = {"day_x_first_step": (x_index - 1) * STEPS_PER_DAY + 1,
                           "day_x_last_step": x_index * STEPS_PER_DAY}
        if growth_on(GROWTH):
            # Load growth: the planning limits the deploy reported for this circuit
            limits_path = mcd / "planning_limits.csv"
            if not limits_path.is_file():
                problems.append(f"{circuit_dir.name}  # No planning_limits.csv (growth_years "
                                f"{GROWTH['growth_years']})")
                continue
            day_x_steps = dict(day_x_steps, growth_years=GROWTH["growth_years"])
            limits_frame = pd.read_csv(limits_path)
            for _, limit_row in limits_frame.iterrows():
                day_x_steps[f"limit_{limit_row['limit']}_over"] = limit_row["elements_over"]
                day_x_steps[f"limit_{limit_row['limit']}_worst"] = limit_row["worst_value"]
            # The dates of the circuit's window: window_days.csv, or with one day the date
            # of the planning limits (every step of a one-day run is on day X)
            if window_days is not None:
                circuit_dates = list(window_days["date"])
            else:
                circuit_dates = [d for d in limits_frame["worst_date"].dropna().astype(str) if d][:1]
        heads = [(1, "")]
        if NETWORK_GROWTH:
            # Network growth: the heads of the circuit and what the deploy built in it
            rounds_path = mcd / "network_growth_rounds.csv"
            if not (rounds_path.is_file() and (mcd / "network_growth.csv").is_file()
                    and (mcd / network_growth.BUILT_FILE).is_file()):
                problems.append(f"{circuit_dir.name}  # No network growth tables (network_growth.mode "
                                f"{GROWTH['network_growth']['mode']})")
                continue
            heads = planning_limits.head_lines(_read_dss_text(_find_dss_file(dss_files, "Master.dss")))
            rounds_frame = pd.read_csv(rounds_path, dtype=str, keep_default_na=False)
            built_frame = pd.read_csv(mcd / "network_growth.csv")
            used = rounds_frame[rounds_frame["round"].str.isdigit() & (rounds_frame["round"] != "0")
                                & (rounds_frame["converged"] == "1")]
            day_x_steps = dict(day_x_steps, heads=len(heads), network_growth_rounds=len(used))
            growth_built_items.extend(network_growth.read_built(mcd / network_growth.BUILT_FILE))

            def by_value(frame, amount):
                """<value of now>:<sum of amount>, one per value, joined by ;"""
                sums = {}
                for value, x in zip(frame["now"], amount):
                    sums[str(value)] = sums.get(str(value), 0.0) + float(x)
                return ";".join(f"{value}:{format(sums[value], '.6g')}" for value in sorted(sums))

            by_step = {step: built_frame[built_frame["step"] == step] for step in network_growth.ITEM_STEPS}
            feeders_new, lines_built = by_step["new_feeder"], by_step["reconductor"]
            trs_built, regs, moved = by_step["service_transformer"], by_step["regulator"], by_step["rebalance_phases"]
            recoded = lines_built[lines_built["was"].astype(str).str.lower() != lines_built["now"].astype(str).str.lower()]
            added_km = (lines_built["count"] - lines_built["count_before"]) * lines_built["length_m"] / 1000.0
            replaced = trs_built[trs_built["was"].astype(float) != trs_built["now"].astype(float)] \
                if len(trs_built) else trs_built
            growth_summary_rows.append({
                "circuit_folder": circuit_dir.name, "substation": substation, "feeder": feeder, "scenario": scenario,
                "rounds": len(used), "planned_items": int((built_frame["round"].astype(str) == "planned").sum()),
                "items": len(built_frame), "heads": len(heads),
                "new_feeders": len(feeders_new), "express_km": feeders_new["length_m"].sum() / 1000.0,
                "express_km_by_code": by_value(feeders_new, feeders_new["length_m"] / 1000.0),
                "rebuilt_km": (recoded["count_before"] * recoded["length_m"]).sum() / 1000.0,
                "rebuilt_km_by_code": by_value(recoded, recoded["count_before"] * recoded["length_m"] / 1000.0),
                "second_circuit_km": added_km.sum(),
                "second_circuit_km_by_code": by_value(lines_built[added_km > 0], added_km[added_km > 0]),
                "transformers_replaced": int(replaced["count_before"].sum()),
                "transformers_replaced_by_kva": by_value(replaced, replaced["count_before"]),
                "parallel_units": int((trs_built["count"] - trs_built["count_before"]).sum()),
                "parallel_units_by_kva": by_value(trs_built[trs_built["count"] > trs_built["count_before"]],
                                                  (trs_built["count"] - trs_built["count_before"])[
                                                      trs_built["count"] > trs_built["count_before"]]),
                "regulators": len(regs), "regulator_units": int(regs["count"].sum()),
                "regulator_kva": (regs["count"] * regs["kva"]).sum(),
                "laterals_moved": len(moved), "laterals_moved_km": moved["length_m"].sum() / 1000.0,
                "limits_over": ";".join(f"{r['limit']}:{r['elements_over']}" for _, r in limits_frame.iterrows()
                                        if r["limit"] != "voltage_band" and r["elements_over"] > 0),
                "regulators_replaced": len(by_step["regulator_rating"])})

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
            **counts_new,
            "feeder_head_kva": feeder_head_kva,
            **day_x_steps
        })

        # ---- Load and annotate m1/m2 CSVs, add timestep + summary row ----
        try:
            df_m1 = pd.read_csv(m1_path)
            df_m2 = pd.read_csv(m2_path)
            head_transformer = _head_transformer(dss_files)
            if head_transformer is not None and head_transformer["phases"] is not None:
                # A head on a transformer: its neutral's channels are left out
                df_m1 = _drop_neutral_channels(df_m1, head_transformer["phases"])
                df_m2 = _drop_neutral_channels(df_m2, head_transformer["phases"])
            head_raw = {}
            if len(heads) > 1:
                # Network growth: the data rows hold the sum over the heads
                prefix = m1_path.name[:m1_path.name.lower().rindex("_mon_m1")]
                for head_k, _ in heads:
                    mon = "" if head_k == 1 else f"h{head_k}"
                    head_raw[head_k] = (pd.read_csv(mcd / f"{prefix}_Mon_{mon}m1_1.csv"),
                                        pd.read_csv(mcd / f"{prefix}_Mon_{mon}m2_1.csv"))
                    head_tr = _head_transformer(dss_files, f"{mon}m1")
                    if head_tr is not None and head_tr["phases"] is not None:
                        # A head on a transformer: its neutral's channels are left out
                        head_raw[head_k] = tuple(_drop_neutral_channels(df, head_tr["phases"])
                                                 for df in head_raw[head_k])
                df_m1, df_m2 = planning_limits.head_totals([pair[0] for pair in head_raw.values()],
                                                           [pair[1] for pair in head_raw.values()])

            # Add identifiers
            for df in (df_m1, df_m2):
                df["circuit_folder"] = circuit_dir.name
                df["substation"] = substation
                df["feeder"] = feeder
                df["scenario"] = scenario

            # Add timestep per circuit file (1..N)
            df_m1["timestep"] = range(1, len(df_m1) + 1)
            df_m2["timestep"] = range(1, len(df_m2) + 1)
            if window_days is not None:
                for df in (df_m1, df_m2):
                    if len(df) != STEPS_PER_DAY * len(window_days):
                        raise ValueError(f"{len(df)} steps for a window of {len(window_days)} days")
                    day = (df["timestep"] - 1) // STEPS_PER_DAY
                    df["date"] = window_days["date"].to_numpy()[day]
                    df["day_index"] = window_days["day_index"].astype(int).to_numpy()[day]
                    df["day_type"] = window_days["day_type"].to_numpy()[day]

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
            if growth_on(GROWTH):
                mix_power.setdefault(scenario, []).append(
                    (circuit_dir.name, df_m2["P_3ph (kW)"].to_numpy(), df_m2["Q_3ph (kVAr)"].to_numpy()))
                mix_windows.setdefault(scenario, []).append(circuit_dates)

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
                    if window_days is not None:
                        cols = [c for c in cols if c not in ("date", "day_index", "day_type")]
                        cols[idx + 2:idx + 2] = ["date", "day_index", "day_type"]
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
                **counts_new,
                "feeder_head_kva": feeder_head_kva,
                "row_type": "summary",
                "timestep": 0,  # clearly outside real time series
                **day_x_steps,
            }
            df_m1["row_type"] = "data"
            df_m2["row_type"] = "data"

            df_m1 = pd.concat([df_m1, pd.DataFrame([summary_base])], ignore_index=True)
            df_m2 = pd.concat([df_m2, pd.DataFrame([summary_base])], ignore_index=True)
            # Network growth: with several heads, one extra set of rows per head (row_type head)
            for head_k, pair in head_raw.items():
                head_frames = []
                for df in pair:
                    df["circuit_folder"] = circuit_dir.name
                    df["substation"] = substation
                    df["feeder"] = feeder
                    df["scenario"] = scenario
                    df["timestep"] = range(1, len(df) + 1)
                    if window_days is not None:
                        day = (df["timestep"] - 1) // STEPS_PER_DAY
                        df["date"] = window_days["date"].to_numpy()[day]
                        df["day_index"] = window_days["day_index"].astype(int).to_numpy()[day]
                        df["day_type"] = window_days["day_type"].to_numpy()[day]
                    df = insert_timestep_next_to(add_pq_totals(df))
                    df["row_type"] = "head"
                    df["head"] = head_k
                    head_frames.append(df)
                df_m1 = pd.concat([df_m1, head_frames[0]], ignore_index=True)
                df_m2 = pd.concat([df_m2, head_frames[1]], ignore_index=True)

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

    if growth_on(GROWTH) and mix_power:
        # The substation: the kVA of the transformers in the folder that holds the feeder folders
        substation_dir = resolve_config_path(load_config()["smart_ds_root"])
        tr_path = next((p for p in substation_dir.iterdir() if p.name.lower() == "transformers.dss"), None) \
            if substation_dir.is_dir() else None
        rating = planning_limits.substation_rating(_read_dss_text(tr_path)) if tr_path else None
        if rating is None:
            print(f"Substation rating not found in {substation_dir}: rating and percent left empty.")
        sub_rows = planning_limits.substation_rows(mix_power, rating,
                                                   GROWTH["planning_limits"]["substation_limit_percent"],
                                                   mix_windows)
        # Substation units, as records: the power flow is unchanged
        sub_record = network_growth.substation_record({"transformers.dss": _read_dss_text(tr_path) if tr_path else ""})
        for row in sub_rows:
            row.update(network_growth.substation_units(sub_record, row["peak_kva"], row["over"],
                                                       GROWTH["network_growth"]["sizing_percent"], NETWORK_GROWTH))
        pd.DataFrame(sub_rows).to_csv(ROOT / "substation_limits.csv", index=False)
        by_mix = {r["scenario"]: r for r in sub_rows}
        for row in summary_rows:
            row["substation_percent"] = by_mix[row["scenario"]]["percent"]
            row["substation_over"] = by_mix[row["scenario"]]["over"]
        for frame in m1_frames + m2_frames:
            is_summary = frame["row_type"] == "summary"
            mix = frame.loc[is_summary, "scenario"].iloc[0]
            frame.loc[is_summary, "substation_percent"] = by_mix[mix]["percent"]
            frame.loc[is_summary, "substation_over"] = by_mix[mix]["over"]

    if m1_frames:
        pd.concat(m1_frames, ignore_index=True).to_csv(out_m1, index=False)
    if m2_frames:
        pd.concat(m2_frames, ignore_index=True).to_csv(out_m2, index=False)
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(out_summary, index=False)
    if NETWORK_GROWTH and growth_summary_rows:
        pd.DataFrame(growth_summary_rows).to_csv(ROOT / "network_growth_summary.csv", index=False)
        network_growth.write_built(ROOT / network_growth.BUILT_FILE, growth_built_items)
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
