# -*- coding: utf-8 -*-
"""
ev_control.py
-------------
The rules of ev_control (pipeline_config.yaml) that shape the charging of controlled
EVs in the Phase 7 deploy. Each car is one row of kW over the 96 fifteen-minute
intervals of the day (its session row).

- place_car(row, curve) and valley_fill(rows, curve): valley filling, after Gan, Topcu
  and Low (2013), "Optimal decentralized protocol for electric vehicle charging", IEEE
  Transactions on Power Systems, https://doi.org/10.1109/TPWRS.2012.2210288.
- valley_fill_curves(rows, curves, car_curves, feeder): valley filling where each car
  fills its own curve (its service transformer, or the feeder).
- monitor_p_kw(header, channels): real power per step of a mode=1 Monitor.
- read_dss_elements(texts), service_transformers(texts, load_buses): the service
  transformer of each load.
- cheap_intervals(rate, month) and offpeak_start(rows, cheap, nominal_kw): a start
  timer at the cheap period of a URDB time-of-use rate.
"""
import re

import numpy as np

N_INTERVALS = 96


def place_car(row, curve):
    """Return the controlled row of one car: its daily energy (row sum) split evenly
    over as many intervals as the row has non-zero intervals, placed on the intervals
    where curve is lowest. Equal curve values go to the earlier interval. An all-zero
    row stays zero.

    ASSUMPTION: controlled cars are placed one at a time in host order, each into the
    intervals where the load it sees is lowest, keeping its daily energy and its number
    of charging intervals; an iterative or optimal schedule would spread later cars
    differently."""
    row = np.asarray(row, dtype=float)
    out = np.zeros(row.size)
    k = np.count_nonzero(row)
    if k == 0:
        return out
    chosen = np.argsort(np.asarray(curve, dtype=float), kind="stable")[:k]
    out[chosen] = row.sum() / k
    return out


def valley_fill(rows, curve):
    """Place every row of rows, in order, on curve (place_car), adding each placed car
    to the curve before the next. Returns (controlled rows, curve after every car)."""
    rows = np.asarray(rows, dtype=float)
    combined = np.asarray(curve, dtype=float).copy()
    out = np.zeros_like(rows)
    for j in range(rows.shape[0]):
        out[j, :] = place_car(rows[j, :], combined)
        combined += out[j, :]
    return out, combined


def valley_fill_curves(rows, curves, car_curves, feeder):
    """Place every row of rows, in order, on its own curve: curves[car_curves[j]].
    Each placed car is added to its own curve and to curves[feeder], because every car
    loads the feeder head. Returns (controlled rows, {name: curve after every car})."""
    rows = np.asarray(rows, dtype=float)
    combined = {name: np.asarray(c, dtype=float).copy() for name, c in curves.items()}
    out = np.zeros_like(rows)
    for j in range(rows.shape[0]):
        name = car_curves[j]
        out[j, :] = place_car(rows[j, :], combined[name])
        combined[name] += out[j, :]
        if name != feeder:
            combined[feeder] += out[j, :]
    return out, combined


_S_RE = re.compile(r"^S(\d+)\s*\(kVA\)$", re.IGNORECASE)
_ANG_RE = re.compile(r"^Ang(\d+)$", re.IGNORECASE)
_P_RE = re.compile(r"^P(\d+)\s*\(kW\)$", re.IGNORECASE)


def monitor_p_kw(header, channel):
    """Real power (kW) per step of a mode=1 Monitor, summed over its phases. header is
    the Monitor's channel names (Monitors.Header); channel(i) returns channel i
    (1-based, Monitors.Channel). Polar channels (S1 (kVA), Ang1, ...) give
    P = sum of S x cos(angle in degrees); rectangular channels give the sum of the
    P1 (kW), P2 (kW), ... channels. Raises ValueError if the header has neither."""
    names = [str(h).strip() for h in header]
    s_cols, ang_cols, p_cols = {}, {}, {}
    for i, h in enumerate(names, start=1):
        for regex, cols in ((_S_RE, s_cols), (_ANG_RE, ang_cols), (_P_RE, p_cols)):
            m = regex.match(h)
            if m:
                cols[int(m.group(1))] = i
    if s_cols and set(s_cols) == set(ang_cols):
        total = None
        for ph in sorted(s_cols):
            s = np.asarray(channel(s_cols[ph]), dtype=float)
            ang = np.asarray(channel(ang_cols[ph]), dtype=float)
            p = s * np.cos(np.radians(ang))
            total = p if total is None else total + p
        return total
    if p_cols:
        return sum(np.asarray(channel(p_cols[ph]), dtype=float) for ph in sorted(p_cols))
    raise ValueError(f"Monitor header has no power channels: {names}")


def _bus(name):
    return str(name).strip().strip("\"'").split(".")[0].lower()


def _logical_lines(text):
    """The New ... statements of a .dss text, with ~ continuation lines joined and
    ! comments removed."""
    out = []
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("~") and out:
            out[-1] += " " + line[1:].strip()
        else:
            out.append(line)
    return out


_PROP_RE = re.compile(r"([A-Za-z%][\w%]*)\s*=\s*(\[[^\]]*\]|\([^\)]*\)|\"[^\"]*\"|'[^']*'|\S+)")


def _array(value):
    return [v for v in re.split(r"[\s,]+", value.strip("[]()\"' ")) if v]


def read_dss_elements(texts):
    """Read the Line and Transformer elements of the .dss texts. Returns (line_buses,
    transformers): a list of (bus1, bus2) pairs, and {transformer name: list of
    (bus, kV) per winding}. Bus names are lower case without node suffixes."""
    line_buses, transformers = [], {}
    for text in texts:
        for st in _logical_lines(text):
            m = re.match(r"(?i)^new\s+(line|transformer)\.(\S+)\s*(.*)$", st)
            if not m:
                continue
            kind, name, rest = m.group(1).lower(), m.group(2), m.group(3)
            props = [(k.lower(), v) for k, v in _PROP_RE.findall(rest)]
            if kind == "line":
                d = dict(props)
                if "bus1" in d and "bus2" in d:
                    line_buses.append((_bus(d["bus1"]), _bus(d["bus2"])))
                continue
            wdg, buses, kvs = 1, {}, {}
            for k, v in props:
                if k == "wdg":
                    wdg = int(v)
                elif k == "bus":
                    buses[wdg] = _bus(v)
                elif k == "kv":
                    kvs[wdg] = float(v)
                elif k == "buses":
                    buses.update({i: _bus(b) for i, b in enumerate(_array(v), start=1)})
                elif k == "kvs":
                    kvs.update({i: float(x) for i, x in enumerate(_array(v), start=1)})
            transformers[name] = [(buses.get(i), kvs.get(i)) for i in sorted(set(buses) | set(kvs))]
    return line_buses, transformers


def secondary_bus(windings):
    """The bus of the last winding when its kV is lower than the first winding's kV,
    else None (equal kV: a regulator)."""
    if len(windings) < 2:
        return None
    (_, kv_first), (bus_last, kv_last) = windings[0], windings[-1]
    if kv_first is None or kv_last is None or bus_last is None:
        return None
    return bus_last if kv_last < kv_first else None


def service_transformers(texts, load_buses):
    """Map each load to its service transformer.

    1. An undirected graph of the buses joined by Line elements of texts.
    2. A transformer's secondary bus: secondary_bus of its windings.
    3. A load's service transformer is the one transformer whose secondary bus lies in
       the graph component of the load's bus; with none or several, the load has none.

    load_buses: {load name: bus1}. Returns (mapping, status): mapping {load: transformer
    name or None}, status {load: "one", "none" or "several"}."""
    line_buses, transformers = read_dss_elements(texts)
    parent = {}

    def find(b):
        parent.setdefault(b, b)
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]
        return b

    for a, b in line_buses:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    by_component = {}
    for name in sorted(transformers):
        sec = secondary_bus(transformers[name])
        if sec is not None:
            by_component.setdefault(find(sec), []).append(name)
    mapping, status = {}, {}
    for load, bus in load_buses.items():
        found = by_component.get(find(_bus(bus)), []) if bus else []
        mapping[load] = found[0] if len(found) == 1 else None
        status[load] = "one" if len(found) == 1 else ("none" if not found else "several")
    return mapping, status


def first_tier_price(tiers):
    """rate plus adj (when present) of the first tier of one period, in USD/kWh."""
    t = tiers[0]
    return float(t.get("rate", 0.0)) + float(t.get("adj", 0.0) or 0.0)


def cheap_intervals(rate, month):
    """Return (cheap period, sorted cheap intervals) of a URDB rate record for month
    (1 to 12). The schedule is energyweekdayschedule[month - 1], because the EV session
    curve is the weekday curve. The cheap period is the period of that row with the
    lowest first-tier price (equal prices go to the lower period number). Cheap
    intervals are the 15-minute intervals i (0 to 95) whose hour i // 4 is in it."""
    row = [int(p) for p in rate["energyweekdayschedule"][month - 1]]
    structure = rate["energyratestructure"]
    period = min(sorted(set(row)), key=lambda p: (first_tier_price(structure[p]), p))
    return period, [i for i in range(N_INTERVALS) if row[i // 4] == period]


def offpeak_row(row, cheap, nominal_kw):
    """Return (controlled row, start interval or None) of one car under offpeak_start.

    The start is the first cheap interval at or after the car's first charging interval
    in its session row, searching forward and wrapping from the last interval to the
    first. The car charges at nominal_kw in consecutive intervals from the start,
    wrapping past the last interval, until its daily energy (row sum, kW-intervals) is
    delivered; the last interval takes the remainder. An all-zero row stays zero.
    Raises ValueError if the energy needs more than every interval of the day."""
    row = np.asarray(row, dtype=float)
    n = row.size
    out = np.zeros(n)
    nz = np.flatnonzero(row)
    if nz.size == 0:
        return out, None
    cheap_set = set(int(i) for i in cheap)
    start = next(((nz[0] + k) % n for k in range(n) if (nz[0] + k) % n in cheap_set), None)
    if start is None:
        raise ValueError("No cheap interval in the day.")
    energy = row.sum()
    n_full = int(energy // nominal_kw)
    remainder = energy - n_full * nominal_kw
    if n_full + (1 if remainder > 0 else 0) > n:
        raise ValueError(f"Daily energy {energy} kW-intervals exceeds {n} intervals at {nominal_kw} kW.")
    for k in range(n_full):
        out[(start + k) % n] = nominal_kw
    if remainder > 0:
        out[(start + n_full) % n] = remainder
    return out, int(start)


def offpeak_start(rows, cheap, nominal_kw):
    """offpeak_row for every row. Returns (controlled rows, list of start intervals)."""
    rows = np.asarray(rows, dtype=float)
    out = np.zeros_like(rows)
    starts = []
    for j in range(rows.shape[0]):
        out[j, :], s = offpeak_row(rows[j, :], cheap, nominal_kw)
        starts.append(s)
    return out, starts
