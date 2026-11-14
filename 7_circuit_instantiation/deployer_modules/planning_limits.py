# -*- coding: utf-8 -*-
"""
planning_limits.py
------------------
The planning limits of a grown circuit (planning_limits in configs/growth.yaml), as
functions that need no OpenDSS. The Phase 7 deploy calls them, with growth on only,
after the final solve of the window. They report; nothing is built, replaced or moved.

- loading_monitor_lines: one Monitor per enabled Line (mode 0: voltages and currents,
  terminal 1) and per Transformer (mode 1, terminal 1, P and Q). The deploy solves
  inside Compile, so the values are read back from the Monitors (read_loading), as the
  load voltages are.
- line_rows, transformer_rows: every Line with its peak current over all steps against
  the normamps of its LineCode, every Transformer with its peak kVA against the kVA of
  its first winding.
- head_series, head_rating: the feeder-head kVA per step from the export of Monitor m2,
  and the rating of the head line, as Phase 8 computes them.
- voltage_rows, limit_rows: the rows of planning_limits.csv.
- block_rows: the block table with the lowest voltage at each block's customers and the
  highest loading on the lines from the source bus to its attach bus.
- substation_rating, substation_rows: the rating of the substation and the step-by-step
  sum of the head power of the case's circuits, for Phase 8.
"""

import math
import re

import numpy as np

from growth import _base, path_lines, read_feeder

# ASSUMPTION: a Line of 1 m or less is a switch, a fuse or a recloser and is left out of
# the line limit. SMART-DS writes those devices as lines of 1 m whose LineCode holds the
# device rating; a longer cut-off would also drop short conductor spans from the count
# of lines over their limit.
SHORT_LINE_M = 1.0

_I_RE = re.compile(r"^I(\d+)$")
_P_RE = re.compile(r"^P(\d+) \(kW\)$", re.IGNORECASE)
_Q_RE = re.compile(r"^Q(\d+) \(kvar\)$", re.IGNORECASE)
_S_RE = re.compile(r"^S(\d+) \(kVA\)$", re.IGNORECASE)
_ANG_RE = re.compile(r"^Ang(\d+)$", re.IGNORECASE)


def loading_monitor_lines(net):
    """(statements, line_monitors, transformer_monitors) for the network net
    (growth.read_feeder): New Monitor.ml_<n> on terminal 1 of every enabled Line, mode 0,
    and New Monitor.mx_<n> on terminal 1 of every Transformer, mode 1 with ppolar=no;
    the two dicts map monitor name to element name."""
    out, line_mon, tr_mon = [], {}, {}
    for n, ln in enumerate((ln for ln in net["lines"] if ln["enabled"]), start=1):
        line_mon[f"ml_{n}"] = ln["name"]
        out.append(f"New Monitor.ml_{n} element=Line.{ln['name']} terminal=1 mode=0\n")
    for n, tr in enumerate(net["transformers"], start=1):
        tr_mon[f"mx_{n}"] = tr["name"]
        out.append(f"New Monitor.mx_{n} element=Transformer.{tr['name']} terminal=1 mode=1 ppolar=no\n")
    return out, line_mon, tr_mon


def peak_current(header, channel):
    """(peak amps, step from 1) of a mode 0 Monitor: the largest of its current
    magnitude channels I1, I2, ... over all steps. channel(i) returns channel i, from 1."""
    cols = [i for i, h in enumerate((str(h).strip() for h in header), start=1) if _I_RE.match(h)]
    if not cols:
        raise ValueError(f"Monitor header has no current channels: {list(header)}")
    amps = np.max(np.abs(np.array([np.asarray(channel(i), dtype=float) for i in cols])), axis=0)
    return float(amps.max()), int(amps.argmax()) + 1


def peak_kva(header, channel):
    """(peak kVA, step from 1) of a mode 1 Monitor with P and Q channels: the largest
    magnitude of (sum of P, sum of Q) over all steps."""
    names = [str(h).strip() for h in header]
    p = [i for i, h in enumerate(names, start=1) if _P_RE.match(h)]
    q = [i for i, h in enumerate(names, start=1) if _Q_RE.match(h)]
    if not p or len(p) != len(q):
        raise ValueError(f"Monitor header has no P and Q channels: {names}")
    kva = np.hypot(sum(np.asarray(channel(i), dtype=float) for i in p),
                   sum(np.asarray(channel(i), dtype=float) for i in q))
    return float(kva.max()), int(kva.argmax()) + 1


def read_loading(circuit, line_monitors, transformer_monitors):
    """({line: (peak amps, step)}, {transformer: (peak kVA, step)}) read from the
    Monitors of a solved circuit (dss_engine's ActiveCircuit)."""
    lines, transformers = {}, {}
    mon = circuit.Monitors
    for name, element in line_monitors.items():
        mon.Name = name
        lines[element] = peak_current(list(mon.Header), mon.Channel)
    for name, element in transformer_monitors.items():
        mon.Name = name
        transformers[element] = peak_kva(list(mon.Header), mon.Channel)
    return lines, transformers


def step_date(step, dates):
    """The date (text) of step (from 1) in a run of 96 steps per date of dates; empty
    without a step."""
    return "" if step is None or step == "" else dates[(int(step) - 1) // 96]


def line_rows(net, peaks, dates, new_names=()):
    """One row per Line of net, in file order: line, bus1, bus2, phases, level (mv or
    lv), length_m, linecode, normamps, enabled, short (1 for a Line of SHORT_LINE_M or
    less: a switch, fuse or recloser, left out of the line limit), new (1 for an
    element added by load growth), peak_amps, peak_step, peak_date and loading_percent
    (peak amps over normamps). A disabled Line has no peak."""
    new_names = {n.lower() for n in new_names}
    rows = []
    for ln in net["lines"]:
        code = net["linecodes"].get(ln["linecode"]) or {}
        amps, step = peaks.get(ln["name"], (None, None))
        rating = code.get("normamps")
        rows.append({
            "line": ln["name"], "bus1": ln["b1"], "bus2": ln["b2"], "phases": ln["phases"],
            "level": "mv" if ln["b1"] in net["mv"] and ln["b2"] in net["mv"] else "lv",
            "length_m": ln["length_m"], "linecode": ln["linecode"], "normamps": rating,
            "enabled": int(ln["enabled"]), "short": int(ln["length_m"] <= SHORT_LINE_M),
            "new": int(ln["name"].lower() in new_names), "peak_amps": amps, "peak_step": step,
            "peak_date": step_date(step, dates),
            "loading_percent": 100.0 * amps / rating if amps is not None and rating else None})
    return rows


def transformer_rows(net, peaks, dates, new_names=()):
    """One row per Transformer of net, in file order: transformer, phases, bus (first
    winding), kva (first winding), new, peak_kva, peak_step, peak_date and
    loading_percent (peak kVA over kVA)."""
    new_names = {n.lower() for n in new_names}
    rows = []
    for tr in net["transformers"]:
        kva, step = peaks.get(tr["name"], (None, None))
        rating = tr["windings"][0][3] if tr["windings"] else None
        rows.append({
            "transformer": tr["name"], "phases": tr["phases"],
            "bus": tr["windings"][0][1] if tr["windings"] else "", "kva": rating,
            "new": int(tr["name"].lower() in new_names), "peak_kva": kva, "peak_step": step,
            "peak_date": step_date(step, dates),
            "loading_percent": 100.0 * kva / rating if kva is not None and rating else None})
    return rows


def head_series(frame):
    """The feeder-head kVA per step from the export of Monitor m2 (a DataFrame of its
    CSV), as Phase 8 computes S_3ph (kVA): per phase P = S x cos(Ang) and Q = S x
    sin(Ang), Ang in degrees; P and Q summed over the phases. Returns (kva, p, q)."""
    cols = {str(c).strip(): c for c in frame.columns}
    p = q = 0.0
    found = False
    for name in sorted(cols):
        m = _S_RE.match(name)
        if not m or f"Ang{m.group(1)}" not in cols:
            continue
        s = frame[cols[name]].astype(float).to_numpy()
        ang = np.deg2rad(frame[cols[f"Ang{m.group(1)}"]].astype(float).to_numpy())
        p, q, found = p + s * np.cos(ang), q + s * np.sin(ang), True
    if not found:
        raise ValueError(f"the m2 export has no S and Ang columns: {list(frame.columns)}")
    return np.sqrt(p ** 2 + q ** 2), p, q


def head_rating(net, master_text):
    """(kVA, line) of the feeder head, as Phase 8 computes feeder_head_kva: the normamps
    of the LineCode of the Line that Monitor m1 of Master.dss watches x the basekV of
    the circuit x sqrt(3). (None, line) when a piece is missing."""
    line = base_kv = None
    for raw in master_text.splitlines():
        st = raw.split("!", 1)[0].strip()
        m = re.search(r"(?i)\bnew\s+monitor\.m1\b.*\belement\s*=\s*line\.(\S+)", st)
        if m and line is None:
            line = m.group(1)
        m = re.search(r"(?i)\bnew\s+circuit\..*\bbasekv\s*=\s*(\S+)", st)
        if m and base_kv is None:
            base_kv = float(m.group(1))
    found = next((ln for ln in net["lines"] if line and ln["name"].lower() == line.lower()), None)
    code = net["linecodes"].get(found["linecode"]) if found else None
    if not code or code["normamps"] is None or base_kv is None:
        return None, line
    return code["normamps"] * base_kv * math.sqrt(3.0), line


def voltage_rows(frame, low, high, dates):
    """The three voltage rows of planning_limits.csv from the load voltage frame of the
    deploy (load, step, v_pu, ev_leg): voltage_band (customers with any step below low
    or above high; worst the lowest voltage), voltage_low and voltage_high. A customer
    is a load name without its _<n> leg suffix; EV legs are left out."""
    f = frame[~frame["ev_leg"].astype(bool)]
    customer = f["load"].map(_base)
    n = int(customer.nunique())
    below, above = f["v_pu"] < low, f["v_pu"] > high
    lo = f.loc[f["v_pu"].idxmin()] if len(f) else None
    hi = f.loc[f["v_pu"].idxmax()] if len(f) else None

    def row(limit, setting, mask, worst):
        return {"limit": limit, "setting": setting, "elements_checked": n,
                "elements_over": int(customer[mask].nunique()),
                "worst_element": "" if worst is None else worst["load"],
                "worst_value": None if worst is None else float(worst["v_pu"]),
                "worst_step": None if worst is None else int(worst["step"]),
                "worst_date": "" if worst is None else step_date(int(worst["step"]), dates)}

    return [row("voltage_band", f"{low} to {high} pu", below | above, lo),
            row("voltage_low", f"{low} pu", below, lo),
            row("voltage_high", f"{high} pu", above, hi)]


def limit_rows(lines, transformers, head_kva, head_rating_kva, head_line, limits, dates):
    """The line, head and transformer rows of planning_limits.csv. lines and
    transformers are the rows of line_rows and transformer_rows; a short or disabled
    Line and an element without a rating are not checked. head_kva is the feeder-head
    kVA per step. limits: planning_limits of growth.yaml. worst_value is a percent of
    the rating."""
    def worst_of(rows, key, limit):
        checked = [r for r in rows if r["loading_percent"] is not None]
        over = [r for r in checked if r["loading_percent"] > limit]
        top = max(checked, key=lambda r: r["loading_percent"], default=None)
        return {"elements_checked": len(checked), "elements_over": len(over),
                "worst_element": top[key] if top else "",
                "worst_value": top["loading_percent"] if top else None,
                "worst_step": top["peak_step"] if top else None,
                "worst_date": top["peak_date"] if top else ""}

    out = [{"limit": "line", "setting": f"{limits['line_limit_percent']} percent of normamps",
            **worst_of([r for r in lines if r["enabled"] and not r["short"]], "line", limits["line_limit_percent"])}]
    head = {"limit": "head", "setting": f"{limits['head_limit_percent']} percent of feeder_head_kva",
            "elements_checked": 0, "elements_over": 0, "worst_element": head_line or "", "worst_value": None,
            "worst_step": None, "worst_date": ""}
    if head_rating_kva:
        step = int(np.argmax(head_kva)) + 1
        percent = 100.0 * float(np.max(head_kva)) / head_rating_kva
        head.update({"elements_checked": 1, "elements_over": int(percent > limits["head_limit_percent"]),
                     "worst_value": percent, "worst_step": step, "worst_date": step_date(step, dates)})
    out.append(head)
    out.append({"limit": "transformer", "setting": f"{limits['transformer_limit_percent']} percent of kVA",
                **worst_of(transformers, "transformer", limits["transformer_limit_percent"])})
    return out


def block_rows(blocks, units, net, frame, line_table, low, high, line_limit):
    """The block rows of one feeder (growth_blocks.csv of phase growth) with, for each
    built block: v_pu_min and v_pu_max at its customers with the load of the lowest,
    path_worst_percent and path_worst_line (the highest loading on the lines from the
    source bus to its attach bus, short lines left out), voltage_outside and path_over
    (1 when outside the band or above line_limit). units: the plan's units of the
    feeder; frame: the load voltage frame; line_table: the rows of line_rows."""
    percent = {r["line"]: r["loading_percent"] for r in line_table if not r["short"]}
    loads_of = {u["unit"]: {ld["name"].lower() for ld in u["loads"]} for u in units}
    low_name = frame["load"].str.lower()
    out = []
    for blk in blocks:
        row = dict(blk)
        extra = {"v_pu_min": None, "v_pu_min_load": "", "v_pu_max": None, "path_worst_percent": None,
                 "path_worst_line": "", "voltage_outside": None, "path_over": None}
        if str(blk.get("built")) == "1":
            f = frame[low_name.isin(loads_of.get(blk["unit"], set()))]
            if len(f):
                lo = f.loc[f["v_pu"].idxmin()]
                extra.update({"v_pu_min": float(lo["v_pu"]), "v_pu_min_load": lo["load"],
                              "v_pu_max": float(f["v_pu"].max())})
                extra["voltage_outside"] = int(extra["v_pu_min"] < low or extra["v_pu_max"] > high)
            path = path_lines(net, net["source"], str(blk["attach_bus"]).lower()) or []
            rated = [(percent[ln["name"]], ln["name"]) for ln in path if percent.get(ln["name"]) is not None]
            if rated:
                extra["path_worst_percent"], extra["path_worst_line"] = max(rated)
                extra["path_over"] = int(extra["path_worst_percent"] > line_limit)
        out.append({**row, **extra})
    return out


def substation_rating(transformers_text):
    """The rating of the substation: the sum of the kVA (first winding) of the
    Transformers in the Transformers.dss of the topology's substation folder, the
    folder that holds the feeder folders. None when the text holds no Transformer with
    a kVA."""
    net = read_feeder({"transformers.dss": transformers_text, "master.dss": "New Circuit.x bus1=x"})
    kva = [tr["windings"][0][3] for tr in net["transformers"] if tr["windings"] and tr["windings"][0][3]]
    return float(sum(kva)) if kva else None


def substation_rows(mix_power, rating, limit):
    """One row per mix for substation_limits.csv. mix_power: {mix: [(circuit, p, q)]},
    p and q the head kW and kvar per step of each circuit of the case. The head power is
    summed step by step over the circuits (P and Q apart, by step number), then taken as
    kVA. Columns: scenario, circuits, rating_kva, limit_percent, peak_kva, peak_step,
    percent, over. Without a rating, rating_kva, percent and over stay empty."""
    rows = []
    for mix, parts in mix_power.items():
        n = min(len(p) for _, p, _ in parts)
        kva = np.hypot(sum(np.asarray(p[:n], dtype=float) for _, p, _ in parts),
                       sum(np.asarray(q[:n], dtype=float) for _, _, q in parts))
        peak = float(kva.max())
        rows.append({"scenario": mix, "circuits": len(parts), "rating_kva": rating, "limit_percent": limit,
                     "peak_kva": peak, "peak_step": int(kva.argmax()) + 1,
                     "percent": 100.0 * peak / rating if rating else None,
                     "over": int(100.0 * peak / rating > limit) if rating else None})
    return rows
