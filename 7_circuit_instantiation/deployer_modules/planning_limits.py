# -*- coding: utf-8 -*-
"""
planning_limits.py
------------------
The planning limits of a grown circuit (planning_limits in configs/growth.yaml), as
functions that need no OpenDSS. The Phase 7 deploy calls them, with growth on only,
after every solve of the window. They report; network growth (network_growth.py) reads
the same tables to decide what to build.

- loading_monitor_lines: one Monitor per enabled Line (mode 0: voltages and currents,
  terminal 1) and per Transformer (mode 1, terminal 1, P and Q). The deploy solves
  inside Compile, so the values are read back from the Monitors (read_loading), as the
  load voltages are.
- line_rows, transformer_rows: every Line with its peak current over all steps against
  the normamps of its LineCode, every Transformer with its peak kVA against the kVA of
  its first winding.
- head_lines, head_classes, head_series, head_rows: the heads of a circuit (the
  element, a Line or a regulator, Monitor m1 watches and the line of every Monitor
  h<k>m1), the head kVA per step from the export
  of a mode 1 Monitor as Phase 8 computes it, and one row per head with its loading by
  kVA and by largest phase current (heads.csv).
- read_phase_currents: the phase currents of every monitored line at given steps.
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


def read_phase_currents(circuit, line_monitors, steps):
    """{step: {line, lower case: [amps of each conductor of terminal 1]}} at the given
    steps (from 1), read from the mode 0 Monitors of a solved circuit."""
    out = {int(s): {} for s in steps}
    mon = circuit.Monitors
    for name, element in line_monitors.items():
        mon.Name = name
        cols = [i for i, h in enumerate((str(h).strip() for h in mon.Header), start=1) if _I_RE.match(h)]
        series = [np.abs(np.asarray(mon.Channel(i), dtype=float)) for i in cols]
        for s in out:
            out[s][element.lower()] = [float(a[s - 1]) for a in series]
    return out


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


def _heads(master_text):
    """{k: (class, element name)} of the Monitors m1 and h<k>m1 of Master.dss on a Line
    or a Transformer; class is line or transformer."""
    out = {}
    for raw in master_text.splitlines():
        st = raw.split("!", 1)[0]
        m = re.search(r"(?i)\bnew\s+monitor\.(m1|h(\d+)m1)\b.*\belement\s*=\s*(line|transformer)\.(\S+)", st)
        if m:
            out.setdefault(int(m.group(2)) if m.group(2) else 1, (m.group(3).lower(), m.group(4)))
    return out


def head_lines(master_text):
    """[(k, element name)] of the heads of a circuit, by head number: the element
    Monitor m1 of Master.dss watches is head 1, the element Monitor h<k>m1 watches is
    head k, a Line or a Transformer (head_classes tells which). A head is the first
    element of a path from the source bus: the line or the regulator of m1, every
    express line of a new feeder and every second circuit of such a line
    (network_growth.py)."""
    return sorted((k, name) for k, (_, name) in _heads(master_text).items())


def head_classes(master_text):
    """{k: line or transformer}: the class of the element of each head of head_lines.
    A Line and a Transformer of one name are told apart only here."""
    return {k: cls for k, (cls, _) in _heads(master_text).items()}


def head_rows(net, heads, exports, dates):
    """One row per head for heads.csv. heads: head_lines; exports: {k: (frame of the
    export of its mode 0 Monitor, frame of the export of its mode 1 Monitor)}. Columns:
    head, line, linecode, normamps, rating_kva (normamps x the circuit's base kV x
    sqrt(3), as Phase 8 computes feeder_head_kva), peak_kva, kva_percent, kva_step,
    kva_date, peak_phase_amps (the largest phase current over all steps), phase_percent
    (over normamps), phase_step, phase_date, and amps_1, amps_2, amps_3, the current of
    each phase node at that step. A head without a rated LineCode or a base kV keeps its
    peaks and has no percent.
    A head on a Transformer (a regulator): line is its name, linecode empty, rating_kva the kVA of its first winding, normamps
    that kVA / (sqrt(3) x the kV of its first winding) for three phases and empty for
    any other phase count, and the phase currents are the first p current channels of
    the export for p phases (the channel of the neutral conductor left out)."""
    rows = []
    for k, name in heads:
        ln = next((x for x in net["lines"] if x["name"].lower() == name.lower()), None)
        tr = None if ln else next((x for x in net["transformers"] if x["name"].lower() == name.lower()), None)
        code = net["linecodes"].get(ln["linecode"]) if ln else None
        normamps = code["normamps"] if code else None
        rating = normamps * net["base_kv"] * math.sqrt(3.0) if normamps is not None and net["base_kv"] else None
        if tr is not None and tr["windings"]:
            _, _, kv, rating = tr["windings"][0]
            normamps = rating / (math.sqrt(3.0) * kv) if tr["phases"] == 3 and rating and kv else None
        m1, m2 = exports[k]
        kva = head_series(m2)[0]
        peak_kva, kva_step = float(np.max(kva)), int(np.argmax(kva)) + 1
        cols = [c for c in m1.columns if _I_RE.match(str(c).strip())]
        if tr is not None:
            cols = cols[:tr["phases"]]
        amps = np.abs(m1[cols].astype(float).to_numpy()).T
        top = amps.max(axis=0)
        peak_amps, amp_step = float(top.max()), int(top.argmax()) + 1
        spec = ln["bus1"] if ln else (tr["windings"][0][0] if tr is not None and tr["windings"] else None)
        nodes = [int(n) for n in str(spec).split(".")[1:] if n.isdigit() and int(n) != 0] if spec else []
        nodes = nodes or list(range(1, len(cols) + 1))
        at = {node: float(amps[i][amp_step - 1]) for i, node in enumerate(nodes[:len(cols)])}
        rows.append({
            "head": k, "line": name, "linecode": ln["linecode"] if ln else "", "normamps": normamps,
            "rating_kva": rating, "peak_kva": peak_kva,
            "kva_percent": 100.0 * peak_kva / rating if rating else None, "kva_step": kva_step,
            "kva_date": step_date(kva_step, dates), "peak_phase_amps": peak_amps,
            "phase_percent": 100.0 * peak_amps / normamps if normamps else None, "phase_step": amp_step,
            "phase_date": step_date(amp_step, dates), "amps_1": at.get(1), "amps_2": at.get(2),
            "amps_3": at.get(3)})
    return rows


def head_totals(m1_frames, m2_frames):
    """The circuit totals of several heads, as two frames with the columns of the first
    head's Monitor exports. Mode 1 (m2_frames: S and Ang per phase): per phase P = the
    sum of S x cos(Ang) and Q = the sum of S x sin(Ang) over the heads, written back as
    S and Ang in degrees. Mode 0 (m1_frames: V, VAngle, I and IAngle per phase): per
    phase the currents of the heads added as phasors; the voltages are those of the
    first head, since every head starts at the source bus."""
    def total(frames, magnitude, angle):
        out = frames[0].copy()
        cols = {str(c).strip(): c for c in out.columns}
        for name in sorted(cols):
            m = magnitude.match(name)
            ang = cols.get(f"{angle}{m.group(1)}") if m else None
            if ang is None:
                continue
            re_part = im_part = 0.0
            for f in frames:
                rad = np.deg2rad(f[ang].astype(float).to_numpy())
                re_part = re_part + f[cols[name]].astype(float).to_numpy() * np.cos(rad)
                im_part = im_part + f[cols[name]].astype(float).to_numpy() * np.sin(rad)
            out[cols[name]] = np.hypot(re_part, im_part)
            out[ang] = np.degrees(np.arctan2(im_part, re_part))
        return out

    return total(m1_frames, _I_RE, "IAngle"), total(m2_frames, _S_RE, "Ang")


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


def limit_rows(lines, transformers, heads, limits, dates):
    """The line, head, head_phase and transformer rows of planning_limits.csv. lines and
    transformers are the rows of line_rows and transformer_rows; a short or disabled
    Line and an element without a rating are not checked. heads are the rows of
    head_rows: the row head tests each head's peak kVA over its rating, the row
    head_phase its largest phase current over the normamps of its LineCode, both against
    head_limit_percent; with several heads both count the heads and give the worst.
    limits: planning_limits of growth.yaml. worst_value is a percent of the rating."""
    def worst_of(rows, key, limit):
        checked = [r for r in rows if r["loading_percent"] is not None]
        over = [r for r in checked if r["loading_percent"] > limit]
        top = max(checked, key=lambda r: r["loading_percent"], default=None)
        return {"elements_checked": len(checked), "elements_over": len(over),
                "worst_element": top[key] if top else "",
                "worst_value": top["loading_percent"] if top else None,
                "worst_step": top["peak_step"] if top else None,
                "worst_date": top["peak_date"] if top else ""}

    def head_row(limit, setting, percent, step, date):
        row = {"limit": limit, "setting": setting, "elements_checked": 0, "elements_over": 0,
               "worst_element": heads[0]["line"] if heads else "", "worst_value": None, "worst_step": None,
               "worst_date": ""}
        checked = [h for h in heads if h[percent] is not None]
        if checked:
            top = max(checked, key=lambda h: h[percent])
            row.update({"elements_checked": len(checked),
                        "elements_over": sum(1 for h in checked if h[percent] > limits["head_limit_percent"]),
                        "worst_element": top["line"], "worst_value": top[percent], "worst_step": top[step],
                        "worst_date": top[date]})
        return row

    return [{"limit": "line", "setting": f"{limits['line_limit_percent']} percent of normamps",
             **worst_of([r for r in lines if r["enabled"] and not r["short"]], "line", limits["line_limit_percent"])},
            head_row("head", f"{limits['head_limit_percent']} percent of feeder_head_kva", "kva_percent",
                     "kva_step", "kva_date"),
            head_row("head_phase", f"{limits['head_limit_percent']} percent of normamps, largest phase",
                     "phase_percent", "phase_step", "phase_date"),
            {"limit": "transformer", "setting": f"{limits['transformer_limit_percent']} percent of kVA",
             **worst_of(transformers, "transformer", limits["transformer_limit_percent"])}]


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


def substation_rows(mix_power, rating, limit, windows=None):
    """One row per mix for substation_limits.csv. mix_power: {mix: [(circuit, p, q)]},
    p and q the head kW and kvar per step of each circuit of the case. The head power is
    summed step by step over the circuits (P and Q apart, by step number), then taken as
    kVA. Columns: scenario, circuits, rating_kva, limit_percent, peak_kva, peak_step,
    percent, over. Without a rating, rating_kva, percent and over stay empty.
    windows, when given: {mix: [the dates of each circuit's window, in the order of
    mix_power]}; it adds coincident (1 when every circuit of the mix has the same window
    dates, else 0: the sum then adds step i of windows on different dates) and windows
    (the first date of each circuit's window, joined by ;)."""
    rows = []
    for mix, parts in mix_power.items():
        n = min(len(p) for _, p, _ in parts)
        kva = np.hypot(sum(np.asarray(p[:n], dtype=float) for _, p, _ in parts),
                       sum(np.asarray(q[:n], dtype=float) for _, _, q in parts))
        peak = float(kva.max())
        row = {"scenario": mix, "circuits": len(parts), "rating_kva": rating, "limit_percent": limit,
               "peak_kva": peak, "peak_step": int(kva.argmax()) + 1,
               "percent": 100.0 * peak / rating if rating else None,
               "over": int(100.0 * peak / rating > limit) if rating else None}
        if windows is not None:
            dates = [list(d) for d in windows[mix]]
            row["coincident"] = int(all(d == dates[0] for d in dates))
            row["windows"] = ";".join(d[0] if d else "" for d in dates)
        rows.append(row)
    return rows
