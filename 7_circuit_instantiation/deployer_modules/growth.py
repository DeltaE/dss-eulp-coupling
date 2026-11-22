# -*- coding: utf-8 -*-
"""
growth.py
---------
The rules of load growth over planning years (configs/growth.yaml), as functions that
need no OpenDSS. Phase growth (growth_plan.py) calls them to write the plan of a run;
find_max_day_curve_impl.py --mix, Phase 7b (instantiate_circuits.py) and the deploy read
that plan and call the small helpers at the end of this file.

One run is one planning year, growth_years years after the data year of the building
curves. Per circuit (one SMART-DS feeder):
- Factors. A home is a customer whose yearly loadshapes all start res_, a business one
  whose loadshapes all start com_ (heating_split.load_segment). Every home's kW and kvar
  are multiplied by (1 + use_per_household / 100) ^ growth_years, every business's by
  (1 + use_per_ft2 / 100) ^ growth_years. A customer that is neither keeps 1 and is
  never copied. load_factors replaces the factor of a named customer; with peak_factor
  its curve is stretched (stretch).
- Counts (counts). New homes = round(H x ((1 + households / 100) ^ years - 1)), H the
  circuit's homes. Companion businesses by the companions setting. The infill share
  splits both between infill and extension blocks.
- The plan is built year by year (year_additions, plan_years), in one seeded sequence
  per circuit: the plan of a horizon is the state after its last year, so a longer
  horizon holds every unit of a shorter one. Year t adds what the counts at t years
  hold beyond what earlier years added.
- Infill. Each infill home is a copy of one existing home, the next position of one
  seeded order of the homes; each companion a copy of one business drawn for it
  (companion_candidates, companion_draw). A copy copies its customer's connection
  (copy_customer).
- Blocks. A block is a copy of one of the circuit's laterals (find_laterals), attached
  at a three-phase medium-voltage bus (attach_bus). Block homes and block companions
  wait until a lateral fits; those still waiting at the horizon arrive as infill copies
  marked waiting.
- Regulators. A voltage regulator (is_regulator) is crossed like a line of its own
  phases wherever the medium-voltage network is walked (read_feeder,
  three_phase_mv_buses, find_laterals, path_lines); every other transformer ends it. A
  lateral that holds a regulator is a block template only under regulators.block_copies
  with_control, and its copy carries each RegControl of its transformers
  (read_regcontrols, copy_lateral). Under regulators.path_impedance with_regulator the
  path impedance counts the reactance of each regulator on the path.
- Named loads. Loads of one ComStock building type, each on a three-phase
  medium-voltage bus, connected like the existing customer of the nearest size
  (connect_named). When that customer sits behind a service transformer and no
  transformer of the feeder is large enough, the load connects at medium voltage on a
  new line and bus of its own (mv_new_line).

Seeds: one growth seed per circuit, random_seed of pipeline_config.yaml plus the sha256
offset of "<substation>|<feeder>" (growth_seed). Every draw has its own name on that
seed (draw), so adding a draw never moves another. Counts are computed, never drawn:
the seeds only choose which customer or lateral is copied and where it attaches.

New names: <template name>_g<unit>, the unit being one infill home (h<position in the
home order>), one block (b<k>), one companion (c<k>) or one named load (n<entry>x<j>).
A load keeps its _<n> leg suffix after the _g<unit> part, so the name of a new customer
never ends in _<digits>.
"""

import math
import random
import re
import statistics

from heating_split import _stable_seed_offset, load_segment
from ev_control import _PROP_RE, _array, _bus, _logical_lines, service_transformers

# ASSUMPTION: bus positions are projected with a spherical Earth of mean radius
# 6,371,008.8 m (the IUGG mean radius R1 of GRS 80), one equirectangular projection per
# circuit about its mean latitude. A circuit spans a few kilometres, where this differs
# from an ellipsoidal projection by under one percent; distances only rank attach buses
# and space blocks apart.
EARTH_RADIUS_M = 6371008.8

# Length of one unit of a Line's Units= in metres (OpenDSS length units).
UNIT_M = {"km": 1000.0, "m": 1.0, "kft": 304.8, "ft": 0.3048, "mi": 1609.344, "in": 0.0254, "cm": 0.01}

# XHL of a transformer statement that writes no XHL, X12 or XscArray: 7 percent, the
# OpenDSS default, https://cimhub-opendss.readthedocs.io/en/latest/schema_ref/Xhl/
XHL_DEFAULT_PERCENT = 7.0
KILO = 1000.0  # the SI prefix kilo, https://www.bipm.org/en/measurement-units/si-prefixes

SEGMENT_RATE = {"residential": "use_per_household", "commercial": "use_per_ft2"}


class GrowthError(Exception):
    """A growth rule cannot be applied. The calling script prints [FAIL] and exits 1."""


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------
def growth_seed(random_seed, substation, feeder):
    """The growth seed of one circuit: random_seed + the sha256 offset of
    "<substation>|<feeder>" (heating_split._stable_seed_offset, as Phase 7b)."""
    return int(random_seed) + _stable_seed_offset(f"{substation}|{feeder}")


def draw(name, seed):
    """A random.Random of its own for the draw called name on seed (the pattern of
    ev_cars.rng: seed + the sha256 offset of the name)."""
    return random.Random(int(seed) + _stable_seed_offset(name))


def seeded_order(items, name, seed):
    """The sorted items in the seeded order of the draw called name."""
    order = sorted(items)
    draw(name, seed).shuffle(order)
    return order


def take(order, n):
    """The first n of order; past its end the order starts again."""
    return [order[i % len(order)] for i in range(n)] if order else []


# ---------------------------------------------------------------------------
# Rates, factors and counts
# ---------------------------------------------------------------------------
def growth_factor(rate, years):
    """(1 + rate / 100) ^ years, rate in percent a year."""
    return (1.0 + float(rate) / 100.0) ** int(years)


def segment_factors(rates, years):
    """{segment: factor} of the existing and new customers of each segment."""
    return {seg: growth_factor(rates[name], years) for seg, name in SEGMENT_RATE.items()}


def counts(homes, businesses, rates, years, companions, national, share):
    """The counts of one circuit with homes homes and businesses businesses: new_homes,
    companions, infill_homes, block_homes, infill_companions, block_companions. Python's
    round. companions feeder: round(new homes x businesses / homes); national: round(new
    homes / (households_million / commercial_buildings_million)); aeo: round(businesses x
    floorspace growth). share is the infill share as a number."""
    new_homes = round(homes * (growth_factor(rates["households"], years) - 1.0))
    if companions == "feeder":
        n_comp = round(new_homes * businesses / homes) if homes else 0
    elif companions == "national":
        n_comp = round(new_homes / (float(national["households_million"])
                                    / float(national["commercial_buildings_million"])))
    else:
        n_comp = round(businesses * (growth_factor(rates["floorspace"], years) - 1.0))
    infill_homes = round(new_homes * share)
    infill_comp = round(n_comp * share)
    return {"new_homes": new_homes, "companions": n_comp, "infill_homes": infill_homes,
            "block_homes": new_homes - infill_homes, "infill_companions": infill_comp,
            "block_companions": n_comp - infill_comp}


def year_additions(homes, businesses, rates, years, companions, national, share):
    """What each year adds, [{count: n}] for year 1 to years. With C(t) the six counts
    of counts at t years, year t adds max(0, C(t) - what earlier years added) of each,
    so a count that never falls from one year to the next sums to its value at the
    horizon."""
    added, out = {}, []
    for t in range(1, int(years) + 1):
        c = counts(homes, businesses, rates, t, companions, national, share)
        step = {key: max(0, value - added.get(key, 0)) for key, value in c.items()}
        added = {key: added.get(key, 0) + step[key] for key in c}
        out.append(step)
    return out


def stretch_coefficients(peak, mean, factor, peak_factor):
    """(a, b) of new = a x old + b for a curve with annual peak and mean: annual energy
    grows by factor and annual peak by peak_factor. a = (peak_factor x peak - factor x
    mean) / (peak - mean), b = mean x (factor - a). Raises GrowthError when peak equals
    mean."""
    if peak == mean:
        raise GrowthError(f"the curve's annual peak equals its annual mean ({peak}); it cannot be stretched")
    a = (peak_factor * peak - factor * mean) / (peak - mean)
    return a, mean * (factor - a)


def stretch(values, factor, peak_factor):
    """(a, b) for the whole-year kW values of one customer (stretch_coefficients on their
    maximum and mean). Raises GrowthError when any point of a x old + b is below 0."""
    peak, low, mean = max(values), min(values), sum(values) / len(values)
    a, b = stretch_coefficients(peak, mean, factor, peak_factor)
    worst = min(a * peak + b, a * low + b)
    if worst < 0:
        raise GrowthError(f"the stretched curve falls to {worst:.6g} kW, below 0 "
                          f"(factor {factor}, peak_factor {peak_factor}, a {a:.6g}, b {b:.6g})")
    return a, b


# ---------------------------------------------------------------------------
# The feeder as SMART-DS built it
# ---------------------------------------------------------------------------
def _props(rest):
    return [(k.lower(), v) for k, v in _PROP_RE.findall(rest)]


_NUMBER = r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?"


def _base(full):
    """The customer of a Load line: its name without the _<n> leg suffix (Phase 7b)."""
    return re.sub(r"_[0-9]+$", "", full)


def _enabled(d):
    return d.get("enabled", "y").strip("\"' ").lower()[:1] not in ("n", "f")


def read_linecodes(text):
    """{linecode name, lower case: {"normamps", "nphases", "z1": positive-sequence
    impedance, complex ohm per unit length, "units"}} of a LineCodes.dss text. z1 is the
    mean diagonal less the mean off-diagonal of Rmatrix + j Xmatrix (the diagonal alone
    for one phase)."""
    out = {}
    for st in _logical_lines(text):
        m = re.match(r"(?i)^new\s+linecode\.(\S+)\s*(.*)$", st)
        if not m:
            continue
        d = dict(_props(m.group(2)))

        def matrix(value):
            rows = [[float(x) for x in _array(r)] for r in value.strip("()[] ").split("|")]
            diag = [row[i] for i, row in enumerate(rows) if i < len(row)]
            n = len(rows)
            off = [rows[i][j] for i in range(n) for j in range(len(rows[i])) if i != j]
            return sum(diag) / len(diag) - (sum(off) / len(off) if off else 0.0)

        z1 = None
        if "rmatrix" in d and "xmatrix" in d:
            z1 = complex(matrix(d["rmatrix"]), matrix(d["xmatrix"]))
        out[m.group(1).lower()] = {"normamps": float(d["normamps"]) if "normamps" in d else None,
                                   "nphases": int(d["nphases"]) if "nphases" in d else None,
                                   "z1": z1, "units": d.get("units", "none").lower()}
    return out


def read_coords(text):
    """{bus, lower case: (lon, lat)} of a Buscoords.dss text (bus x y per line)."""
    out = {}
    for raw in text.splitlines():
        parts = re.split(r"[\s,]+", raw.strip())
        if len(parts) >= 3:
            try:
                out[parts[0].lower()] = (float(parts[1]), float(parts[2]))
            except ValueError:
                continue
    return out


def is_regulator(tr):
    """True for a voltage regulator: a transformer of read_feeder with two or more
    windings whose windings all have the same kV (a winding without a written kV makes
    it none). The line regulators network growth builds are regulators too."""
    kvs = [w[2] for w in tr["windings"]]
    return len(kvs) >= 2 and None not in kvs and len(set(kvs)) == 1


def regulator_reactance(tr):
    """The series reactance (ohm) of regulator tr (read_feeder): XHL / 100 x kV^2 x KILO /
    kVA, with kV and kVA of its first winding as written and XHL that of read_feeder, else
    XHL_DEFAULT_PERCENT. XHL is the percent reactance from winding 1 to winding 2 on the
    kVA base of winding 1, kV phase to phase for a three-phase transformer and the winding
    kV otherwise (https://opendss.epri.com/Properties16.html); the conversion to ohm:
    https://cimhub-opendss.readthedocs.io/en/latest/schema_ref/XHL/ . None when the first
    winding has no kV or no kVA.
    ASSUMPTION: a regulator adds its leakage reactance only; its winding resistance is left
    out, which lowers the magnitude of a path impedance a little."""
    _, _, kv, kva = tr["windings"][0] if tr["windings"] else (None, None, None, None)
    if not kv or not kva:
        return None
    xhl = XHL_DEFAULT_PERCENT if tr.get("xhl") is None else tr["xhl"]
    return xhl / 100.0 * kv * kv * KILO / kva


def read_feeder(texts):
    """The network of one feeder. texts: {file name, lower case: text} with lines.dss,
    transformers.dss, loads.dss and master.dss (linecodes.dss and buscoords.dss when
    present). Returns a dict:
    - source: the source bus of New Circuit (lower case, no nodes); base_kv: its basekV
      (None when not written);
    - lines: one dict per New Line (name, text, bus1, bus2 as written, b1, b2 lower case
      without nodes, phases, length_m, linecode, switch, enabled);
    - transformers: one dict per New Transformer (name, text, windings [(bus as written,
      bus, kV, kVA)], phases, xhl: the value of XHL or X12, else the first value of
      XscArray, None when the statement writes none);
    - loads: one dict per New Load (name, base, text, bus1, bus, kv, phases, kw, kvar,
      yearly);
    - customers: {base: {loads, bus (None when its lines sit on several buses), kw,
      kvar, shapes, segment}};
    - parent: {bus: (kind line or transformer, element, upstream bus)} of the tree walked
      from the source bus over enabled lines and transformers; children {bus: [bus]};
    - mv: the source bus and every bus reached over a line or over a regulator
      (is_regulator) from a bus of mv; any other transformer ends it;
    - extra_lines: enabled lines that close a loop (both ends already reached);
    - linecodes, coords.
    A feeder without a source bus raises GrowthError."""
    lines, transformers, loads = [], [], []
    for st in _logical_lines(texts.get("lines.dss", "")):
        m = re.match(r"(?i)^new\s+line\.(\S+)\s*(.*)$", st)
        if not m:
            continue
        d = dict(_props(m.group(2)))
        if "bus1" not in d or "bus2" not in d:
            continue
        lines.append({"name": m.group(1), "text": st, "bus1": d["bus1"], "bus2": d["bus2"],
                      "b1": _bus(d["bus1"]), "b2": _bus(d["bus2"]), "phases": int(d.get("phases", 3)),
                      "length_m": float(d.get("length", 0.0)) * UNIT_M.get(d.get("units", "m").lower(), 1.0),
                      "linecode": d.get("linecode", "").lower(),
                      "switch": d.get("switch", "n").strip("\"' ").lower()[:1] in ("y", "t"),
                      "enabled": _enabled(d)})
    for st in _logical_lines(texts.get("transformers.dss", "")):
        m = re.match(r"(?i)^new\s+transformer\.(\S+)\s*(.*)$", st)
        if not m:
            continue
        wdg, buses, kvs, kvas, phases = 1, {}, {}, {}, 3
        xhl = xsc = None
        for k, v in _props(m.group(2)):
            if k == "wdg":
                wdg = int(v)
            elif k == "bus":
                buses[wdg] = v
            elif k == "kv":
                kvs[wdg] = float(v)
            elif k == "kva":
                kvas[wdg] = float(v)
            elif k == "phases":
                phases = int(v)
            elif k == "buses":
                buses.update({i: b for i, b in enumerate(_array(v), start=1)})
            elif k == "kvs":
                kvs.update({i: float(x) for i, x in enumerate(_array(v), start=1)})
            elif k == "kvas":
                kvas.update({i: float(x) for i, x in enumerate(_array(v), start=1)})
            elif k in ("xhl", "x12") and re.fullmatch(_NUMBER, v):
                xhl = float(v)
            elif k == "xscarray" and _array(v) and re.fullmatch(_NUMBER, _array(v)[0]):
                xsc = float(_array(v)[0])
        windings = [(buses.get(i), _bus(buses[i]) if i in buses else None, kvs.get(i), kvas.get(i))
                    for i in sorted(set(buses) | set(kvs))]
        transformers.append({"name": m.group(1), "text": st, "windings": windings, "phases": phases,
                             "xhl": xhl if xhl is not None else xsc})
    for st in _logical_lines(texts.get("loads.dss", "")):
        m = re.match(r"(?i)^new\s+load\.(\S+)\s*(.*)$", st)
        if not m:
            continue
        d = dict(_props(m.group(2)))
        loads.append({"name": m.group(1), "base": _base(m.group(1)), "text": st, "bus1": d.get("bus1", ""),
                      "bus": _bus(d.get("bus1", "")), "kv": float(d["kv"]) if "kv" in d else None,
                      "phases": int(d.get("phases", 3)), "kw": float(d.get("kw", 0.0)),
                      "kvar": float(d.get("kvar", 0.0)), "yearly": d.get("yearly")})
    source = base_kv = None
    for st in _logical_lines(texts.get("master.dss", "")):
        m = re.match(r"(?i)^new\s+circuit\.\S+\s*(.*)$", st)
        if m:
            d = dict(_props(m.group(1)))
            source = _bus(d.get("bus1", "sourcebus"))
            base_kv = float(d["basekv"]) if "basekv" in d else None
            break
    if source is None:
        raise GrowthError("Master.dss has no New Circuit line")

    customers, base_to_daily = {}, {}
    for ld in loads:
        if ld["base"] == "load":
            continue
        c = customers.setdefault(ld["base"], {"loads": [], "buses": [], "kw": 0.0, "kvar": 0.0, "shapes": set()})
        c["loads"].append(ld)
        c["kw"] += ld["kw"]
        c["kvar"] += ld["kvar"]
        if ld["bus"] not in c["buses"]:
            c["buses"].append(ld["bus"])
        if ld["yearly"]:
            c["shapes"].add(ld["yearly"])
            base_to_daily.setdefault(ld["base"], set()).add(ld["yearly"])
    for base, c in customers.items():
        c["bus"] = c["buses"][0] if len(c["buses"]) == 1 else None
        c["segment"] = load_segment(base, base_to_daily)

    adjacent = {}
    for ln in lines:
        if ln["enabled"]:
            adjacent.setdefault(ln["b1"], []).append(("line", ln, ln["b2"]))
            adjacent.setdefault(ln["b2"], []).append(("line", ln, ln["b1"]))
    for tr in transformers:
        first = tr["windings"][0][1] if tr["windings"] else None
        for _, bus, _, _ in tr["windings"][1:]:
            if first and bus and bus != first:
                adjacent.setdefault(first, []).append(("transformer", tr, bus))
    parent, children, mv, extra = {}, {}, {source}, []
    queue, seen_lines = [source], set()
    while queue:
        bus = queue.pop(0)
        for kind, element, other in adjacent.get(bus, []):
            if kind == "line":
                if id(element) in seen_lines:
                    continue
                seen_lines.add(id(element))
            if other == source or other in parent:
                if kind == "line":
                    extra.append(element)
                continue
            parent[other] = (kind, element, bus)
            children.setdefault(bus, []).append(other)
            if bus in mv and (kind == "line" or is_regulator(element)):
                mv.add(other)
            queue.append(other)
    return {"source": source, "base_kv": base_kv, "lines": lines, "transformers": transformers, "loads": loads,
            "customers": customers, "parent": parent, "children": children, "mv": mv,
            "extra_lines": extra, "linecodes": read_linecodes(texts.get("linecodes.dss", "")),
            "coords": read_coords(texts.get("buscoords.dss", ""))}


def subtree(net, bus):
    """bus and every bus downstream of it, in walk order."""
    out, queue = [], [bus]
    while queue:
        b = queue.pop(0)
        out.append(b)
        queue.extend(net["children"].get(b, []))
    return out


def path_lines(net, top, bus):
    """The lines from bus up to top, as a list ordered from top down; a regulator on
    the way is crossed and adds no line. None when the walk meets another transformer
    or the source before top."""
    out = []
    while bus != top:
        step = net["parent"].get(bus)
        if step is None or (step[0] != "line" and not is_regulator(step[1])):
            return None
        if step[0] == "line":
            out.append(step[1])
        bus = step[2]
    return out[::-1]


def three_phase_mv_buses(net):
    """The medium-voltage buses fed by a three-phase line or by a three-phase regulator,
    the source bus left out, sorted."""
    return sorted(b for b, (kind, el, up) in net["parent"].items()
                  if (kind == "line" or is_regulator(el)) and b in net["mv"] and el["phases"] == 3)


def transformer_map(net, texts):
    """({load name: service transformer name or None}, {transformer name: [customer
    base, ...]}) by ev_control.service_transformers on the feeder's .dss texts."""
    mapping, _ = service_transformers(list(texts.values()), {ld["name"]: ld["bus1"] for ld in net["loads"]})
    served = {}
    for base in sorted(net["customers"]):
        names = {mapping.get(ld["name"]) for ld in net["customers"][base]["loads"]}
        if len(names) == 1 and None not in names:
            served.setdefault(names.pop(), []).append(base)
    return mapping, served


def customer_connection(net, base, tr_map, served):
    """How customer base is connected: a dict with pattern and the elements a copy needs.
    - own_bus: its load bus is not the end of exactly one line (its lines sit on several
      buses, the bus is fed by a transformer or by no element, or a loop ends there), or
      it has no single service transformer and is not at medium voltage. reason says
      which.
    - mv_line: a medium-voltage customer; line is the line that feeds its bus.
    - drop: its service transformer serves more than one customer; line is its last
      line, transformer the shared transformer.
    - transformer: it is alone on its service transformer.
    drop and transformer both carry transformer and lines, the lines from the
    transformer's secondary bus down to the load bus."""
    c = net["customers"][base]
    bus = c["bus"]
    if bus is None:
        return {"pattern": "own_bus", "reason": "load lines on several buses"}
    step = net["parent"].get(bus)
    if step is None or step[0] != "line":
        return {"pattern": "own_bus", "reason": "load bus is not the end of a line"}
    if any(bus in (ln["b1"], ln["b2"]) for ln in net["extra_lines"]):
        return {"pattern": "own_bus", "reason": "load bus is the end of more than one line"}
    line = step[1]
    if bus in net["mv"]:
        return {"pattern": "mv_line", "line": line, "up": step[2]}
    names = {tr_map.get(ld["name"]) for ld in c["loads"]}
    if len(names) != 1 or None in names:
        return {"pattern": "own_bus", "reason": "no single service transformer"}
    tr_name = names.pop()
    tr = next(t for t in net["transformers"] if t["name"] == tr_name)
    lines = path_lines(net, tr["windings"][-1][1], bus)
    if not lines:
        return {"pattern": "own_bus", "reason": "no line path from the service transformer"}
    return {"pattern": "drop" if len(served.get(tr_name, [])) > 1 else "transformer", "line": line,
            "up": step[2], "transformer": tr, "lines": lines}


# ---------------------------------------------------------------------------
# Copies
# ---------------------------------------------------------------------------
_BUS_VALUE = re.compile(r"(?i)\b(bus1|bus2|bus)=(\S+)")
# a buses= array in brackets, parentheses or quotes, and one bus of it
_BUSES_VALUE = re.compile(r"(?i)\b(buses\s*=\s*)(\[[^\]]*\]|\([^\)]*\)|\"[^\"]*\"|'[^']*')")
_ARRAY_BUS = re.compile(r"[^\s,()\[\]\"']+")


def new_name(name, unit):
    """<name>_g<unit>; a Load name keeps its _<n> leg suffix last."""
    base = _base(name)
    return f"{base}_g{unit}{name[len(base):]}"


def copy_text(text, kind, name, busmap):
    """The New <kind>.<...> statement text with the element renamed to name and every
    bus1, bus2 or bus value whose bus is a key of busmap (lower case, no nodes) set to
    the mapped bus, its nodes kept. The same holds for each bus of a buses= array
    (buses=(a.1, b.1), buses=[a.1 b.1] or quoted); its brackets, separators and every
    other character stay as written."""
    out = re.sub(rf"(?i)^(\s*new\s+{kind}\.)\S+", lambda m: m.group(1) + name, text, count=1)

    def swap(m):
        bare, dot, nodes = m.group(2).partition(".")
        new = busmap.get(bare.lower())
        return f"{m.group(1)}={new}{dot}{nodes}" if new else m.group(0)

    def swap_bus(m):
        bare, dot, nodes = m.group(0).partition(".")
        new = busmap.get(bare.lower())
        return f"{new}{dot}{nodes}" if new else m.group(0)

    out = _BUSES_VALUE.sub(lambda m: m.group(1) + _ARRAY_BUS.sub(swap_bus, m.group(2)), out)
    return _BUS_VALUE.sub(swap, out)


def _new_buses(buses, unit):
    return {b: f"{b}_g{unit}" for b in buses}


def copy_elements(net, unit, lines, transformers, customers, busmap, shape=None):
    """The new elements of one unit: copies of lines, transformers and the Load lines of
    customers (bases), every name with _g<unit> and every bus through busmap. shape
    replaces the yearly loadshape of the new Load lines when given. Returns {"lines":
    [text], "transformers": [text], "loads": [{name, template, bus1, base, yearly}],
    "buses": {new bus: template bus}}; a bus mapped to an existing bus is no new bus."""
    existing = set(net["parent"]) | {net["source"]}
    out = {"lines": [copy_text(ln["text"], "line", new_name(ln["name"], unit), busmap) for ln in lines],
           "transformers": [copy_text(tr["text"], "transformer", new_name(tr["name"], unit), busmap)
                            for tr in transformers],
           "loads": [], "buses": {new: old for old, new in sorted(busmap.items()) if new.lower() not in existing}}
    for base in customers:
        for ld in net["customers"][base]["loads"]:
            bare, dot, nodes = ld["bus1"].partition(".")
            out["loads"].append({"name": new_name(ld["name"], unit), "template": ld["name"],
                                 "bus1": f"{busmap.get(bare.lower(), bare)}{dot}{nodes}",
                                 "base": new_name(base, unit), "yearly": shape or ld["yearly"]})
    return out


def copy_customer(net, base, unit, connection, at=None, own_transformer=False):
    """The new elements of a copy of customer base as unit (copy_elements), by its
    connection (customer_connection):
    - own_bus: the same Load lines on the customer's own bus, no other element;
    - mv_line or drop: a copy of its last line from the same upstream bus to a new bus;
    - transformer: a copy of its transformer on the same primary bus and of its secondary
      lines down to a new load bus.
    at names another bus for the upstream end (the primary side of the transformer, or
    the upstream bus of a medium-voltage line): a block's attach bus. With
    own_transformer a customer under a shared transformer is copied as if alone on it.
    Returns the elements with pattern and transformer (the name of the transformer
    that serves the copy, "" at medium voltage)."""
    pattern = connection["pattern"]
    c = net["customers"][base]
    if pattern == "own_bus":
        out = copy_elements(net, unit, [], [], [base], {})
        return dict(out, pattern=pattern, transformer="")
    if pattern == "mv_line" or (pattern == "drop" and not own_transformer):
        busmap = _new_buses([c["bus"]], unit)
        if at:
            busmap[connection["up"]] = at
        out = copy_elements(net, unit, [connection["line"]], [], [base], busmap)
        return dict(out, pattern=pattern,
                    transformer=connection["transformer"]["name"] if pattern == "drop" else "")
    tr = connection["transformer"]
    lower = [b for _, b, _, _ in tr["windings"][1:]] + [ln["b2"] for ln in connection["lines"]] \
        + [ln["b1"] for ln in connection["lines"]]
    busmap = _new_buses(sorted(set(lower) - {tr["windings"][0][1]}), unit)
    if at:
        busmap[tr["windings"][0][1]] = at
    out = copy_elements(net, unit, connection["lines"], [tr], [base], busmap)
    return dict(out, pattern="transformer", transformer=new_name(tr["name"], unit))


# ---------------------------------------------------------------------------
# Companions
# ---------------------------------------------------------------------------
def mean_floor_area(businesses, buildings):
    """The mean floor area of the circuit's businesses with a known building (buildings:
    {business: {"type", "sqft"}}), the excluded types included; 0 without one."""
    areas = [buildings[b]["sqft"] for b in businesses if b in buildings]
    return sum(areas) / len(areas) if areas else 0.0


def companion_candidates(k, businesses, buildings, excluded_types, mean):
    """(pool, bound) of the k-th companion of a circuit (k from 1): the sorted
    businesses with a known building, a type outside excluded_types and a floor area no
    larger than bound = k x mean, mean the circuit's mean floor area per business. The
    bound grows with k, so no copy is larger than the companion count times the mean."""
    bound = k * mean
    return sorted(b for b in businesses if b in buildings and buildings[b]["type"] not in excluded_types
                  and buildings[b]["sqft"] <= bound), bound


def companion_draw(k, pool, copied, seed):
    """The business the k-th companion copies: one seeded draw called companion_<k>
    among pool, leaving out the businesses in copied (those earlier companions copied)
    while any other is left. None for an empty pool."""
    fresh = [b for b in pool if b not in copied] or list(pool)
    return fresh[draw(f"companion_{k}", seed).randrange(len(fresh))] if fresh else None


# ---------------------------------------------------------------------------
# Laterals and blocks
# ---------------------------------------------------------------------------
def find_laterals(net):
    """The laterals of the feeder, sorted by root bus. A lateral is rooted at a
    medium-voltage bus fed by a line of fewer than three phases whose upstream bus (the
    tap) is the source bus or is fed by a three-phase line or by a three-phase
    regulator. It holds that first line and everything downstream of the root. Each:
    root, tap, lines, transformers, customers (bases), homes, businesses, others
    (customers that are neither), buses (root first), kind: homes (homes only), mixed,
    businesses (businesses only) or none, and regulator: True when it holds a regulator
    (one whose first winding sits on a bus of the lateral)."""
    out = []
    for root in sorted(net["parent"]):
        kind, el, tap = net["parent"][root]
        if kind != "line" or root not in net["mv"] or el["phases"] >= 3:
            continue
        up = net["parent"].get(tap)
        if not (tap == net["source"] or (up is not None and up[1]["phases"] == 3
                                         and (up[0] == "line" or is_regulator(up[1])))):
            continue
        buses = subtree(net, root)
        inside = set(buses)
        lines = [el] + [net["parent"][b][1] for b in buses[1:] if net["parent"][b][0] == "line"]
        trs = [t for t in net["transformers"] if t["windings"] and t["windings"][0][1] in inside]
        bases = sorted(b for b, c in net["customers"].items() if c["buses"] and all(x in inside for x in c["buses"]))
        seg = [net["customers"][b]["segment"] for b in bases]
        homes, biz = seg.count("residential"), seg.count("commercial")
        others = len(bases) - homes - biz
        if others or not (homes or biz):
            label = "none"
        else:
            label = "homes" if not biz else ("mixed" if homes else "businesses")
        out.append({"root": root, "tap": tap, "lines": lines, "transformers": trs, "customers": bases,
                    "homes": homes, "businesses": biz, "others": others, "buses": buses, "kind": label,
                    "regulator": any(is_regulator(t) for t in trs)})
    return out


def project(coords):
    """{bus: (x, y) in metres}: one equirectangular projection about the mean latitude
    of coords ({bus: (lon, lat) in degrees}), x east and y north of the mean position."""
    if not coords:
        return {}
    lon0 = sum(c[0] for c in coords.values()) / len(coords)
    lat0 = sum(c[1] for c in coords.values()) / len(coords)
    k = math.cos(math.radians(lat0))
    return {b: (EARTH_RADIUS_M * math.radians(lon - lon0) * k, EARTH_RADIUS_M * math.radians(lat - lat0))
            for b, (lon, lat) in coords.items()}


def load_centre(net, xy):
    """The mean position of the circuit's customers, one position per customer (its
    load bus; a customer whose bus has no coordinates is left out)."""
    points = [xy[c["bus"]] for c in net["customers"].values() if c["bus"] in xy]
    if not points:
        return None
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def lateral_radius(lateral, xy):
    """r of a lateral: the largest straight distance from its tap bus to any of its
    buses (0 without coordinates)."""
    if lateral["tap"] not in xy:
        return 0.0
    tx, ty = xy[lateral["tap"]]
    return max((math.hypot(xy[b][0] - tx, xy[b][1] - ty) for b in lateral["buses"] if b in xy), default=0.0)


def attach_bus(candidates, xy, centre, bearing, radius, earlier):
    """The outermost bus of candidates along bearing (radians, 0 east, counter-clockwise)
    from centre that is at least radius + r_i from every earlier attach bus (earlier:
    [(bus, r_i)]): the largest projection of (bus - centre) on the bearing, the first
    name on a tie. None when no bus qualifies."""
    ux, uy = math.cos(bearing), math.sin(bearing)
    best = None
    for b in sorted(candidates):
        if b not in xy or centre is None:
            continue
        if any(e not in xy or math.hypot(xy[b][0] - xy[e][0], xy[b][1] - xy[e][1]) < radius + r
               for e, r in earlier):
            continue
        score = (xy[b][0] - centre[0]) * ux + (xy[b][1] - centre[1]) * uy
        if best is None or score > best[0]:
            best = (score, b)
    return best[1] if best else None


def eligible_templates(laterals, homes_waiting, companions_waiting, placed, businesses, buildings,
                       excluded_types, mean, with_regulator=False):
    """The laterals that fit: homes-only and mixed laterals with no more homes than
    homes_waiting. A mixed lateral also needs no more businesses than companions_waiting,
    each with a known building, a type outside excluded_types and a floor area no larger
    than (placed + b) x mean, placed being the companions placed so far and b the
    lateral's businesses (companion_candidates at the index of its last business). A
    lateral that holds a regulator fits only with with_regulator (regulators.block_copies
    with_control); its copy then carries the regulator and its RegControl
    (copy_lateral)."""
    businesses = set(businesses)
    out = []
    for lat in laterals:
        if (lat["kind"] not in ("homes", "mixed") or lat["homes"] > homes_waiting
                or (lat["regulator"] and not with_regulator)):
            continue
        if lat["kind"] == "mixed":
            members = [b for b in lat["customers"] if b in businesses]
            pool, _ = companion_candidates(placed + lat["businesses"], members, buildings, excluded_types, mean)
            if lat["businesses"] > companions_waiting or len(pool) != lat["businesses"]:
                continue
        out.append(lat)
    return out


def plan_years(net, laterals, additions, home_order, businesses, buildings, excluded_types, seed,
               given_buses=(), with_regulator=False):
    """The growth plan of one circuit as a list of events in plan order, built year by
    year from additions (year_additions). The events of the first N years are the plan
    of horizon N apart from the waiting events, so plans nest across horizons.
    with_regulator goes to eligible_templates.

    Inside year t, in this order:
    1. The year's infill homes take the next positions of home_order (the seeded order
       of the homes; past its end it starts again).
    2. The year's infill companions are the next companions.
    3. The year's block homes join the waiting homes and its block companions the
       waiting companions. While a template is eligible (eligible_templates), block k (k
       runs over the whole plan) is one seeded draw (block_template_<k>) among them; it
       attaches at the next unused bus of given_buses, else at attach_bus along the
       seeded bearing block_bearing_<k>. A built block takes its homes and businesses
       off the waiting lists; the businesses of a mixed lateral are the next companions.
       A block without an attach bus is not built: its homes leave the waiting list and
       arrive as infill homes at the next positions, marked remainder.
    4. Once a block is built, the waiting companions are dealt to the built blocks: the
       j-th dealt companion of the circuit goes to block ((j - 1) mod B) + 1 in build
       order, B being the blocks built when it is dealt.
    At the end of the last year the homes still waiting arrive as infill homes and the
    companions still waiting as the next companions, both marked remainder and waiting.

    The k-th companion (k counts infill companions, the businesses of mixed laterals
    and dealt companions as they arrive) copies companion_draw of companion_candidates;
    an empty pool leaves it without a template.

    Events, each with year:
    - home: position, template, remainder, waiting;
    - companion: k, template (None when the pool is empty), block (the block it is dealt
      to, else None), pool (its size), bound, remainder, waiting;
    - block: k, template (the lateral), attach (None when not built), given,
      bearing_deg, radius_m, companions (the k of each business of a built mixed
      lateral, in the order of its customers)."""
    xy = project(net["coords"])
    centre = load_centre(net, xy)
    candidates = three_phase_mv_buses(net)
    given = [b.lower() for b in given_buses]
    for b in given:
        if b not in candidates:
            raise GrowthError(f"block_attach_buses: {b} is not a three-phase medium-voltage bus of the feeder")
    mean = mean_floor_area(businesses, buildings)
    events, built, earlier, copied = [], [], [], set()
    state = {"position": 0, "k": 0, "blocks": 0, "dealt": 0}

    def home(year, remainder=False, waiting=False):
        if not home_order:
            return
        state["position"] += 1
        events.append({"event": "home", "year": year, "position": state["position"],
                       "template": take(home_order, state["position"])[-1],
                       "remainder": remainder, "waiting": waiting})

    def companion(year, block=None, remainder=False, waiting=False):
        state["k"] += 1
        pool, bound = companion_candidates(state["k"], businesses, buildings, excluded_types, mean)
        template = companion_draw(state["k"], pool, copied, seed)
        if template is not None:
            copied.add(template)
        events.append({"event": "companion", "year": year, "k": state["k"], "template": template,
                       "block": block, "pool": len(pool), "bound": bound, "remainder": remainder,
                       "waiting": waiting})

    homes_waiting = companions_waiting = 0
    for year, add in enumerate(additions, start=1):
        for _ in range(add["infill_homes"]):
            home(year)
        for _ in range(add["infill_companions"]):
            companion(year)
        homes_waiting += add["block_homes"]
        companions_waiting += add["block_companions"]
        while True:
            fits = eligible_templates(laterals, homes_waiting, companions_waiting, state["k"], businesses,
                                      buildings, excluded_types, mean, with_regulator)
            if not fits:
                break
            state["blocks"] += 1
            n = state["blocks"]
            lat = fits[draw(f"block_template_{n}", seed).randrange(len(fits))]
            bearing = draw(f"block_bearing_{n}", seed).random() * 2.0 * math.pi
            radius = lateral_radius(lat, xy)
            block = {"event": "block", "year": year, "k": n, "template": lat, "given": False,
                     "bearing_deg": math.degrees(bearing), "radius_m": radius, "attach": None, "companions": []}
            if given:
                block["attach"], block["given"] = given.pop(0), True
            else:
                block["attach"] = attach_bus(candidates, xy, centre, bearing, radius, earlier)
            events.append(block)
            homes_waiting -= lat["homes"]
            if block["attach"] is None:
                for _ in range(lat["homes"]):
                    home(year, remainder=True)
                continue
            members = [b for b in lat["customers"] if b in set(businesses)]
            block["companions"] = [state["k"] + i for i in range(1, len(members) + 1)]
            state["k"] += len(members)
            copied.update(members)
            companions_waiting -= lat["businesses"]
            earlier.append((block["attach"], radius))
            built.append(block)
        while built and companions_waiting:
            state["dealt"] += 1
            companions_waiting -= 1
            companion(year, block=built[(state["dealt"] - 1) % len(built)]["k"])
    for _ in range(homes_waiting):
        home(len(additions), remainder=True, waiting=True)
    for _ in range(companions_waiting):
        companion(len(additions), remainder=True, waiting=True)
    return events


def read_regcontrols(texts):
    """The New RegControl statements of a feeder's texts ({file name: text}, every file
    in sorted order, ~ continuation lines joined): [{name, transformer (as written, ""
    when none is), text}]."""
    out = []
    for fname in sorted(texts):
        for st in _logical_lines(texts[fname]):
            m = re.match(r"(?i)^new\s+regcontrol\.(\S+)\s*(.*)$", st)
            if m:
                out.append({"name": m.group(1), "transformer": dict(_props(m.group(2))).get("transformer", ""),
                            "text": st})
    return out


def copy_lateral(net, lateral, unit, attach, regcontrols=()):
    """The new elements of a copy of lateral as unit, its tap on bus attach
    (copy_elements): every line, transformer and customer of the lateral, the new buses
    named <bus>_g<unit>. The first line keeps its own phase at the attach bus.
    regcontrols (read_regcontrols): every RegControl whose transformer= names a
    transformer of the lateral (any letter case) is copied under the name
    new_name(name, unit), with transformer= the copied transformer's new name and any bus=
    value through the bus map; every other property stays as written. The elements then
    hold regcontrols, the copied statements, when there is one. A regulator of the lateral
    that no RegControl names is copied alone, and one [growth] line names it."""
    busmap = _new_buses(lateral["buses"], unit)
    for tr in lateral["transformers"]:
        for _, b, _, _ in tr["windings"][1:]:
            busmap.setdefault(b, f"{b}_g{unit}")
    busmap[lateral["tap"]] = attach
    out = copy_elements(net, unit, lateral["lines"], lateral["transformers"], lateral["customers"], busmap)
    copies = []
    for tr in lateral["transformers"]:
        own = [rc for rc in regcontrols if rc["transformer"].lower() == tr["name"].lower()]
        for rc in own:
            text = copy_text(rc["text"], "regcontrol", new_name(rc["name"], unit), busmap)
            copies.append(re.sub(r"(?i)\b(transformer\s*=\s*)\S+", lambda m: m.group(1) + new_name(tr["name"], unit),
                                 text, count=1))
        if not own and is_regulator(tr):
            print(f"[growth] the regulator {tr['name']} of the lateral at {lateral['root']} has no RegControl; its "
                  f"copy {new_name(tr['name'], unit)} has none")
    if copies:
        out["regcontrols"] = copies
    return out


def shifted_coords(net, buses, shift_from=None, shift_to=None):
    """{new bus: (lon, lat)} for the new buses of one unit (buses: {new: template}): the
    template's coordinates, moved by (shift_to - shift_from) in degrees when both buses
    have coordinates. A template without coordinates gives none."""
    coords = net["coords"]
    dx = dy = 0.0
    if shift_from in coords and shift_to in coords:
        dx, dy = coords[shift_to][0] - coords[shift_from][0], coords[shift_to][1] - coords[shift_from][1]
    return {new: (coords[old][0] + dx, coords[old][1] + dy) for new, old in buses.items() if old in coords}


# ---------------------------------------------------------------------------
# Named loads
# ---------------------------------------------------------------------------
def path_impedance(net, bus, regulators=False):
    """The magnitude of the positive-sequence impedance (ohm) of the lines from the
    source bus to bus: the sum of z1 of each line's LineCode x its length. A regulator
    on the path adds nothing (path_lines), or, with regulators (regulators.path_impedance
    with_regulator), j x its regulator_reactance. None when the path crosses another
    transformer, a line without a LineCode impedance or, with regulators, a regulator
    without a kV or a kVA on its first winding."""
    lines = path_lines(net, net["source"], bus)
    if lines is None:
        return None
    total = 0j
    for ln in lines:
        code = net["linecodes"].get(ln["linecode"])
        if code is None or code["z1"] is None:
            return None
        total += code["z1"] * ln["length_m"] / UNIT_M.get(code["units"], 1.0)
    while regulators and bus != net["source"]:
        kind, element, bus = net["parent"][bus]
        if kind == "transformer":
            x = regulator_reactance(element)
            if x is None:
                return None
            total += 1j * x
    return abs(total)


def path_length_m(net, bus):
    """The length (m) of the lines from the source bus to bus, a regulator adding
    nothing; None across another transformer."""
    lines = path_lines(net, net["source"], bus)
    return None if lines is None else sum(ln["length_m"] for ln in lines)


def named_bus(net, rule, name, seed, bus=None, regulators=False):
    """The bus of a named load. bus, when given, must be a three-phase medium-voltage bus
    of the feeder. Else by rule: seeded, a draw called name among those buses; strongest,
    the one with the lowest path_impedance (regulators goes to it); weakest, the highest
    (the first name on a tie). Returns (bus, why). Raises GrowthError when the bus is not
    one of them or the feeder has none."""
    buses = three_phase_mv_buses(net)
    if bus is not None:
        if bus.lower() not in buses:
            raise GrowthError(f"bus {bus} is not a three-phase medium-voltage bus of the feeder")
        return bus.lower(), "given"
    if not buses:
        raise GrowthError("the feeder has no three-phase medium-voltage bus")
    if rule == "seeded":
        return buses[draw(name, seed).randrange(len(buses))], "seeded"
    z = [(path_impedance(net, b, regulators), b) for b in buses]
    z = [(v, b) for v, b in z if v is not None]
    if not z:
        raise GrowthError("no three-phase medium-voltage bus has a path impedance")
    return min(z, key=lambda t: (t[0] if rule == "strongest" else -t[0], t[1]))[1], rule


def named_candidates(final_rows, read_metadata, building_type, zone, state,
                     type_col="in.comstock_building_type", zone_col="in.building_america_climate_zone"):
    """({bldg_id as text: row}, source) for a named load of ComStock type building_type.
    The buildings of that type in the state's Phase 4 final commercial selection
    (final_rows; source phase4_selection). When it has none: the buildings of that type
    in the state's Phase 1 metadata whose climate zone is zone, the most common zone
    among the circuit's own businesses (source metadata_zone); read_metadata() returns
    (header, rows) and is called only then. Raises GrowthError naming the type, the state
    and the zone when the metadata has no zone column or no such building."""
    found = {str(int(float(r["bldg_id"]))): r for r in final_rows if r.get(type_col) == building_type}
    if found:
        return found, "phase4_selection"
    header, rows = read_metadata()
    if zone_col not in header:
        raise GrowthError(f"no {building_type} in the Phase 4 selection of {state}, and the Phase 1 metadata "
                          f"has no {zone_col} column to choose one in climate zone {zone!r}")
    found = {str(int(float(r["bldg_id"]))): r for r in rows
             if r.get(type_col) == building_type and r.get(zone_col) == zone}
    if not found:
        raise GrowthError(f"no building of type {building_type} in the Phase 4 selection of {state} and none "
                          f"in its Phase 1 metadata in climate zone {zone!r}")
    return found, "metadata_zone"


def named_building(candidates, name, seed):
    """A seeded draw called name among the sorted candidate building ids."""
    ids = sorted(candidates)
    return ids[draw(name, seed).randrange(len(ids))]


def named_template(net, peak_kw, tr_map, served):
    """The existing business whose SMART-DS kW is closest to peak_kw and whose connection
    a new load can copy (mv_line, drop or transformer), with that connection; the first
    name on a tie. None when the feeder has no such business."""
    best = None
    for base in sorted(net["customers"]):
        c = net["customers"][base]
        if c["segment"] != "commercial":
            continue
        conn = customer_connection(net, base, tr_map, served)
        if conn["pattern"] == "own_bus":
            continue
        gap = abs(c["kw"] - peak_kw)
        if best is None or gap < best[0]:
            best = (gap, base, conn)
    return (best[1], best[2]) if best else None


def pick_transformer(net, like, peak_kva):
    """The transformer of a named load: among the feeder's transformers with the phases
    and winding voltages of transformer like, the first (by name) of the smallest kVA at
    or above peak_kva; when none is large enough, of the largest kVA. Returns
    (transformer, large_enough)."""
    key = (like["phases"], tuple(w[2] for w in like["windings"]))
    same = sorted((t for t in net["transformers"]
                   if (t["phases"], tuple(w[2] for w in t["windings"])) == key and t["windings"][0][3]),
                  key=lambda t: (t["windings"][0][3], t["name"]))
    for t in same:
        if t["windings"][0][3] >= peak_kva:
            return t, True
    largest = [t for t in same if t["windings"][0][3] == same[-1]["windings"][0][3]]
    return largest[0], False


def mv_new_line(net, mv_lines, peak_kva, default_length_m):
    """The LineCode and length of the new line of a named load that connects at medium
    voltage. mv_lines: the lines that feed the feeder's own medium-voltage customers.
    - LineCode: among the LineCodes of the feeder's three-phase medium-voltage lines
      longer than 1 m whose name holds _OH_ (overhead in SMART-DS names), the one with
      the smallest normamps at or above the load's peak current, peak_kva / (sqrt(3) x
      base kV), the first name on a tie; the largest when none is at or above it
      (carries False); over all three-phase medium-voltage LineCodes of lines longer
      than 1 m when the feeder has no overhead one.
    - Length: the median length of mv_lines (rule feeder_median); on a feeder without a
      medium-voltage customer, default_length_m (rule named_load_mv_line_m).
    Returns {linecode (as written in Lines.dss), normamps, peak_amps, carries, length_m,
    length_rule}. Raises GrowthError when the feeder has no rated three-phase
    medium-voltage LineCode or no base kV."""
    if not net["base_kv"]:
        raise GrowthError("Master.dss gives no basekV for a load at medium voltage")
    written = {}
    for ln in net["lines"]:
        code = net["linecodes"].get(ln["linecode"])
        if (ln["phases"] == 3 and ln["length_m"] > 1.0 and ln["b1"] in net["mv"] and ln["b2"] in net["mv"]
                and code and code["normamps"] is not None):
            written.setdefault(ln["linecode"], re.search(r"(?i)\blinecode=(\S+)", ln["text"]).group(1))
    codes = sorted((net["linecodes"][c]["normamps"], c) for c in written)
    overhead = [t for t in codes if "_oh_" in t[1]]
    codes = overhead or codes
    if not codes:
        raise GrowthError("the feeder has no rated three-phase medium-voltage LineCode for a load at medium voltage")
    peak_amps = peak_kva / (math.sqrt(3.0) * net["base_kv"])
    fits = [t for t in codes if t[0] >= peak_amps]
    amps, code = fits[0] if fits else [t for t in codes if t[0] == codes[-1][0]][0]
    lengths = [ln["length_m"] for ln in mv_lines]
    return {"linecode": written[code], "normamps": amps, "peak_amps": peak_amps, "carries": bool(fits),
            "length_m": statistics.median(lengths) if lengths else float(default_length_m),
            "length_rule": "feeder_median" if lengths else "named_load_mv_line_m"}


def mv_load_line(template_text, name, bus1, kv, kw, kvar, shape):
    """The Load line of a customer connected at medium voltage with no line to copy: one
    three-phase wye load at kv on bus1, with the model, Vminpu and Vmaxpu of
    template_text (a New Load line) and daily loadshape shape."""
    d = {k.lower(): v for k, v in _PROP_RE.findall(template_text)}
    kept = " ".join(f"{key}={d[key.lower()]}" for key in ("Vminpu", "Vmaxpu", "model") if key.lower() in d)
    return (f"New Load.{name} conn=wye bus1={bus1} kV={format(kv, '.10g')} {kept} kW={format(kw, '.10g')} "
            f"kvar={format(kvar, '.10g')} Phases=3 daily={shape}")


def connect_named(net, unit, template, connection, bus, peak_kva, shape, mv_lines=(), mv_line_m=None):
    """The new elements of a named load as unit on bus (a three-phase medium-voltage
    bus), with the Load lines of template under loadshape shape:
    - a medium-voltage template: a copy of its line from bus to a new load bus;
    - a template behind a service transformer: a transformer (pick_transformer on
      peak_kva) from bus and a copy of the template's secondary lines to a new load bus;
    - the same template when no transformer is large enough: pattern mv_new, one new
      three-phase line (mv_new_line with mv_lines and mv_line_m) from bus to a new bus
      of its own and one three-phase Load line at the circuit's base kV on that bus
      (nodes .1.2.3). Its load entry carries mv_new (the kV) and templates (the
      template's Load lines, whose kW and kvar it carries whole).
    Returns the elements with pattern, transformer, transformer_kva, large_enough and
    mv (the dict of mv_new_line, None for another pattern)."""
    c = net["customers"][template]
    if connection["pattern"] == "mv_line":
        busmap = _new_buses([c["bus"]], unit)
        busmap[connection["up"]] = bus
        out = copy_elements(net, unit, [connection["line"]], [], [template], busmap, shape=shape)
        return dict(out, pattern="mv_line", transformer="", transformer_kva=None, large_enough=True, mv=None)
    like = connection["transformer"]
    lines, top = connection["lines"], like["windings"][-1][1]
    donor, enough = pick_transformer(net, like, peak_kva)
    if not enough:
        mv = mv_new_line(net, mv_lines, peak_kva, mv_line_m)
        new_bus = f"{c['bus']}_g{unit}"
        line = (f"New Line.{new_name(connection['line']['name'], unit)} Units=m Length={mv['length_m']!r} "
                f"bus1={bus}.1.2.3 bus2={new_bus}.1.2.3 switch=n enabled=y phases=3 Linecode={mv['linecode']}")
        first = c["loads"][0]
        load = {"name": new_name(template, unit), "template": first["name"], "bus1": f"{new_bus}.1.2.3",
                "base": new_name(template, unit), "yearly": shape, "mv_new": net["base_kv"],
                "templates": [ld["name"] for ld in c["loads"]]}
        return {"lines": [line], "transformers": [], "loads": [load], "buses": {new_bus: c["bus"]},
                "pattern": "mv_new", "transformer": "", "transformer_kva": None, "large_enough": False, "mv": mv}
    busmap = _new_buses(sorted({ln["b1"] for ln in lines} | {ln["b2"] for ln in lines}), unit)
    out = copy_elements(net, unit, lines, [], [template], busmap, shape=shape)
    # the new transformer feeds the upstream end of the copied secondary from bus
    tr_buses = {donor["windings"][0][1]: bus}
    for _, b, _, _ in donor["windings"][1:]:
        tr_buses[b] = busmap[top]
    name = new_name(donor["name"], unit)
    out["transformers"] = [copy_text(donor["text"], "transformer", name, tr_buses)]
    return dict(out, pattern="transformer", transformer=name, transformer_kva=donor["windings"][0][3],
                large_enough=enough, mv=None)


# ---------------------------------------------------------------------------
# Helpers for the phases that read the plan
# ---------------------------------------------------------------------------
def label_new_shapes(names, shares, seed):
    """{loadshape: baseline | dm | un} for the loadshapes new to a feeder, in one draw of
    their own (heating_new_shapes on seed): the shares normalized as in
    heating_split.split_heating, counts by largest remainder, no minimum of one."""
    names = sorted(names)
    p = {k: float(shares.get(k, 0.0)) for k in ("baseline", "dm", "un")}
    total = sum(p.values())
    p = {"baseline": 1.0, "dm": 0.0, "un": 0.0} if total <= 0 else {k: v / total for k, v in p.items()}
    raw = {k: v * len(names) for k, v in p.items()}
    cnt = {k: int(math.floor(v)) for k, v in raw.items()}
    frac = sorted(((raw[k] - cnt[k], k) for k in raw), reverse=True)
    for i in range(len(names) - sum(cnt.values())):
        cnt[frac[i % len(frac)][1]] += 1
    labels = ["baseline"] * cnt["baseline"] + ["dm"] * cnt["dm"] + ["un"] * cnt["un"]
    rng = draw("heating_new_shapes", seed)
    rng.shuffle(labels)
    rng.shuffle(names)
    return dict(zip(names, labels))


def pick_new(items, share, name, seed):
    """round(share x n) of the sorted items in the seeded order of the draw called name:
    the hosts among new loads. No minimum of one."""
    order = seeded_order(items, name, seed)
    return order[:int(round(float(share) * len(order)))]


def der_use_factor(base, factor, new_customers, resize):
    """The factor on the annual electricity use that sizes the PV and storage of host
    base (der_resize_with_growth in growth.yaml). A host among new_customers is sized on
    its own use, its building's annual use x factor. An existing host keeps the size of
    a run without growth (1) unless resize is true (factor)."""
    return float(factor) if resize or base in new_customers else 1.0


def customer_factors(feeder_plan, bases, segment_of):
    """{base: factor on kW and kvar of its Load lines} for the existing customers bases
    of one feeder of the plan: the factor of its segment, 1 for a customer of neither
    segment, the load_factors value for a named customer, and 1 for a stretched customer
    (peak_factor), whose own loadshape carries its growth."""
    out = {}
    for base in bases:
        entry = feeder_plan["load_factors"].get(base)
        if entry is None:
            out[base] = feeder_plan["factors"].get(segment_of(base), 1.0)
        else:
            out[base] = 1.0 if entry.get("peak_factor") is not None else float(entry["factor"])
    return out
