# -*- coding: utf-8 -*-
"""
storage_control.py
------------------
The storage rules of storage_rule (der_sizing in pipeline_config.yaml) in the Phase 7
deploy. A curve is the forecast of the measured kW of one view (the feeder head, a
service transformer or a host's service line) over the steps of the day, each step
dt hours long.

- simple_targets(curve, peak_fraction, mean_fraction): kWTarget and kWTargetLow of the
  StorageController from the curve's peak and mean.
- tuned_targets(curve, kw, kwh, reserve, eff_charge, eff_discharge, dt): kWTarget at
  the level above which the curve holds the usable energy of the view's batteries, and
  kWTargetLow at the level below which filling the curve recharges them.
- schedule(curve, kw, kwh, start, reserve, eff_charge, eff_discharge, dt): one
  battery's charge and discharge per step, peak shaving and valley filling (Gan, Topcu
  and Low 2013, https://doi.org/10.1109/TPWRS.2012.2210288) within its kW, kWh,
  efficiencies and reserve, ending the day at its starting energy.
- feeding_lines(texts, hosts): the Line that feeds each host's bus (storage_view
  building).
- level_above(curve, energy, cap, dt) and level_below(curve, energy, cap, dt): the
  levels these rules use.
Energies are kWh, powers kW, start and reserve fractions of kWh.
"""
import re
from collections import deque

import numpy as np

from ev_control import _PROP_RE, _bus, _logical_lines, read_dss_elements, secondary_bus

BISECTION_STEPS = 200  # as water_fill in ev_control.py


def feeding_lines(texts, hosts):
    """The Line that feeds each host's bus, for storage_view building.

    hosts: {host: (host bus, service transformer name or None)}. Over the enabled Line
    elements of texts (enabled=n, no or false left out, as read_dss_elements), a
    breadth-first search from the transformer's secondary bus (secondary_bus) reaches
    the host's bus; the last Line on that path feeds it. Returns {host: (line name,
    terminal) or None}: terminal 1 when the line's bus1 is the end nearer the
    transformer, else 2. None when the host has no transformer, its bus is the
    secondary bus, or the search does not reach it."""
    lines = []
    for text in texts:
        for st in _logical_lines(text):
            m = re.match(r"(?i)^new\s+line\.(\S+)\s*(.*)$", st)
            if not m:
                continue
            d = {k.lower(): v for k, v in _PROP_RE.findall(m.group(2))}
            if d.get("enabled", "y").strip("\"' ").lower()[:1] in ("n", "f"):
                continue
            if "bus1" in d and "bus2" in d:
                lines.append((m.group(1), _bus(d["bus1"]), _bus(d["bus2"])))
    adj = {}
    for name, b1, b2 in lines:
        adj.setdefault(b1, []).append((b2, name, 1))
        adj.setdefault(b2, []).append((b1, name, 2))
    _, transformers = read_dss_elements(texts)
    out, parents = {}, {}
    for host, (bus, tr) in hosts.items():
        sec = secondary_bus(transformers.get(tr, [])) if tr else None
        target = _bus(bus) if bus else None
        if sec is None or target is None or target == sec:
            out[host] = None
            continue
        if sec not in parents:
            parent = {sec: None}
            queue = deque([sec])
            while queue:
                b = queue.popleft()
                for nb, name, term in adj.get(b, []):
                    if nb not in parent:
                        parent[nb] = (b, name, term)
                        queue.append(nb)
            parents[sec] = parent
        step = parents[sec].get(target)
        out[host] = (step[1], step[2]) if step else None
    return out


def level_above(curve, energy, cap, dt):
    """The level L with sum over steps of min(cap, max(0, curve - L)) x dt = energy
    (cap None: no cap), by BISECTION_STEPS bisection steps on [min(curve) - cap or
    min(curve), max(curve)]. Energy at or above the most the curve holds gives the
    lower end."""
    f = np.asarray(curve, dtype=float)
    lo, hi = f.min() - (cap if cap is not None else 0.0), f.max()

    def held(level):
        d = np.maximum(0.0, f - level)
        return (d if cap is None else np.minimum(cap, d)).sum() * dt

    if energy <= 0:
        return hi
    if held(lo) <= energy:
        return lo
    for _ in range(BISECTION_STEPS):
        mid = (lo + hi) / 2.0
        if held(mid) > energy:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def level_below(curve, energy, cap, dt):
    """The level L with sum over steps of min(cap, max(0, L - curve)) x dt = energy, by
    BISECTION_STEPS bisection steps on [min(curve), max(curve) + cap]. Energy at or
    above the most that fits gives the upper end."""
    f = np.asarray(curve, dtype=float)
    lo, hi = f.min(), f.max() + cap

    def filled(level):
        return np.minimum(cap, np.maximum(0.0, level - f)).sum() * dt

    if energy <= 0:
        return lo
    if filled(hi) <= energy:
        return hi
    for _ in range(BISECTION_STEPS):
        mid = (lo + hi) / 2.0
        if filled(mid) < energy:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def simple_targets(curve, peak_fraction, mean_fraction):
    """Return (kWTarget, kWTargetLow) = (peak_fraction x max(curve), mean_fraction x
    mean(curve))."""
    f = np.asarray(curve, dtype=float)
    return peak_fraction * float(f.max()), mean_fraction * float(f.mean())


def tuned_targets(curve, kw, kwh, reserve, eff_charge, eff_discharge, dt):
    """Return (kWTarget, kWTargetLow, usable, delivered, recharge) for the batteries of
    one view (total kW kw, total kWh kwh).

    usable = kwh x (1 - reserve) x eff_discharge, the energy above the reserve as it
    reaches the grid.
    kWTarget = max(L_d, max(curve) - kw), where L_d = level_above(curve, usable, None,
    dt): the level above which the curve's energy equals usable, not lower than the
    peak minus the batteries' total kW.
    delivered = sum of min(kw, max(0, curve - kWTarget)) x dt, the energy the batteries
    give above kWTarget.
    recharge = delivered / (eff_discharge x eff_charge), the grid energy that brings
    them back to their starting energy.
    kWTargetLow = min(kWTarget, level_below(curve, recharge, kw, dt)): the level below
    which filling the curve, within kw, takes recharge."""
    f = np.asarray(curve, dtype=float)
    usable = kwh * (1.0 - reserve) * eff_discharge
    target = max(level_above(f, usable, None, dt), float(f.max()) - kw)
    delivered = float(np.minimum(kw, np.maximum(0.0, f - target)).sum() * dt)
    recharge = delivered / (eff_discharge * eff_charge)
    low = min(target, level_below(f, recharge, kw, dt))
    return target, low, usable, delivered, recharge


def _plan(f, x, kw, eff_charge, eff_discharge, dt):
    """Discharge of x kWh above level L_d and the matching charge below level L_c."""
    l_d = level_above(f, x, kw, dt)
    dis = np.minimum(kw, np.maximum(0.0, f - l_d))
    need = dis.sum() * dt / (eff_discharge * eff_charge)
    l_c = level_below(f, need, kw, dt)
    chg = np.minimum(kw, np.maximum(0.0, l_c - f))
    return dis, chg, l_d, l_c


def _energy(dis, chg, e0, eff_charge, eff_discharge, dt):
    """Stored energy at the start of each step and at the end of the day."""
    delta = (chg * eff_charge - dis / eff_discharge) * dt
    return e0 + np.concatenate(([0.0], np.cumsum(delta)))


def schedule(curve, kw, kwh, start, reserve, eff_charge, eff_discharge, dt):
    """Return (net, energy, x) for one battery on curve.

    For a discharge budget x (kWh to the grid): discharge d_i = min(kw, max(0, f_i -
    L_d)) with sum d_i x dt = x (peak shaving), and charge c_i = min(kw, max(0, L_c -
    f_i)) with sum c_i x dt = x / (eff_discharge x eff_charge) (valley filling), so the
    stored energy e, starting at start x kwh and moving by (c_i x eff_charge - d_i /
    eff_discharge) x dt per step, ends the day where it started. x is the largest budget
    in [0, (1 - reserve) x kwh x eff_discharge] found by BISECTION_STEPS bisection
    steps for which e stays within [reserve x kwh, kwh] at every step, ends within a
    rounding tolerance of its start and L_c < L_d;
    x = 0 (no schedule) always qualifies. net_i = d_i - c_i (kW, positive discharge),
    energy the 97 stored energies (kWh) from the start of the day to its end."""
    f = np.asarray(curve, dtype=float)
    e0, e_min, e_max = start * kwh, reserve * kwh, kwh
    tol = kwh * 1e-9

    def ok(x):
        dis, chg, l_d, l_c = _plan(f, x, kw, eff_charge, eff_discharge, dt)
        e = _energy(dis, chg, e0, eff_charge, eff_discharge, dt)
        return ((l_c < l_d) and e.min() >= e_min - tol and e.max() <= e_max + tol
                and abs(e[-1] - e0) <= tol)

    lo, hi = 0.0, (1.0 - reserve) * kwh * eff_discharge
    if hi > 0 and ok(hi):
        lo = hi
    elif hi > 0:
        for _ in range(BISECTION_STEPS):
            mid = (lo + hi) / 2.0
            if ok(mid):
                lo = mid
            else:
                hi = mid
    if lo <= 0:
        z = np.zeros(f.size)
        return z, _energy(z, z, e0, eff_charge, eff_discharge, dt), 0.0
    dis, chg, _, _ = _plan(f, lo, kw, eff_charge, eff_discharge, dt)
    return dis - chg, _energy(dis, chg, e0, eff_charge, eff_discharge, dt), lo
