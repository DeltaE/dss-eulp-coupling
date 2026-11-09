# -*- coding: utf-8 -*-
"""
ev_control.py
-------------
The rules of ev_control (pipeline_config.yaml) that shape the charging of controlled
EVs in the Phase 7 deploy. Each car is one row of kW over the 96 fifteen-minute
intervals of the day (its session row).

- place_car(row, curve, window) and valley_fill(rows, curve, windows, order): valley
  filling, after Gan, Topcu and Low (2013), "Optimal decentralized protocol for electric
  vehicle charging", IEEE Transactions on Power Systems,
  https://doi.org/10.1109/TPWRS.2012.2210288.
- valley_fill_curves(rows, curves, car_curves, feeder, windows, order): valley filling
  where each car fills its own curve (its service transformer, or the feeder).
- water_fill(rows, curve, powers, windows, order): each car's power varies from 0 to its
  limit in each interval, filling the lowest intervals toward one level.
- plugin_order(plug_minutes): the order of placement, by plug-in time from 04:00.
- forecast_cv(w, model, coefficients) and forecast_curve(curve, model, coefficients, z):
  the aggregator's forecast of a curve, with an hourly normal error.
- monitor_p_kw(header, channels): real power per step of a mode=1 Monitor.
- read_dss_elements(texts), service_transformers(texts, load_buses): the service
  transformer of each load.
- cheap_intervals(rate, month), start_offsets(rows, cheap, windows, z, sigma_min) and
  offpeak_start(rows, cheap, nominal_kw, windows, shifts): a start timer at the cheap
  period of a URDB time-of-use rate, with starts spread around it.
A window is the list of intervals a car is plugged in at home, in plug order (ev_cars.py);
None means every interval of the day.
"""
import re

import numpy as np

N_INTERVALS = 96


def place_car(row, curve, window=None):
    """Return the controlled row of one car: its daily energy (row sum) split evenly
    over as many intervals as the row has non-zero intervals (k), placed on the
    intervals where curve is lowest. Equal curve values go to the earlier interval. An
    all-zero row stays zero. With a window, the candidates are the window's intervals
    in ascending order and the k with the lowest curve are chosen; with fewer than k
    candidates all of them are chosen, each still getting row sum / k, and the rest of
    the energy is left over.

    ASSUMPTION: controlled cars are placed one at a time in order of plug-in time, the
    day running from 04:00 as the NHTS travel day, each into the intervals where the
    forecast load it sees is lowest, keeping its daily energy and its number of charging
    intervals; an aggregator that knows only the cars already plugged in places them in
    that order, and an iterative or optimal schedule would spread later cars
    differently."""
    row = np.asarray(row, dtype=float)
    out = np.zeros(row.size)
    k = np.count_nonzero(row)
    if k == 0:
        return out
    if window is None:
        chosen = np.argsort(np.asarray(curve, dtype=float), kind="stable")[:k]
    else:
        cand = np.array(sorted(set(int(i) for i in window)), dtype=int)
        chosen = cand[np.argsort(np.asarray(curve, dtype=float)[cand], kind="stable")[:k]]
    out[chosen] = row.sum() / k
    return out


def valley_fill(rows, curve, windows=None, order=None):
    """Place every row of rows on curve (place_car, with windows[j] when windows is
    given), in the order of the row positions in order (host order when None), adding
    each placed car to the curve before the next. Returns (controlled rows, curve after
    every car)."""
    rows = np.asarray(rows, dtype=float)
    combined = np.asarray(curve, dtype=float).copy()
    out = np.zeros_like(rows)
    for j in (range(rows.shape[0]) if order is None else order):
        out[j, :] = place_car(rows[j, :], combined, None if windows is None else windows[j])
        combined += out[j, :]
    return out, combined


def valley_fill_curves(rows, curves, car_curves, feeder, windows=None, order=None):
    """Place every row of rows on its own curve: curves[car_curves[j]] (place_car, with
    windows[j] when windows is given), in the order of the row positions in order (host
    order when None).
    Each placed car is added to its own curve and to curves[feeder], because every car
    loads the feeder head. Returns (controlled rows, {name: curve after every car})."""
    rows = np.asarray(rows, dtype=float)
    combined = {name: np.asarray(c, dtype=float).copy() for name, c in curves.items()}
    out = np.zeros_like(rows)
    for j in (range(rows.shape[0]) if order is None else order):
        name = car_curves[j]
        out[j, :] = place_car(rows[j, :], combined[name], None if windows is None else windows[j])
        combined[name] += out[j, :]
        if name != feeder:
            combined[feeder] += out[j, :]
    return out, combined


def water_fill(rows, curve, powers, windows=None, order=None):
    """Place every row of rows on curve with a power that varies by interval, in the
    order of the row positions in order (host order when None), adding each placed car
    to the curve before the next. For car j: E = row sum (kW-intervals), p = powers[j],
    W_j = windows[j] (every interval when windows or windows[j] is None) and F the curve
    so far. If p x |W_j| <= E the car charges p in every interval of W_j and the rest is
    left over. Else the level L with sum over W_j of min(p, max(0, L - F_i)) = E is found
    by 200 bisection steps on [min F over W_j, max F over W_j + p], and the car's row is
    min(p, max(0, L - F_i)) on W_j and 0 elsewhere. An all-zero row stays zero. Returns
    (controlled rows, curve after every car).

    ASSUMPTION: under water_fill_feeder each controlled car may charge at any power from
    0 up to its car power in each interval of its window, and the aggregator fills the
    lowest intervals of its forecast toward one level, the valley-filling schedule of
    Gan, Topcu and Low (2013); under evwatts_sessions a car's power is its session's mean
    power, which can be below its charger's limit."""
    rows = np.asarray(rows, dtype=float)
    combined = np.asarray(curve, dtype=float).copy()
    out = np.zeros_like(rows)
    for j in (range(rows.shape[0]) if order is None else order):
        energy = rows[j, :].sum()
        if energy <= 0:
            continue
        p = float(powers[j])
        window = None if windows is None else windows[j]
        cand = np.arange(rows.shape[1]) if window is None else np.array(sorted(set(int(i) for i in window)), dtype=int)
        if p * cand.size <= energy:
            out[j, cand] = p
        else:
            f = combined[cand]
            lo, hi = f.min(), f.max() + p
            for _ in range(200):
                level = (lo + hi) / 2.0
                if np.minimum(p, np.maximum(0.0, level - f)).sum() < energy:
                    lo = level
                else:
                    hi = level
            out[j, cand] = np.minimum(p, np.maximum(0.0, (lo + hi) / 2.0 - f))
        combined += out[j, :]
    return out, combined


def plugin_order(plug_minutes):
    """The row positions of the cars in order of plug-in time: key (t - 240) mod 1440
    for a car plugged in at clock minute t, so the day runs from 04:00 as the NHTS
    travel day. Cars whose plug-in time is None (not charging, or a class (ii) day) come
    last. Ties, and the cars without a time, keep host order."""
    timed = [j for j, t in enumerate(plug_minutes) if t is not None]
    timed.sort(key=lambda j: (float(plug_minutes[j]) - 240.0) % 1440.0)
    return timed + [j for j, t in enumerate(plug_minutes) if t is None]


def forecast_cv(w, model, coefficients):
    """The relative RMS error CV (percent) of a forecast of a load whose mean is w (kWh
    per hour): hour_ahead sqrt(a^2 / w^b + c^2), day_ahead sqrt(a / w + c), with the
    coefficients {a, b, c} of the model."""
    k = coefficients
    if model == "hour_ahead":
        return float(np.sqrt(k["a"] ** 2 / w ** k["b"] + k["c"] ** 2))
    if model == "day_ahead":
        return float(np.sqrt(k["a"] / w + k["c"]))
    raise ValueError(f"Unknown forecast_error model {model!r}.")


def forecast_curve(curve, model, coefficients, z):
    """Return (forecast, error, w, cv) of a curve of 96 kW values. w = the curve's mean
    (kW, equal to kWh per hour); cv = forecast_cv(w, model, coefficients); z = 24 normal
    draws, one per hour. error_i = z[i // 4] x cv / 100 x w and forecast = curve + error.
    When w <= 0 the curve gets no error: forecast = curve, error 0 and cv None."""
    curve = np.asarray(curve, dtype=float)
    w = float(curve.mean())
    if w <= 0:
        return curve.copy(), np.zeros(curve.size), w, None
    cv = forecast_cv(w, model, coefficients)
    error = np.asarray(z, dtype=float)[np.arange(curve.size) // 4] * cv / 100.0 * w
    return curve + error, error, w, cv


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


def read_dss_elements(texts, skipped=None):
    """Read the Line and Transformer elements of the .dss texts. Returns (line_buses,
    transformers): a list of (bus1, bus2) pairs, and {transformer name: list of
    (bus, kV) per winding}. Bus names are lower case without node suffixes. A Line
    whose enabled value starts with n or f (enabled=n, no, false; any case) is left
    out, because OpenDSS solves without a switched-out line; its name is appended to
    skipped when a list is given."""
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
                if d.get("enabled", "y").strip("\"' ").lower()[:1] in ("n", "f"):
                    if skipped is not None:
                        skipped.append(name)
                    continue
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


def service_transformers(texts, load_buses, skipped=None):
    """Map each load to its service transformer.

    1. An undirected graph of the buses joined by Line elements of texts.
    2. A transformer's secondary bus: secondary_bus of its windings.
    3. A load's service transformer is the one transformer whose secondary bus lies in
       the graph component of the load's bus; with none or several, the load has none.

    load_buses: {load name: bus1}. skipped: passed to read_dss_elements. Returns
    (mapping, status): mapping {load: transformer name or None}, status {load: "one",
    "none" or "several"}."""
    line_buses, transformers = read_dss_elements(texts, skipped)
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


def offpeak_row(row, cheap, nominal_kw, window=None, shift=None):
    """Return (controlled row, start interval or None) of one car under offpeak_start.

    Without a window: the start is the first cheap interval at or after the car's first
    charging interval in its session row, searching forward and wrapping from the last
    interval to the first. The car charges at nominal_kw in consecutive intervals from
    the start, wrapping past the last interval, until its daily energy (row sum,
    kW-intervals) is delivered; the last interval takes the remainder. Raises
    ValueError if the energy needs more than every interval of the day.
    With a window (intervals in plug order): the start is the first cheap interval met
    going forward through the window, or the window's first interval if none is cheap;
    the car charges at nominal_kw in the window's consecutive intervals from the start
    until its energy is delivered or the window ends; the rest is left over.
    With shift (intervals), a start that is a cheap interval moves by shift: inside a
    window it is clamped to the window's first and last intervals, without a window it
    wraps modulo 96. A start in a window with no cheap interval does not move.
    An all-zero row stays zero."""
    row = np.asarray(row, dtype=float)
    n = row.size
    out = np.zeros(n)
    nz = np.flatnonzero(row)
    if nz.size == 0:
        return out, None
    cheap_set = set(int(i) for i in cheap)
    if window is not None:
        window = [int(i) for i in window]
        pos = next((k for k, i in enumerate(window) if i in cheap_set), None)
        if pos is None:
            pos = 0
        elif shift:
            pos = min(max(pos + int(shift), 0), len(window) - 1)
        slots = window[pos:]
        energy = row.sum()
        n_full = int(energy // nominal_kw)
        remainder = energy - n_full * nominal_kw
        for i in slots[:n_full]:
            out[i] = nominal_kw
        if n_full < len(slots) and remainder > 0:
            out[slots[n_full]] = remainder
        return out, slots[0]
    start = next(((nz[0] + k) % n for k in range(n) if (nz[0] + k) % n in cheap_set), None)
    if start is None:
        raise ValueError("No cheap interval in the day.")
    if shift:
        start = (start + int(shift)) % n
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


def offpeak_start(rows, cheap, nominal_kw, windows=None, shifts=None):
    """offpeak_row for every row, with power nominal_kw (one value for every car, or
    one per car), windows[j] when windows is given and shifts[j] when shifts is given.
    Returns (controlled rows, list of start intervals)."""
    rows = np.asarray(rows, dtype=float)
    out = np.zeros_like(rows)
    starts = []
    for j in range(rows.shape[0]):
        kw = nominal_kw[j] if np.ndim(nominal_kw) else nominal_kw
        out[j, :], s = offpeak_row(rows[j, :], cheap, kw, None if windows is None else windows[j],
                                   None if shifts is None else shifts[j])
        starts.append(s)
    return out, starts


def start_offsets(rows, cheap, windows, z, sigma_min):
    """The start offset d_j = round(z[j] x sigma_min / 15) intervals (Python round, half
    to even) of every car whose start under offpeak_start is a cheap interval: a car
    without a window, or with a window that holds a cheap interval. None for an all-zero
    row or a window with no cheap interval. z holds one normal draw per car, in host
    order."""
    cheap_set = set(int(i) for i in cheap)
    out = []
    for j in range(np.asarray(rows).shape[0]):
        window = None if windows is None else windows[j]
        if not np.any(np.asarray(rows[j], dtype=float)) or (
                window is not None and not any(int(i) in cheap_set for i in window)):
            out.append(None)
        else:
            out.append(int(round(float(z[j]) * float(sigma_min) / 15.0)))
    return out
