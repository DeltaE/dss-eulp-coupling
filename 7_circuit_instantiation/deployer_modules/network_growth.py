# -*- coding: utf-8 -*-
"""
network_growth.py
-----------------
Network growth driven by the planning limits (network_growth in configs/growth.yaml), as
functions that need no OpenDSS. Load growth grows the load of a planning year; network
growth is expansion (a new feeder from the substation) and reinforcement (a rebuilt
line or second circuits, a replaced or parallel service transformer, a line voltage
regulator), with phase rebalancing as a first step that builds nothing. The planning
limits tell the run when the network has to grow. The run reports quantities, no costs.

The Phase 7 deploy solves the grown circuit as built (round 0), then, up to max_rounds
times, tests the limits on the last solve, applies the first step that applies and
solves again. This module holds the rules; the deploy holds the loop and the solves.

- The catalog (inventory, build_catalog, substation_record): the LineCodes and the
  transformer ratings a step may use, read from SMART-DS feeder folders by phase growth.
- The network (read_network): growth.read_feeder on the .dss files of
  ModifiedCircuitData. A regulator (growth.is_regulator: a SMART-DS voltage regulator
  or a line regulator of network growth) is crossed like a line, so the buses behind it
  stay at medium voltage. A regulator is never a service transformer, and a head on a
  regulator gets no new feeder and no rebuilt line (head_groups, next_step).
- The tests (lines_over, transformers_over, head_groups, customers_under).
- The steps (next_step): rebalance_moves, new_feeder_choice, reconductor_items,
  transformer_items, regulator_choice. Each returns items in the built format.
- The statements (apply_items): what each item writes into the .dss files.
- The built format (read_built, write_built) and the substation units
  (substation_units).

Nothing is drawn: every choice is computed from the last solve, the catalog and the
settings, with ties broken by element name.

ASSUMPTION: the steps run in the fixed order of the settings, capacity before voltage,
so the result is a rule-based plan and no least-cost plan; another order builds other
equipment.
"""

import math
import re

import yaml

import growth
from growth import _PROP_RE, _logical_lines
from planning_limits import SHORT_LINE_M, head_classes, head_lines

STEPS = ("new_feeder", "reconductor", "service_transformer", "regulator")
ITEM_STEPS = ("rebalance_phases",) + STEPS
BUILT_FILE = "network_growth_built.yaml"
CATALOG_FILE = "network_catalog.json"

# Impedance values of a line regulator, one single-phase two-winding transformer per
# phase: XHL 0.01 percent and %LoadLoss 0.01, the values of the regulator of the IEEE 13
# node test case distributed with OpenDSS,
# https://github.com/dss-extensions/electricdss-tst/blob/master/Version8/Distrib/IEEETestCases/13Bus/IEEE13Nodeckt.dss
# ASSUMPTION: a line regulator takes those two values, the ampacity of its line and the
# vreg, band and ptratio of the substation regulator of its SMART-DS topology, with the
# OpenDSS default taps and delays and no line-drop compensation. A regulator with
# line-drop compensation holds a different voltage downstream.
REGULATOR_XHL = 0.01
REGULATOR_LOADLOSS = 0.01

_NEW_RE = re.compile(r"(?i)^\s*new\s+(\w+)\.(\S+)")
_BUS_TOKEN = re.compile(r"(?i)(?<![\w%])(bus1|bus2|bus)(\s*=\s*)(\S+)")
_NG_SUFFIX = re.compile(r"_ng(\d+)$")
_REG_NAME = re.compile(r"(?i)^ngreg(\d+)_(\d+)$")
_REG_BUS = re.compile(r"_ngreg\d+$")
_EXPRESS = "ng_express_"


class NetworkGrowthError(Exception):
    """An item cannot be built. The calling script prints [FAIL] and exits 1."""


# ---------------------------------------------------------------------------
# Names and small helpers
# ---------------------------------------------------------------------------
def construction(code):
    """OH, UG or the empty text for a LineCode name.
    ASSUMPTION: SMART-DS names a LineCode with _OH_ for overhead and _UG_ for underground
    construction; a name with neither shows no construction, and a line of such a code
    is never rebuilt with another code. A feeder with other names gets second circuits
    where a larger code would do."""
    low = code.lower()
    return "OH" if "_oh_" in low else ("UG" if "_ug_" in low else "")


def line_key(phases, level, code):
    """The catalog class of a line: <phases>|<mv or lv>|<OH, UG or empty>."""
    return f"{phases}|{level}|{construction(code)}"


def transformer_key(tr):
    """The catalog class of a transformer (growth.read_feeder): <phases>|<kV of each
    winding, joined by commas>."""
    return f"{tr['phases']}|{','.join(repr(float(w[2])) for w in tr['windings'])}"


def is_regulator(name):
    """True for the name of a transformer of a line regulator built by network growth
    (it numbers the next one; growth.is_regulator tells any regulator)."""
    return bool(_REG_NAME.match(name))


def base_name(name):
    """The element a second circuit or parallel unit <name>_ng<j> belongs to."""
    return _NG_SUFFIX.sub("", name)


def _nodes(spec, phases):
    """The phase nodes of a bus value as written (a.1.2.3 -> [1, 2, 3]); 1 to phases
    when none is written. Node 0 is left out."""
    parts = [int(p) for p in str(spec).split(".")[1:] if p.isdigit() and int(p) != 0]
    return parts or list(range(1, int(phases) + 1))


def _swap_node(spec, old, new):
    bare, *nodes = spec.split(".")
    return ".".join([bare] + [str(new) if n == str(old) else n for n in nodes])


def _level(net, ln):
    return "mv" if ln["b1"] in net["mv"] and ln["b2"] in net["mv"] else "lv"


# ---------------------------------------------------------------------------
# The network
# ---------------------------------------------------------------------------
def read_network(text):
    """growth.read_feeder on text, the .dss files of one circuit joined. Its
    medium-voltage buses (mv) are also reached across every regulator
    (growth.is_regulator), those network growth built included, so a line beyond a
    regulator stays a medium-voltage line."""
    net = growth.read_feeder({key: text for key in ("lines.dss", "transformers.dss", "loads.dss", "master.dss",
                                                    "linecodes.dss", "buscoords.dss")})
    for ln in net["lines"]:  # the LineCode as written in the Line statement
        ln["text_code"] = (re.search(r"(?i)\blinecode\s*=\s*(\S+)", ln["text"]) or [None, ""])[1]
    net["line_of"] = {ln["name"].lower(): ln for ln in net["lines"]}
    net["transformer_of"] = {tr["name"].lower(): tr for tr in net["transformers"]}
    return net


def phase_table(net, currents):
    """{line, lower case: {phase node: amps}} from {line, lower case: [amps of each
    conductor of terminal 1]}: conductor i of a line is on the i-th node of its bus1."""
    out = {}
    for name, amps in currents.items():
        ln = net["line_of"].get(name)
        if ln is not None:
            out[name] = dict(zip(_nodes(ln["bus1"], ln["phases"]), amps))
    return out


def orientation(net, ln):
    """(upstream bus, downstream bus) of a line of the tree walked from the source bus;
    None for a disabled line or one that closes a loop (a second circuit takes the
    orientation of the line beside it)."""
    for up, down in ((ln["b1"], ln["b2"]), (ln["b2"], ln["b1"])):
        step = net["parent"].get(down)
        if step is not None and step[2] == up and (step[1] is ln or (step[0] == "line" and ln["enabled"])):
            return up, down
    return None


def circuits(net, ln):
    """The enabled lines of the branch of ln: ln and every line between the same two
    buses (its second circuits, or the line they were added to), the line whose name
    carries no _ng<j> suffix first."""
    pair = {ln["b1"], ln["b2"]}
    members = [x for x in net["lines"] if x["enabled"] and {x["b1"], x["b2"]} == pair]
    return sorted(members, key=lambda x: (base_name(x["name"].lower()) != x["name"].lower(), x["name"].lower()))


def mv_path(net, bus):
    """The lines from the source bus to the medium-voltage bus bus, source side first,
    passing a regulator (growth.is_regulator); None when the walk crosses another
    transformer."""
    out = []
    while bus != net["source"]:
        step = net["parent"].get(bus)
        if step is None or (step[0] != "line" and not growth.is_regulator(step[1])):
            return None
        if step[0] == "line":
            out.append(step[1])
        bus = step[2]
    return out[::-1]


def path_length_m(net, bus):
    """The length (m) of mv_path to bus; None without a path."""
    path = mv_path(net, bus)
    return None if path is None else sum(ln["length_m"] for ln in path)


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------
def inventory(texts):
    """What one SMART-DS feeder folder gives a catalog. texts: {file name, lower case:
    text} as growth.read_feeder takes them. Returns
    - uses: {line_key: [LineCode, lower case]} of the enabled lines longer than 1 m, the
      level by the medium-voltage set of growth.read_feeder (a regulator is crossed);
    - linecodes: {LineCode, lower case: {linecode (as written), normamps, statement}} of
      every rated LineCode the folder defines;
    - transformers: {transformer_key: [{kva, statement}]}, one statement per rating, the
      first in file order."""
    net = growth.read_feeder(texts)
    codes = {}
    for st in _logical_lines(texts.get("linecodes.dss", "")):
        m = re.match(r"(?i)^new\s+linecode\.(\S+)", st)
        if not m:
            continue
        d = {k.lower(): v for k, v in _PROP_RE.findall(st)}
        if "normamps" in d:
            codes.setdefault(m.group(1).lower(), {"linecode": m.group(1), "normamps": float(d["normamps"]),
                                                  "statement": st})
    uses = {}
    for ln in net["lines"]:
        if ln["enabled"] and ln["length_m"] > SHORT_LINE_M and ln["linecode"] in codes:
            uses.setdefault(line_key(ln["phases"], _level(net, ln), ln["linecode"]), set()).add(ln["linecode"])
    transformers = {}
    for tr in net["transformers"]:
        kva = tr["windings"][0][3] if tr["windings"] else None
        if kva and all(w[2] is not None for w in tr["windings"]):
            ratings = transformers.setdefault(transformer_key(tr), [])
            if all(r["kva"] != kva for r in ratings):
                ratings.append({"kva": float(kva), "statement": tr["text"]})
    return {"uses": {key: sorted(names) for key, names in uses.items()}, "linecodes": codes,
            "transformers": transformers}


def build_catalog(own, others):
    """The catalog of one circuit. own: the inventory of its own feeder folder; others:
    the inventories of the other feeder folders of the scope, in sorted folder order.
    Returns {"lines": {line_key: [{linecode, normamps, statement}], by normamps then
    name}, "transformers": {transformer_key: [{kva, statement}], by kVA}}. A LineCode is
    in a class when a line longer than 1 m of any folder of the scope uses it there. A
    statement comes from the circuit's own feeder when it defines the name or rating,
    else from the first folder in sorted order that does."""
    scope = [own] + list(others)
    lines, transformers = {}, {}
    for inv in scope:
        for key, names in inv["uses"].items():
            for name in names:
                entry = next((x["linecodes"][name] for x in scope if name in x["linecodes"]), None)
                if entry is not None:
                    lines.setdefault(key, {})[name] = entry
        for key, ratings in inv["transformers"].items():
            for r in ratings:
                transformers.setdefault(key, {}).setdefault(r["kva"], r)
    return {"lines": {key: sorted(v.values(), key=lambda e: (e["normamps"], e["linecode"].lower()))
                      for key, v in sorted(lines.items())},
            "transformers": {key: [v[kva] for kva in sorted(v)] for key, v in sorted(transformers.items())}}


def substation_record(texts):
    """The substation of a topology from the .dss texts of its substation folder:
    {"transformers": [{name, kva}], "regcontrol": {vreg, band, ptratio} of its first
    RegControl, or None}."""
    net = growth.read_feeder({"transformers.dss": texts.get("transformers.dss", ""),
                              "master.dss": "New Circuit.x bus1=x"})
    units = [{"name": tr["name"], "kva": float(tr["windings"][0][3])} for tr in net["transformers"]
             if tr["windings"] and tr["windings"][0][3]]
    reg = None
    for name in sorted(texts):
        for st in _logical_lines(texts[name]):
            if re.match(r"(?i)^new\s+regcontrol\.", st) and reg is None:
                d = {k.lower(): v for k, v in _PROP_RE.findall(st)}
                if all(k in d for k in ("vreg", "band", "ptratio")):
                    reg = {k: float(d[k]) for k in ("vreg", "band", "ptratio")}
    return {"transformers": units, "regcontrol": reg}


def substation_units(record, peak_kva, over, sizing_percent, build):
    """The unit columns of one row of substation_limits.csv, as records (the power flow
    is unchanged): units_existing and unit_kva (the transformers of the substation
    folder; a new unit copies the largest), units_in_all = ceil(peak_kva / (unit_kva x
    sizing_percent / 100)), at least units_existing, when the row is over its limit,
    else units_existing; units_added the difference. With build false (mode "off")
    units_in_all and units_added stay empty.
    ASSUMPTION: a new substation unit copies the largest transformer of the substation
    folder and takes the same substation_limit_percent and sizing_percent; the
    substation transformer is in no solved circuit, so its losses and its regulator are
    outside the power flow."""
    ratings = [u["kva"] for u in (record or {}).get("transformers", [])]
    out = {"units_existing": len(ratings), "unit_kva": max(ratings) if ratings else None,
           "units_in_all": None, "units_added": None}
    if build and ratings:
        total = len(ratings)
        if over:
            total = max(total, int(math.ceil(peak_kva / (max(ratings) * sizing_percent / 100.0))))
        out.update({"units_in_all": total, "units_added": total - len(ratings)})
    return out


# ---------------------------------------------------------------------------
# The tests on the last solve
# ---------------------------------------------------------------------------
def lines_over(line_rows, limit):
    """The rows of planning_limits.line_rows over limit percent of the normamps of their
    LineCode. A line of 1 m or less, a disabled line and a line without a rating are
    never tested."""
    return [r for r in line_rows if r["enabled"] and not r["short"] and r["loading_percent"] is not None
            and r["loading_percent"] > limit]


def transformers_over(transformer_rows, limit):
    """The rows of planning_limits.transformer_rows over limit percent of their kVA."""
    return [r for r in transformer_rows if r["loading_percent"] is not None and r["loading_percent"] > limit]


def customers_under(load_min, low):
    """{customer: lowest voltage} of the customers with any step of any Load line below
    low. load_min: {load name: lowest per-unit voltage over all steps}, EV legs left out;
    a customer is a load name without its _<n> leg suffix."""
    out = {}
    for load, v in load_min.items():
        if v < low:
            base = growth._base(load)
            out[base] = min(v, out.get(base, v))
    return out


def head_measure(row, metric):
    """The measure of a head row (planning_limits.head_rows) in percent: under
    largest_phase its largest phase current over the normamps of its LineCode, under
    three_phase_kva its kVA over normamps x base kV x sqrt(3)."""
    return row["phase_percent"] if metric == "largest_phase" else row["kva_percent"]


def head_groups(net, head_rows, phase_amps, metric):
    """The heads as groups, one per pair of buses: a head line with its second circuits
    carries its current over several lines, and the group is tested as one element with
    the summed current and the summed rating. Each: k (the lowest head number), heads
    (their numbers), lines (their names), code (LineCode of the first), up, down (the
    bus the group feeds), normamps (summed), step (the step of the largest phase current
    of the first), amps ({node: summed amps at that step}), percent (the highest measure
    of its heads). head_rows: planning_limits.head_rows; phase_amps: {head number: {line,
    lower case: {node: amps}}} at each head's step. A head without a rating or outside
    the tree is left out.
    A head on a regulator (growth.is_regulator) is a group of its own with regulator
    True: up is the bus of its first winding, down the bus of its second winding, code
    None, and its normamps and amps those of its row (amps_1 to amps_3)."""
    groups = {}
    for row in sorted(head_rows, key=lambda r: r["head"]):
        ln = net["line_of"].get(str(row["line"]).lower())
        tr = None if ln else net["transformer_of"].get(str(row["line"]).lower())
        if tr is not None and growth.is_regulator(tr):
            up, down = tr["windings"][0][1], tr["windings"][1][1]
            step = net["parent"].get(down)
            if step is None or step[1] is not tr or not row["normamps"] or head_measure(row, metric) is None:
                continue
            groups[(up, down)] = {"k": row["head"], "heads": [row["head"]], "lines": [tr["name"]], "code": None,
                                  "up": up, "down": down, "normamps": row["normamps"], "step": row["phase_step"],
                                  "percent": head_measure(row, metric), "regulator": True,
                                  "amps": {p: row[f"amps_{p}"] or 0.0 for p in (1, 2, 3)}}
            continue
        way = orientation(net, ln) if ln else None
        if way is None or not row["normamps"] or head_measure(row, metric) is None:
            continue
        g = groups.setdefault(way, {"k": row["head"], "heads": [], "lines": [], "code": ln["linecode"],
                                    "up": way[0], "down": way[1], "normamps": 0.0, "step": row["phase_step"],
                                    "percent": 0.0})
        g["heads"].append(row["head"])
        g["lines"].append(ln["name"])
        g["normamps"] += row["normamps"]
        g["percent"] = max(g["percent"], head_measure(row, metric))
    out = sorted(groups.values(), key=lambda g: g["k"])
    for g in out:
        if g.get("regulator"):
            continue
        at = phase_amps[g["k"]]
        g["amps"] = {p: sum(at.get(name.lower(), {}).get(p, 0.0) for name in g["lines"]) for p in (1, 2, 3)}
    return out


def _larger_codes(catalog, row):
    """The catalog codes of the class of a line row with a larger normamps, by normamps
    then name; none for a construction that is not shown."""
    if not construction(row["linecode"]) or not row["normamps"]:
        return []
    return [e for e in catalog["lines"].get(line_key(row["phases"], row["level"], row["linecode"]), [])
            if e["normamps"] > row["normamps"]]


def _fed_by(net, group):
    """The buses fed by a head group: its downstream bus and everything below it."""
    return set(growth.subtree(net, group["down"]))


# ---------------------------------------------------------------------------
# Step: phase rebalancing
# ---------------------------------------------------------------------------
def single_phase_laterals(net):
    """The laterals a rebalancing may move: those of growth.find_laterals whose
    medium-voltage lines are all single-phase on one phase node, a lateral that holds a
    regulator left out (a move rewrites bus=, bus1= and bus2= values only, and a
    regulator statement may name its buses with buses=). Each lateral gains node,
    mv_lines, first (its first line) and firsts (the names of the first line and of its
    second circuits, which together carry the lateral's current)."""
    out = []
    for lat in growth.find_laterals(net):
        if lat["regulator"]:
            continue
        mv_lines = [ln for ln in lat["lines"] if ln["b1"] in net["mv"] and ln["b2"] in net["mv"]]
        nodes = {tuple(_nodes(ln["bus1"], ln["phases"])) for ln in mv_lines}
        if mv_lines and all(ln["phases"] == 1 for ln in mv_lines) and len(nodes) == 1 and len(next(iter(nodes))) == 1:
            out.append(dict(lat, node=next(iter(nodes))[0], mv_lines=mv_lines, first=lat["lines"][0],
                            firsts=[x["name"] for x in circuits(net, lat["lines"][0])]))
    return out


def rebalance_moves(net, groups, phase_amps):
    """The laterals to move, as items {step, lateral, to_phase}. Per head group, at the
    step of its largest phase current, with the candidates the single-phase laterals it
    feeds and c the current of a lateral's first line at that step: take the heaviest
    phase H and the lightest phase L of the head; among the laterals on H, move to L the
    one with the smallest max(I_H - c, I_L + c), the first root bus on a tie, when that
    lowers the largest of the three head phase currents; repeat until no move does. The
    arithmetic adds current magnitudes; the solve that follows gives the result.
    ASSUMPTION: a single-phase lateral can be moved to another phase at its tap with no
    change to its lines or transformers. The rule moves whole laterals only and balances
    the head at its peak step, so other steps of the window can end less balanced."""
    items = []
    for g in groups:
        fed = _fed_by(net, g)
        amps = dict(g["amps"])
        at = phase_amps[g["k"]]
        laterals = []
        for lat in single_phase_laterals(net):
            if lat["tap"] in fed:
                c = sum(at.get(name.lower(), {}).get(lat["node"], 0.0) for name in lat["firsts"])
                if c:
                    laterals.append({"root": lat["root"], "node": lat["node"], "from": lat["node"], "c": c})
        while True:
            heavy = max(sorted(amps), key=lambda p: amps[p])
            light = min(sorted(amps), key=lambda p: amps[p])
            other = max(amps[p] for p in amps if p not in (heavy, light)) if len(amps) > 2 else 0.0
            best = None
            for lat in sorted(laterals, key=lambda x: x["root"]):
                if lat["node"] != heavy:
                    continue
                value = max(amps[heavy] - lat["c"], amps[light] + lat["c"])
                if max(value, other) < amps[heavy] and (best is None or value < best[0]):
                    best = (value, lat)
            if best is None or heavy == light:
                break
            lat = best[1]
            amps[heavy] -= lat["c"]
            amps[light] += lat["c"]
            lat["node"] = light
        for lat in sorted(laterals, key=lambda x: x["root"]):
            if lat["node"] != lat["from"]:
                items.append({"step": "rebalance_phases", "lateral": lat["root"], "to_phase": lat["node"],
                              "_peak": lat["c"], "_detail": f"head {g['k']} step {g['step']} from phase {lat['from']}"})
    return items


# ---------------------------------------------------------------------------
# Step: a new feeder
# ---------------------------------------------------------------------------
def watched_lines(text):
    """The lines, lower case, that a CapControl or a StorageController watches (element=
    or monitoredobj=Line.<name>). Such a line is never the open point of a new feeder."""
    out = set()
    for st in _logical_lines(text):
        if re.match(r"(?i)^new\s+(capcontrol|storagecontroller|regcontrol)\.", st):
            out.update(m.lower() for m in re.findall(r"(?i)\b(?:element|monitoredobj)\s*=\s*line\.(\S+)", st))
    return out


def new_feeder_choice(net, groups, line_rows, phase_amps, catalog, ng, limits, express, state, watched=()):
    """One new feeder, as ([item], [note]). The step applies to a head group that is
    over its limit while the catalog holds no larger code for its line, or that feeds a
    stuck line: a three-phase medium-voltage line longer than 1 m over its limit with no
    larger code of its phases, level and construction. With several such groups the one
    with the highest measure is taken. At the step of its largest phase current:
    1. What must be lost on phase p: the largest, over the head (when over) and the
       stuck lines, of the element's current on p less its limit percent of its normamps,
       floor 0.
    2. Candidates under open_point switch: the closed three-phase medium-voltage lines
       the head feeds with switch=y or a length of 1 m or less, the head lines and the
       lines a control watches left out (a line with second circuits is one candidate
       with the sum of their currents), that lie beyond every stuck line and whose
       current on every phase is at least what must be lost on it. With no candidate,
       the stuck line farthest from the source bus leaves the set and the search runs
       again, until candidates exist or the set is empty; an empty set with a head that
       is not over gives no candidate.
    3. The candidates whose largest phase current is at most sizing_percent of the
       normamps of the express LineCode; if none, those within head_limit_percent. The
       choice has the smallest max(largest phase of the old head after the transfer over
       its normamps, largest phase of the new head over its normamps); on a tie the
       shorter express line, then the name.
    Under switch a head without a choice is left out from then on (state no_feeder) and
    its stuck lines go to the reconductor step. Under switch_then_bus the search runs
    again over the three-phase medium-voltage buses the head feeds, each standing for
    the line that feeds it; if none passes step 3, the candidate of step 2 with the
    smallest max of step 3 is taken whatever the limits (the buses beyond the stuck
    lines when step 2 has none), and a later round may build another feeder. Under bus
    the candidates are the buses from the start.
    express: {linecode, normamps} of the head line of round 0, the code of every express
    line; None when head 1 is a regulator. The step never applies to a head on a
    regulator, nor to any head when express is None.
    ASSUMPTION: the new feeder is one express line of the head's LineCode along the
    existing route from the substation bus to the open point, and it serves nothing on
    the way. A real route can be longer, and the voltage beyond the open point then
    lower."""
    notes = []
    head_names = {name.lower() for g in groups for name in g["lines"]}
    over_rows = lines_over(line_rows, limits["line_limit_percent"])
    stuck_rows = [r for r in over_rows if r["phases"] == 3 and r["level"] == "mv"
                  and r["line"].lower() not in head_names and not _larger_codes(catalog, r)]
    qualified = []
    for g in groups:
        # a head on a regulator gets no new feeder (express is None when head 1 is one);
        # its stuck lines go to the reconductor step
        if g.get("regulator") or express is None:
            continue
        if any(name.lower() in state["no_feeder"] for name in g["lines"]):
            continue
        fed = _fed_by(net, g)
        head_row = {"linecode": g["code"], "normamps": g["normamps"] / len(g["lines"]), "phases": 3, "level": "mv"}
        head_over = g["percent"] > limits["head_limit_percent"] and not _larger_codes(catalog, head_row)
        stuck = []
        for r in stuck_rows:
            ln = net["line_of"][r["line"].lower()]
            way = orientation(net, ln)
            if way is not None and way[0] in fed:
                stuck.append({"line": ln["name"], "down": way[1], "normamps": r["normamps"],
                              "far": path_length_m(net, way[1]) or 0.0})
        if head_over or stuck:
            qualified.append((g, head_over, stuck))
    if not qualified:
        return [], notes
    g, head_over, stuck = max(qualified, key=lambda t: (t[0]["percent"], -t[0]["k"]))
    at = phase_amps[g["k"]]
    fed = _fed_by(net, g)

    def amps_of(name):
        return {p: at.get(name.lower(), {}).get(p, 0.0) for p in (1, 2, 3)}

    def candidates(kind):
        found = []
        for ln in net["lines"]:
            low = ln["name"].lower()
            if (not ln["enabled"] or ln["phases"] != 3 or _level(net, ln) != "mv" or low in head_names
                    or low in watched):
                continue
            if kind == "switch" and not (ln["switch"] or ln["length_m"] <= SHORT_LINE_M):
                continue
            way = orientation(net, ln)
            members = circuits(net, ln)
            if way is None or way[0] not in fed or members[0] is not ln:
                continue
            total = {p: sum(amps_of(x["name"])[p] for x in members) for p in (1, 2, 3)}
            found.append({"line": ln["name"], "up": way[0], "down": way[1], "amps": total,
                          "length": path_length_m(net, way[1]) or 0.0})
        return found

    def search(kind):
        """(step 2 candidates, those beyond the stuck set, the stuck set left, need)."""
        pool, left = candidates(kind), sorted(stuck, key=lambda s: (-s["far"], s["line"]))
        while True:
            need = {p: 0.0 for p in (1, 2, 3)}
            if head_over:
                for p in need:
                    need[p] = max(need[p], g["amps"][p] - limits["head_limit_percent"] / 100.0 * g["normamps"])
            for s in left:
                a = amps_of(s["line"])
                for p in need:
                    need[p] = max(need[p], a[p] - limits["line_limit_percent"] / 100.0 * s["normamps"])
            below = [set(growth.subtree(net, s["down"])) for s in left]
            beyond = [c for c in pool if all(c["up"] in b for b in below)]
            found = [c for c in beyond if all(c["amps"][p] >= need[p] for p in need)]
            if found or not left:
                break
            left = left[1:]
        if not left and not head_over:
            found, beyond = [], []
        return found, beyond, left, need

    def score(c):
        return max(max(g["amps"][p] - c["amps"][p] for p in (1, 2, 3)) / g["normamps"],
                   max(c["amps"].values()) / express["normamps"])

    def pick(found, any_limit=False):
        for label, percent in (("sizing", ng["sizing_percent"]), ("limit", limits["head_limit_percent"])):
            kept = [c for c in found if max(c["amps"].values()) <= percent / 100.0 * express["normamps"]]
            if kept:
                return min(kept, key=lambda c: (score(c), c["length"], c["line"])), label
        if any_limit and found:
            return min(found, key=lambda c: (score(c), c["length"], c["line"])), "any"
        return None, ""

    choice = kind = label = None
    kinds = {"switch": ("switch",), "switch_then_bus": ("switch", "bus"), "bus": ("bus",)}[ng["open_point"]]
    for kind in kinds:
        found, beyond, left, need = search(kind)
        choice, label = pick(found)
        if choice is None and kind == "bus":
            choice, label = pick(found or beyond, any_limit=True)
        if choice is not None:
            break
    if choice is None:
        state["no_feeder"].update(name.lower() for name in g["lines"])
        notes.append(f"no {'switch' if kinds == ('switch',) else 'open point'} qualifies for head {g['k']} "
                     f"({g['lines'][0]})")
        return [], notes
    detail = {"head": g["k"], "step": g["step"], "head_amps": [round(g["amps"][p], 3) for p in (1, 2, 3)],
              "need": [round(need[p], 3) for p in (1, 2, 3)],
              "amps": [round(choice["amps"][p], 3) for p in (1, 2, 3)], "kind": kind, "set": label,
              "candidates": len(found), "stuck": [s["line"] for s in sorted(stuck, key=lambda s: s["line"])],
              "kept": [s["line"] for s in sorted(left, key=lambda s: s["line"])], "head_over": int(head_over)}
    item = {"step": "new_feeder", "_peak": max(g["amps"].values()),
            "_detail": ";".join(f"{k}={v}" for k, v in detail.items())}
    item.update({"open": choice["line"]} if kind == "switch" else {"cut_bus": choice["down"]})
    return [item], notes


# ---------------------------------------------------------------------------
# Steps: rebuilt lines and service transformers
# ---------------------------------------------------------------------------
def _groups_of(rows, key):
    """{base name, lower case: [rows]} of the rows whose element is the base element or
    one of its second circuits or parallel units <base>_ng<j>, the base first."""
    names = {r[key].lower() for r in rows}
    out = {}
    for r in rows:
        low = r[key].lower()
        base = base_name(low)
        out.setdefault(base if base in names else low, []).append(r)
    for members in out.values():
        members.sort(key=lambda r: (r[key].lower() != base_name(r[key].lower()), r[key].lower()))
    return out


def reconductor_items(net, groups, line_rows, catalog, ng, limits):
    """The lines to rebuild, as items {step, line, linecode, circuits}: every line over
    its limit and every head over its limit. For a line with peak current I (its largest
    phase, over all steps): among the catalog codes of its phases, level and
    construction with a larger normamps, the smallest whose normamps x sizing_percent /
    100 is at or above I; if none, the largest when I is within line_limit_percent of
    its normamps. The line keeps its length and buses. If no code passes (none is
    larger, none is large enough, or the construction is not shown): second circuits.
    The line takes the largest code available to it (its own when none is larger) and n
    circuits in all, n = ceil(I / (normamps x sizing_percent / 100)), the added ones
    named <line>_ng<j>. A line that already has second circuits is taken with them: I is
    the largest of their currents for the choice of a code, and their sum for n."""
    limit, sizing = limits["line_limit_percent"], ng["sizing_percent"] / 100.0
    over = {r["line"].lower() for r in lines_over(line_rows, limit)}
    for g in groups:
        if g["percent"] > limits["head_limit_percent"]:
            over.update(name.lower() for name in g["lines"])
    items = []
    for base, members in sorted(_groups_of([r for r in line_rows if r["enabled"]], "line").items()):
        row = members[0]
        if (not any(r["line"].lower() in over for r in members) or row["short"] or not row["normamps"]
                or any(r["peak_amps"] is None for r in members)):
            continue
        peak, total = max(r["peak_amps"] for r in members), sum(r["peak_amps"] for r in members)
        larger = _larger_codes(catalog, row)
        fits = [e for e in larger if e["normamps"] * sizing >= peak]
        if fits:
            code, circuits = fits[0], len(members)
        elif larger and peak <= limit / 100.0 * larger[-1]["normamps"]:
            code, circuits = larger[-1], len(members)
        else:
            code = larger[-1] if larger else {"linecode": net["line_of"][base]["text_code"], "normamps": row["normamps"]}
            circuits = max(len(members), int(math.ceil(total / (code["normamps"] * sizing))))
        if code["linecode"].lower() == row["linecode"] and circuits == len(members):
            continue
        items.append({"step": "reconductor", "line": row["line"], "linecode": code["linecode"], "circuits": circuits,
                      "_peak": peak, "_detail": f"circuits_before={len(members)};sum_amps={total:.6g}"})
    return items


def transformer_items(net, transformer_rows, catalog, ng, limits):
    """The service transformers to replace, as items {step, transformer, kva, units}:
    every transformer over its limit, every regulator (growth.is_regulator) left out. For
    a transformer with peak kVA S: among the catalog ratings of its phases and winding
    voltages above its kVA, the smallest with kVA x sizing_percent / 100 at or above S;
    if none, the largest when S is within transformer_limit_percent of it. If no rating
    passes: the largest rating available to it (its own when none is larger) and n units
    in all, n = ceil(S / (kVA x sizing_percent / 100)), the added ones named
    <transformer>_ng<j>. A transformer that already has parallel units is taken with
    them: S is the largest of their peaks for the choice of a rating, and their sum for
    n."""
    limit, sizing = limits["transformer_limit_percent"], ng["sizing_percent"] / 100.0
    over = {r["transformer"].lower() for r in transformers_over(transformer_rows, limit)}
    items = []
    rows = [r for r in transformer_rows if not growth.is_regulator(net["transformer_of"][r["transformer"].lower()])]
    for base, members in sorted(_groups_of(rows, "transformer").items()):
        row = members[0]
        if (not any(r["transformer"].lower() in over for r in members) or not row["kva"]
                or any(r["peak_kva"] is None for r in members)):
            continue
        peak, total = max(r["peak_kva"] for r in members), sum(r["peak_kva"] for r in members)
        larger = [e["kva"] for e in catalog["transformers"].get(transformer_key(net["transformer_of"][base]), [])
                  if e["kva"] > row["kva"]]
        fits = [k for k in larger if k * sizing >= peak]
        if fits:
            kva, units = fits[0], len(members)
        elif larger and peak <= limit / 100.0 * larger[-1]:
            kva, units = larger[-1], len(members)
        else:
            kva = larger[-1] if larger else row["kva"]
            units = max(len(members), int(math.ceil(total / (kva * sizing))))
        if kva == row["kva"] and units == len(members):
            continue
        items.append({"step": "service_transformer", "transformer": row["transformer"], "kva": kva, "units": units,
                      "_peak": peak, "_detail": f"units_before={len(members)};sum_kva={total:.6g}"})
    return items


# ---------------------------------------------------------------------------
# Step: a line voltage regulator
# ---------------------------------------------------------------------------
def customer_path(net, customer):
    """The medium-voltage lines from the source bus to customer (a base name of
    net["customers"]): to its service transformer primary, or to its own bus at medium
    voltage. None when it has no such path."""
    c = net["customers"].get(customer)
    bus = c["buses"][0] if c and c["buses"] else None
    while bus is not None and bus not in net["mv"]:
        step = net["parent"].get(bus)
        bus = step[2] if step else None
    return mv_path(net, bus) if bus is not None else None


def regulator_choice(net, groups, under, substation):
    """One line regulator, as ([item], [note]). The regulator is built at the upstream
    end of its line: a new bus, the upstream end of the line and of its second circuits
    moved to it, and per phase one single-phase two-winding transformer whose kVA is the
    summed normamps of those circuits x base kV / sqrt(3); on a line of SHORT_LINE_M or
    less (a switch, fuse or recloser) the amps are the largest of that sum and, for each
    branch at either end bus, the summed normamps of its medium-voltage lines longer than
    SHORT_LINE_M (_apply_regulator). The step applies when customers are
    under the band (under: {customer: lowest voltage}). Per head group, the customers
    under the band it feeds; the group with the most is taken, the first head on a tie.
    The line is the deepest medium-voltage line on the path of every one of them
    (customer_path). The step does not apply to a head whose line found this way starts
    at the source bus, at the bus of a regulator network growth built, or at a bus fed by
    any regulator (growth.is_regulator); the next head is tried. A line
    with second circuits is named by the line they were added to, and the regulator
    takes them all. A substation folder without a RegControl makes the step not
    apply."""
    if not under:
        return [], []
    if not substation.get("regcontrol"):
        return [], ["no regulator: the substation folder holds no RegControl"]
    counted = []
    for g in groups:
        fed = _fed_by(net, g)
        paths = {}
        for customer in sorted(under):
            path = customer_path(net, customer)
            if path and (orientation(net, path[0]) or (None, None))[1] in fed:
                paths[customer] = path
        if paths:
            counted.append((g, paths))
    for g, paths in sorted(counted, key=lambda t: (-len(t[1]), t[0]["k"])):
        common = None
        for path in paths.values():
            names = [ln["name"] for ln in path]
            if common is None:
                common = names
            else:
                n = 0
                while n < min(len(common), len(names)) and common[n] == names[n]:
                    n += 1
                common = common[:n]
        if not common:
            continue
        ln = circuits(net, net["line_of"][common[-1].lower()])[0]
        up = orientation(net, ln)[0]
        feed = net["parent"].get(up)
        if up == net["source"] or _REG_BUS.search(up) or (feed is not None and feed[0] == "transformer"
                                                           and growth.is_regulator(feed[1])):
            continue
        return [{"step": "regulator", "line": ln["name"], "_peak": min(under[c] for c in paths),
                 "_detail": f"head {g['k']};customers={len(paths)}"}], []
    return [], []


# ---------------------------------------------------------------------------
# The order of the steps
# ---------------------------------------------------------------------------
def new_state():
    """What one circuit folder remembers across its rounds: rebalanced (the rebalancing
    ran), no_feeder (the head lines, lower case, without an open point) and noted (the
    pairs (head or transformer, regulator name in lower case) whose note
    regulator_notes has given)."""
    return {"rebalanced": False, "no_feeder": set(), "noted": set()}


def regulator_notes(net, groups, transformer_rows, limits, state):
    """The notes on regulators over their limit, each once per circuit folder (state
    noted): a head group on a regulator over head_limit_percent, and a regulator over
    transformer_limit_percent. A regulator is never replaced, and nothing is built at a
    head on a regulator."""
    notes, noted = [], state.setdefault("noted", set())
    for g in groups:
        key = ("head", g["lines"][0].lower())
        if g.get("regulator") and g["percent"] > limits["head_limit_percent"] and key not in noted:
            noted.add(key)
            notes.append(f"head {g['k']} is the regulator {g['lines'][0]} at {g['percent']:.6g} percent, over "
                         f"head_limit_percent; no new feeder is built and nothing is rebuilt at the head")
    for r in transformers_over(transformer_rows, limits["transformer_limit_percent"]):
        key = ("transformer", r["transformer"].lower())
        if growth.is_regulator(net["transformer_of"][key[1]]) and key not in noted:
            noted.add(key)
            notes.append(f"the regulator {r['transformer']} is at {r['loading_percent']:.6g} percent of its kVA, over "
                         f"transformer_limit_percent; a regulator is not a service transformer and is not replaced")
    return notes


def next_step(net, head_rows, line_rows, transformer_rows, phase_amps, load_min, catalog, substation, ng, limits,
              low, express, state, watched=()):
    """(step, items, notes): the first step that applies on the last solve, in this
    order: rebalance_phases when it is true and has not run in this circuit folder (it
    applies when a head or a three-phase medium-voltage line longer than 1 m is over its
    limit), then the steps of ng["steps"] in their order: new_feeder (one per round),
    reconductor (every line over its limit), service_transformer (every transformer
    over its limit), regulator (one per round). step is None when no step applies. notes
    start with regulator_notes."""
    groups = head_groups(net, head_rows, phase_amps, ng["head_metric"])
    notes = regulator_notes(net, groups, transformer_rows, limits, state)
    if ng["rebalance_phases"] and not state["rebalanced"]:
        head_over = any(g["percent"] > limits["head_limit_percent"] for g in groups)
        line_over = any(r["phases"] == 3 and r["level"] == "mv"
                        for r in lines_over(line_rows, limits["line_limit_percent"]))
        if head_over or line_over:
            items = rebalance_moves(net, groups, phase_amps)
            if items:
                state["rebalanced"] = True
                return "rebalance_phases", items, notes
    for step in ng["steps"]:
        if step == "new_feeder":
            items, more = new_feeder_choice(net, groups, line_rows, phase_amps, catalog, ng, limits, express, state,
                                            watched)
        elif step == "reconductor":
            items, more = reconductor_items(net, groups, line_rows, catalog, ng, limits), []
        elif step == "service_transformer":
            items, more = transformer_items(net, transformer_rows, catalog, ng, limits), []
        else:
            items, more = regulator_choice(net, groups, customers_under(load_min, low), substation)
        notes.extend(more)
        if items:
            return step, items, notes
    return None, [], notes


# ---------------------------------------------------------------------------
# The statements an item writes
# ---------------------------------------------------------------------------
class Files:
    """The .dss files of one circuit as lists of physical lines, edited in place.
    texts: {file name: text}. text() joins every file for read_network."""

    def __init__(self, texts):
        self.lines = {name: text.splitlines(keepends=True) for name, text in texts.items()}
        self.changed = set()

    def eol(self, fname):
        """The line ending of a file: that of its first line."""
        lines = self.lines[fname]
        return "\r\n" if lines and lines[0].endswith("\r\n") else "\n"

    def elements(self):
        """{(line or transformer, name in lower case): statement} of every New Line and
        New Transformer statement."""
        out = {}
        for fname in self.lines:
            for line in self.lines[fname]:
                m = _NEW_RE.match(line)
                if m and m.group(1).lower() in ("line", "transformer"):
                    out[(m.group(1).lower(), m.group(2).lower())] = line.rstrip("\r\n")
        return out

    def text(self):
        return "\n".join("".join(self.lines[name]) for name in sorted(self.lines))

    def texts(self):
        return {name: "".join(self.lines[name]) for name in self.lines}

    def find(self, cls, name):
        """(file, index) of the New <cls>.<name> statement; None when absent."""
        for fname in sorted(self.lines):
            for i, line in enumerate(self.lines[fname]):
                m = _NEW_RE.match(line)
                if m and m.group(1).lower() == cls and m.group(2).lower() == name.lower():
                    return fname, i
        return None

    def file_of(self, cls, default):
        """The file that holds the first statement of class cls, else the file named
        default (any case); None when neither exists."""
        for fname in sorted(self.lines):
            for line in self.lines[fname]:
                m = _NEW_RE.match(line)
                if m and m.group(1).lower() == cls:
                    return fname
        return next((f for f in self.lines if f.lower() == default), None)

    def set(self, fname, index, line):
        self.lines[fname][index] = line.rstrip("\r\n") + self.eol(fname)
        self.changed.add(fname)

    def insert(self, fname, index, statements):
        eol = self.eol(fname)
        self.lines[fname][index:index] = [st + eol for st in statements]
        self.changed.add(fname)

    def append(self, fname, statements):
        lines, eol = self.lines[fname], self.eol(fname)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += eol
        lines.extend(st + eol for st in statements)
        self.changed.add(fname)


def _set_prop(line, prop, value):
    """line with prop=value in place of its prop value, appended when the line has none."""
    pattern = re.compile(rf"(?i)(?<![\w%])({re.escape(prop)}\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)")
    if pattern.search(line):
        return pattern.sub(lambda m: m.group(1) + str(value), line, count=1)
    return line.rstrip("\r\n") + f" {prop}={value}\n"


def _rename(line, cls, name):
    return re.sub(rf"(?i)^(\s*new\s+{cls}\.)\S+", lambda m: m.group(1) + name, line, count=1)


def _element(files, cls, name, item):
    found = files.find(cls, name)
    if found is None:
        raise NetworkGrowthError(f"{cls} {name} of item {public(item)} is not in the circuit")
    return found


def _add_head(files, line_name):
    """Make line_name a head: Monitors h<k>m1 (mode 0) and h<k>m2 (mode 1) on it after
    the Monitors of the last head in Master.dss, and their Export lines after the last
    Export of a head Monitor. Returns k. The names matter: Phase 8 finds the exports of
    head 1 by the token m1 or m2, and h<k>m1 does not match it."""
    master = next((f for f in files.lines if f.lower() == "master.dss"), None)
    if master is None:
        raise NetworkGrowthError("the circuit has no Master.dss for the Monitors of a new head")
    lines = files.lines[master]
    k = max(k for k, _ in head_lines("".join(lines))) + 1
    mon = [i for i, ln in enumerate(lines) if re.match(r"(?i)^\s*new\s+monitor\.(m2|h\d+m2)\b", ln)]
    exp = [i for i, ln in enumerate(lines) if re.match(r"(?i)^\s*export\s+monitors\s+(m2|h\d+m2)\b", ln)]
    if not mon or not exp:
        raise NetworkGrowthError("Master.dss has no Monitor m2 or no Export of it for the Monitors of a new head")
    files.insert(master, exp[-1] + 1, [f"Export monitors h{k}m1", f"Export monitors h{k}m2"])
    files.insert(master, mon[-1] + 1, [f"New Monitor.h{k}m1 element=Line.{line_name} mode=0",
                                       f"New Monitor.h{k}m2 element=Line.{line_name} mode=1"])
    return k


def _row(item, element, was, now, before, count, length_m="", kva=""):
    return {"step": item["step"], "element": element, "was": was, "now": now, "count_before": before,
            "count": count, "length_m": length_m, "kva": kva, "peak": item.get("_peak", ""),
            "detail": item.get("_detail", "")}


def _apply_rebalance(files, net, item):
    lat = next((x for x in single_phase_laterals(net) if x["root"] == str(item["lateral"]).lower()), None)
    if lat is None:
        raise NetworkGrowthError(f"lateral {item['lateral']} of item {public(item)} is not a single-phase "
                                 f"lateral of the circuit")
    old, new = lat["node"], int(item["to_phase"])
    buses = {b for b in lat["buses"] if b in net["mv"]}
    firsts = {name.lower() for name in lat["firsts"]}
    for fname in sorted(files.lines):
        for i, line in enumerate(files.lines[fname]):
            m = _NEW_RE.match(line)
            is_first = bool(m) and m.group(1).lower() == "line" and m.group(2).lower() in firsts

            def swap(t):
                bare = t.group(3).split(".")[0].lower()
                if bare in buses or (is_first and bare == lat["tap"]):
                    return t.group(1) + t.group(2) + _swap_node(t.group(3), old, new)
                return t.group(0)

            changed = _BUS_TOKEN.sub(swap, line)
            if changed != line:
                files.set(fname, i, changed)
    return _row(item, lat["root"], f"phase {old}", f"phase {new}", 1, 1,
                sum(ln["length_m"] for ln in lat["mv_lines"]))


def _apply_new_feeder(files, net, item, express):
    heads = dict(head_lines(files.text()))
    head1 = net["transformer_of"].get(str(heads.get(1, "")).lower())
    if head_classes(files.text()).get(1) == "transformer" and head1 is not None and growth.is_regulator(head1):
        raise NetworkGrowthError(f"item {public(item)}: head 1 of feeder {item.get('feeder', '')} is the regulator "
                                 f"{head1['name']}; no new feeder is built on a feeder whose head is a regulator")
    if "open" in item:
        ln = net["line_of"].get(str(item["open"]).lower())
        way = orientation(net, ln) if ln is not None and ln["enabled"] else None
        if way is None:
            raise NetworkGrowthError(f"line {item['open']} of item {public(item)} is not a closed line of the circuit")
        was = ln["name"]
    else:
        down = str(item["cut_bus"]).lower()
        step = net["parent"].get(down)
        if step is None or step[0] != "line":
            raise NetworkGrowthError(f"bus {item['cut_bus']} of item {public(item)} is not fed by a line of the circuit")
        ln, way = circuits(net, step[1])[0], (step[2], down)
        was = f"{ln['name']} (bus {down})"
    length = path_length_m(net, way[1])
    if length is None:
        raise NetworkGrowthError(f"the open point of item {public(item)} is not at medium voltage")
    for member in circuits(net, ln):                       # the line and its second circuits are opened
        fname, index = _element(files, "line", member["name"], item)
        files.set(fname, index, _set_prop(files.lines[fname][index], "enabled", "n"))
        for other in sorted(files.lines):                  # a Fuse on an opened line goes out with it
            for i, line in enumerate(files.lines[other]):
                if re.match(r"(?i)^\s*new\s+(fuse|recloser|relay)\.", line) and re.search(
                        rf"(?i)\bmonitoredobj\s*=\s*line\.{re.escape(member['name'])}(\s|$)", line):
                    files.set(other, i, _set_prop(line, "enabled", "n"))
    fname, index = _element(files, "line", ln["name"], item)
    k = max(k for k, _ in head_lines(files.text())) + 1
    name = f"{_EXPRESS}{k}"
    files.append(fname, [f"New Line.{name} Units=m Length={length!r} bus1={net['source']}.1.2.3 bus2={way[1]}.1.2.3 "
                         f"switch=n enabled=y phases=3 Linecode={express['linecode']}"])
    _add_head(files, name)
    return _row(item, name, was, express["linecode"], 0, 1, length)


def _apply_reconductor(files, net, item, catalog, heads):
    base = str(item["line"])
    ln = net["line_of"].get(base.lower())
    if ln is None:
        raise NetworkGrowthError(f"line {base} of item {public(item)} is not in the circuit")
    members = [ln] + sorted((x for x in net["lines"] if base_name(x["name"].lower()) == base.lower()
                             and x["name"].lower() != base.lower()), key=lambda x: x["name"].lower())
    code = str(item["linecode"])
    if code.lower() not in net["linecodes"]:
        entry = next((e for entries in catalog["lines"].values() for e in entries
                      if e["linecode"].lower() == code.lower()), None)
        if entry is None:
            raise NetworkGrowthError(f"LineCode {code} of item {public(item)} is not in the catalog")
        target = files.file_of("linecode", "linecodes.dss")
        if target is None:
            raise NetworkGrowthError("the circuit has no LineCodes file for a LineCode new to it")
        files.append(target, [entry["statement"]])
        code = entry["linecode"]
        # the items of one round share the network: the code is now one of the circuit's
        net["linecodes"][code.lower()] = {"normamps": entry["normamps"], "nphases": None, "z1": None,
                                          "units": "none"}
    for member in members:
        fname, index = _element(files, "line", member["name"], item)
        files.set(fname, index, _set_prop(files.lines[fname][index], "linecode", code))
    fname, index = _element(files, "line", ln["name"], item)
    circuits = int(item["circuits"])
    used = {x["name"].lower() for x in net["lines"]}
    j, added = 0, []
    while len(members) + len(added) < circuits:
        j += 1
        name = f"{ln['name']}_ng{j}"
        if name.lower() not in used:
            added.append(name)
    files.append(fname, [_rename(files.lines[fname][index], "line", name).rstrip("\r\n") for name in added])
    if ln["name"].lower() in {name.lower() for _, name in heads}:
        for name in added:
            _add_head(files, name)
    return _row(item, ln["name"], ln["text_code"], code, len(members), len(members) + len(added), ln["length_m"])


def retarget(statement, name, buses):
    """The New Transformer statement renamed to name, the bus of winding n set to
    buses[n - 1] (as written, with its nodes), winding by winding. The statement gives
    its windings as wdg=<n> ... bus=<bus>."""
    out, pos, wdg, seen = [], 0, 1, set()
    for m in re.finditer(r"(?i)(?<![\w%])(wdg|bus)(\s*=\s*)(\S+)", statement):
        if m.group(1).lower() == "wdg":
            wdg = int(m.group(3))
            continue
        if not 1 <= wdg <= len(buses):
            raise NetworkGrowthError(f"the catalog statement has winding {wdg}; the transformer has {len(buses)}")
        out.append(statement[pos:m.start(3)] + buses[wdg - 1])
        pos = m.end(3)
        seen.add(wdg)
    if len(seen) != len(buses):
        raise NetworkGrowthError(f"the catalog statement names {len(seen)} winding buses; the transformer has "
                                 f"{len(buses)}")
    return _rename("".join(out) + statement[pos:], "transformer", name)


def _apply_transformer(files, net, item, catalog):
    base = str(item["transformer"])
    tr = net["transformer_of"].get(base.lower())
    if tr is None:
        raise NetworkGrowthError(f"transformer {base} of item {public(item)} is not in the circuit")
    members = [tr] + sorted((x for x in net["transformers"] if base_name(x["name"].lower()) == base.lower()
                             and x["name"].lower() != base.lower()), key=lambda x: x["name"].lower())
    kva, own = float(item["kva"]), tr["windings"][0][3]
    statement = None
    if kva != own:
        entry = next((e for e in catalog["transformers"].get(transformer_key(tr), []) if e["kva"] == kva), None)
        if entry is None:
            raise NetworkGrowthError(f"rating {kva:g} kVA of item {public(item)} is not in the catalog for "
                                     f"transformers of class {transformer_key(tr)}")
        statement = entry["statement"]
    buses = [w[0] for w in tr["windings"]]
    for member in members:
        fname, index = _element(files, "transformer", member["name"], item)
        if statement is not None:
            files.set(fname, index, retarget(statement, member["name"], buses))
    fname, index = _element(files, "transformer", tr["name"], item)
    units = int(item["units"])
    used = {x["name"].lower() for x in net["transformers"]}
    j, added = 0, []
    while len(members) + len(added) < units:
        j += 1
        name = f"{tr['name']}_ng{j}"
        if name.lower() not in used:
            added.append(name)
    files.append(fname, [_rename(files.lines[fname][index], "transformer", name).rstrip("\r\n") for name in added])
    return _row(item, tr["name"], own, kva, len(members), len(members) + len(added), "", kva)


def _apply_regulator(files, net, item, substation):
    reg = (substation or {}).get("regcontrol")
    if not reg:
        raise NetworkGrowthError(f"item {public(item)}: the substation folder holds no RegControl for a regulator")
    ln = net["line_of"].get(str(item["line"]).lower())
    way = orientation(net, ln) if ln is not None and ln["enabled"] else None
    if way is None or _level(net, ln) != "mv":
        raise NetworkGrowthError(f"line {item['line']} of item {public(item)} is not a closed medium-voltage line "
                                 f"of the circuit")
    up = way[0]
    code = net["linecodes"].get(ln["linecode"]) or {}
    if up == net["source"] or _REG_BUS.search(up) or not code.get("normamps") or not net["base_kv"]:
        raise NetworkGrowthError(f"line {item['line']} of item {public(item)} starts at the source bus, already "
                                 f"carries a regulator, or has no rating")
    k = 1 + max([int(_REG_NAME.match(t["name"]).group(1)) for t in net["transformers"] if is_regulator(t["name"])],
                default=0)
    members = circuits(net, ln)
    ln = members[0]
    end = "bus1" if ln["b1"] == up else "bus2"
    spec = ln[end]
    new_bus = f"{spec.split('.')[0]}_ngreg{k}"
    amps = 0.0
    for member in members:                                 # the line and its second circuits
        m_end = "bus1" if member["b1"] == up else "bus2"
        fname, index = _element(files, "line", member["name"], item)
        files.set(fname, index, _set_prop(files.lines[fname][index], m_end,
                                          ".".join([new_bus] + member[m_end].split(".")[1:])))
        amps += (net["linecodes"].get(member["linecode"]) or {}).get("normamps") or 0.0
    if ln["length_m"] <= SHORT_LINE_M:
        # a switch, fuse or recloser: the rating is the largest of its own and, for each
        # branch at either end bus, the summed normamps of the branch's medium-voltage lines
        # longer than SHORT_LINE_M (the circuit as read before the regulator bus is added)
        pair = {ln["b1"], ln["b2"]}
        branches = {}
        for x in net["lines"]:
            ends = frozenset((x["b1"], x["b2"]))
            if (x["enabled"] and ends != pair and ends & set(way) and x["length_m"] > SHORT_LINE_M
                    and _level(net, x) == "mv"):
                branches[ends] = branches.get(ends, 0.0) + \
                    ((net["linecodes"].get(x["linecode"]) or {}).get("normamps") or 0.0)
        amps = max([amps] + list(branches.values()))
    kv = net["base_kv"] / math.sqrt(3.0)
    kva = amps * kv
    nodes = _nodes(spec, ln["phases"])
    statements = []
    for p in nodes:
        unit = f"ngreg{k}_{p}"
        statements.append(
            f"New Transformer.{unit} phases=1 windings=2 XHL={REGULATOR_XHL} %LoadLoss={REGULATOR_LOADLOSS} "
            f"wdg=1 conn=wye bus={spec.split('.')[0]}.{p} Kv={kv:.10g} kva={kva:.10g} "
            f"wdg=2 conn=wye bus={new_bus}.{p} Kv={kv:.10g} kva={kva:.10g}")
        statements.append(f"New RegControl.{unit} transformer={unit} winding=2 vreg={reg['vreg']!r} "
                          f"band={reg['band']!r} ptratio={reg['ptratio']!r}")
    target = files.file_of("transformer", "transformers.dss")
    if target is None:
        raise NetworkGrowthError("the circuit has no Transformers file for a regulator")
    files.append(target, statements)
    coords = next((f for f in files.lines if f.lower() == "buscoords.dss"), None)
    if coords is not None and up in net["coords"]:
        files.append(coords, [f"{new_bus} {net['coords'][up][0]!r} {net['coords'][up][1]!r}"])
    return _row(item, ln["name"], up, new_bus, 0, len(nodes), "", kva)


def apply_items(texts, items, catalog, substation, express):
    """Write the statements of items, in order, into the .dss texts of one circuit
    ({file name: text}). Returns ({file name: new text} of the files that changed, rows):
    one row per item for network_growth.csv (step, element, was, now, count_before,
    count, length_m, kva, peak, detail) with changed, the (line or transformer, name)
    pairs whose statement the item wrote or changed. An item sees what the items before
    it built. An
    item whose element is not in the circuit, or whose code or rating is not in the
    catalog, raises NetworkGrowthError."""
    files = Files(texts)
    rows, net, last = [], None, None
    for item in items:
        step = item.get("step")
        # items of one step touch different elements; the network is read again when the
        # step changes and before every item that changes the tree
        if net is None or step != last or step not in ("reconductor", "service_transformer"):
            net = read_network(files.text())
        last = step
        before = files.elements()
        if step == "rebalance_phases":
            rows.append(_apply_rebalance(files, net, item))
        elif step == "new_feeder":
            rows.append(_apply_new_feeder(files, net, item, express))
        elif step == "reconductor":
            rows.append(_apply_reconductor(files, net, item, catalog, head_lines(files.text())))
        elif step == "service_transformer":
            rows.append(_apply_transformer(files, net, item, catalog))
        elif step == "regulator":
            rows.append(_apply_regulator(files, net, item, substation))
        else:
            raise NetworkGrowthError(f"item {public(item)} has no known step")
        rows[-1]["changed"] = sorted(key for key, text in files.elements().items() if before.get(key) != text)
    return {name: text for name, text in files.texts().items() if name in files.changed}, rows


# ---------------------------------------------------------------------------
# The built format
# ---------------------------------------------------------------------------
def public(item):
    """item without the keys the rules keep for the tables (those that start with _)."""
    return {k: v for k, v in item.items() if not str(k).startswith("_")}


def items_for(items, feeder, mix):
    """The items of one circuit folder, in file order: those of feeder whose mix is mix
    or all."""
    return [dict(i) for i in items if i.get("feeder") == feeder and i.get("mix") in (mix, "all")]


def write_built(path, items):
    """Write items as network_growth_built.yaml: one flow mapping per item (feeder, mix,
    step, its elements, round), in the order built."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if items:
            yaml.safe_dump([public(i) for i in items], f, default_flow_style=None, sort_keys=False, width=100000,
                           allow_unicode=True)
        else:
            f.write("[]\n")


def read_built(path):
    """The items of a network_growth_built.yaml, a list of mappings (an empty file is no
    item)."""
    with open(path, encoding="utf-8") as f:
        items = yaml.safe_load(f)
    return [dict(i) for i in (items or [])]
