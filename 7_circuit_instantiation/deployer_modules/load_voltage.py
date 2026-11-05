# -*- coding: utf-8 -*-
"""
load_voltage.py
---------------
Voltage at every load of a solved circuit, from one mode=0 Monitor per Load.

- monitor_name(load): the Monitor name of a load, "vl_" + the load name in lower case.
  Load names are unique in a circuit and are valid OpenDSS names, so the Monitor names
  are unique and valid too.
- monitor_lines(loads): the "New Monitor" lines of Monitors_LoadVoltage.dss.
- read_load_monitors(circuit, loads): reads each load's Monitor through the circuit
  object of dss_engine (the same interface on Windows and Linux) and returns one plain
  record per load for load_voltage_frame.
- load_voltage_frame(records): one row per load, step and phase conductor.
- step_table, load_table, circuit_summary: the summaries of that frame.

Per-unit base: the line-to-neutral base kV of the load's bus that OpenDSS reports after
the solve. A bus with no base voltage (0) takes the base from the load's own kV and
phases by OpenDSS's convention: kV is line to neutral for a one-phase wye load and line
to line otherwise, so the base is kV for a one-phase wye load and kV / sqrt(3) else.
"""
import math
import re

import numpy as np
import pandas as pd

V_CHANNEL_RE = re.compile(r"^\s*V(\d+)\s*$")


def monitor_name(load):
    return f"vl_{load.lower()}"


def monitor_lines(loads):
    return [f"New Monitor.{monitor_name(ld)} element=Load.{ld} terminal=1 mode=0\n" for ld in loads]


def base_kv(bus_kv_base, load_kv, phases, delta):
    """Return (line-to-neutral base kV, True if it came from the load because the bus
    has no base voltage)."""
    if bus_kv_base and bus_kv_base > 0:
        return float(bus_kv_base), False
    if int(phases) == 1 and not delta:
        return float(load_kv), True
    return float(load_kv) / math.sqrt(3.0), True


def voltage_columns(header):
    """Return {conductor number (1-based): channel index (1-based)} of the voltage
    magnitude channels (V1, V2, ...) of a mode=0 Monitor header."""
    out = {}
    for i, h in enumerate(header, start=1):
        m = V_CHANNEL_RE.match(h)
        if m:
            out[int(m.group(1))] = i
    return out


def read_load_monitors(circuit, loads):
    """Read the Monitor of each load in loads from a solved circuit (dss_engine's
    ActiveCircuit). Returns one record per load: load, bus, node_order, v (steps x
    conductors, volts), kv_base (bus), kv, phases, delta. The step count is the
    number of samples the Monitor holds."""
    records = []
    for ld in loads:
        circuit.SetActiveElement(f"Load.{ld}")
        elem = circuit.ActiveCktElement
        node_order = [int(n) for n in elem.NodeOrder]
        phases = int(elem.NumPhases)
        bus = str(elem.BusNames[0]).split(".")[0]
        circuit.Loads.Name = ld
        kv = float(circuit.Loads.kV)
        delta = bool(circuit.Loads.IsDelta)
        circuit.SetActiveBus(bus)
        kv_bus = float(circuit.ActiveBus.kVBase)
        mon = circuit.Monitors
        mon.Name = monitor_name(ld)
        n = int(mon.SampleCount)
        cols = voltage_columns(list(mon.Header))
        if len(cols) != len(node_order):
            raise RuntimeError(f"Monitor {monitor_name(ld)} has {len(cols)} voltage channels; "
                               f"load {ld} has {len(node_order)} conductors.")
        v = np.zeros((n, len(node_order)))
        for k in range(len(node_order)):
            ch = np.asarray(mon.Channel(cols[k + 1]), dtype=float)
            if ch.size != n:
                raise RuntimeError(f"Monitor {monitor_name(ld)} channel {cols[k + 1]} holds "
                                   f"{ch.size} values; SampleCount is {n}.")
            v[:, k] = ch
        records.append({"load": ld, "bus": bus, "node_order": node_order, "v": v,
                        "kv_base": kv_bus, "kv": kv, "phases": phases, "delta": delta})
    return records


def load_voltage_frame(records):
    """Return (frame, no_base_loads). frame has one row per load, step (1..N) and phase
    conductor, columns load, bus, step, conductor, v_volts, v_pu; neutral and ground
    conductors (node 0) are left out. no_base_loads lists the loads whose bus has no
    base voltage (base from the load, see base_kv)."""
    parts = []
    no_base = []
    for r in records:
        kv, from_load = base_kv(r["kv_base"], r["kv"], r["phases"], r["delta"])
        if from_load:
            no_base.append(r["load"])
        v = np.asarray(r["v"], dtype=float)
        n = v.shape[0]
        for k, node in enumerate(r["node_order"]):
            if int(node) == 0:
                continue
            parts.append(pd.DataFrame({
                "load": r["load"], "bus": r["bus"], "step": np.arange(1, n + 1),
                "conductor": int(node), "v_volts": v[:, k], "v_pu": v[:, k] / (kv * 1000.0),
            }))
    cols = ["load", "bus", "step", "conductor", "v_volts", "v_pu"]
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    frame = frame.sort_values(["load", "conductor", "step"], kind="mergesort").reset_index(drop=True)
    return frame[cols], no_base


def step_table(frame, low_pu, high_pu):
    """One row per step: lowest and highest v_pu with their load, and the count of load
    conductors below low_pu and above high_pu. Ties go to the first load by name."""
    f = frame.sort_values(["step", "load", "conductor"], kind="mergesort")
    g = f.groupby("step", sort=True)
    lo = f.loc[g["v_pu"].idxmin()]
    hi = f.loc[g["v_pu"].idxmax()]
    return pd.DataFrame({
        "step": lo["step"].to_numpy(),
        "v_pu_min": lo["v_pu"].to_numpy(),
        "v_pu_min_load": lo["load"].to_numpy(),
        "v_pu_max": hi["v_pu"].to_numpy(),
        "v_pu_max_load": hi["load"].to_numpy(),
        "n_below": g["v_pu"].apply(lambda s: int((s < low_pu).sum())).to_numpy(),
        "n_above": g["v_pu"].apply(lambda s: int((s > high_pu).sum())).to_numpy(),
    })


def load_table(frame, low_pu, high_pu):
    """One row per load: lowest and highest v_pu over the day with their steps, and the
    number of steps at which any of the load's conductors is outside the band. Ties go
    to the first step."""
    f = frame.sort_values(["load", "step", "conductor"], kind="mergesort")
    g = f.groupby("load", sort=True)
    lo = f.loc[g["v_pu"].idxmin()]
    hi = f.loc[g["v_pu"].idxmax()]
    outside = f.assign(out=(f["v_pu"] < low_pu) | (f["v_pu"] > high_pu))
    n_out = outside.groupby(["load", "step"])["out"].any().groupby("load").sum()
    return pd.DataFrame({
        "load": lo["load"].to_numpy(),
        "bus": lo["bus"].to_numpy(),
        "v_pu_min": lo["v_pu"].to_numpy(),
        "v_pu_min_step": lo["step"].to_numpy(),
        "v_pu_max": hi["v_pu"].to_numpy(),
        "v_pu_max_step": hi["step"].to_numpy(),
        "n_steps_outside": n_out.reindex(lo["load"]).astype(int).to_numpy(),
    })


def circuit_summary(loads, low_pu, high_pu):
    """One circuit's summary from its load table (load_voltage_loads.csv): lowest and
    highest load v_pu of the day, loads ever below the band, loads ever above, and
    load-steps outside the band."""
    return {
        "v_pu_min": float(loads["v_pu_min"].min()),
        "v_pu_max": float(loads["v_pu_max"].max()),
        "n_loads_below": int((loads["v_pu_min"] < low_pu).sum()),
        "n_loads_above": int((loads["v_pu_max"] > high_pu).sum()),
        "n_load_steps_outside": int(loads["n_steps_outside"].sum()),
    }
