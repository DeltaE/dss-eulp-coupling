#!/usr/bin/env python3
"""Repairs of two defects of the SMART-DS release, made on the run's own copy of a circuit.

Some feeders of the SMART-DS v0.9 release contradict themselves. Each repair below has a
detection rule that reads only the feeder's own files, a change that writes only values
read from those files, and a reason. A defect that has no repair stops the run.

- head_meters_on_regulator. Defect: Monitor m1, Monitor m2 or Energymeter m3 of
  Master.dss names an element Line.<name>, and no New Line.<name> statement exists in the
  feeder folder. The repair exists when exactly one transformer of the feeder is a
  regulator (two or more windings, all of the same kV) with its first winding on the
  source bus (bus1 of the New Circuit statement), and that transformer is named
  trans_<name>. Change: the element of each such statement becomes
  Transformer.<the regulator's name as the feeder's files write it>. Reason: the meters
  name the head regulator under the class Line, so OpenDSS meters nothing and the solve
  fails.
- source_voltage_from_transformers. Transformer voltage of a feeder: for each
  transformer that is not a regulator, its winding of the highest kV (the first on a
  tie), times sqrt(3) when the transformer has phases=1 and that winding's bus names
  exactly one phase node (a node other than 0), else its kV as written; the largest such
  value. Defect: basekV of the New Circuit statement and the transformer voltage differ
  at VOLTAGE_DECIMALS decimals. Change: basekV takes the rounded transformer voltage
  (Python's repr of the rounded value), and in Set Voltagebases the old basekV value is
  removed, the new value is added if the list does not hold it, and the list is written
  in ascending order, every kept value with its own text. Reason: the source then holds
  the voltage the feeder's own transformers are rated for. A feeder with no such
  transformer is not checked.

The functions work on the texts of a feeder folder ({file name: text}). Phase pre runs
this file as a script (check, read only on the staged files); Phase 7b calls
repair_folder on its copy and write_table in each circuit folder; with load growth on,
phase growth (growth_plan.py) reads each feeder through repaired_texts, in memory. The
repairs apply with growth on and off. smartds_repairs in pipeline_config.yaml turns
every repair off.

Script use (phase pre, from the repository root with the PIPELINE_* variables set):
    python smartds_repairs.py --topology-id <topology_id>
"""
import argparse
import csv
import math
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "7_circuit_instantiation" / "deployer_modules"))
from ev_control import _PROP_RE, _array, _bus, _logical_lines
from pipeline_utils import load_config, load_feeder_registry, resolve_config_path, smartds_repairs_on

# ASSUMPTION: basekV and the transformer voltage are compared at 2 decimals, because the
# release writes a line-to-neutral rating with 3 decimals (14.434 kV for a 25 kV system
# gives 14.434 x sqrt(3) = 25.0004 kV); a comparison at more decimals would flag every such
# feeder, and one at fewer would pass a feeder whose source and transformers differ by up
# to 0.05 kV.
VOLTAGE_DECIMALS = 2

TABLE_FILE = "smartds_repairs.csv"
TABLE_COLUMNS = ["feeder", "repair", "file", "line", "was", "now"]
MASTER = "master.dss"
HEADS = ("monitor.m1", "monitor.m2", "energymeter.m3")
HEAD_RE = re.compile(r"(?i)^new\s+(monitor\.m1|monitor\.m2|energymeter\.m3)(?=\s|$)\s*(.*)$")


def read_texts(folder):
    """{file name: text} of the .dss files (any letter case) directly in folder."""
    texts = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if name.lower().endswith(".dss") and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="surrogateescape") as fh:
                texts[name] = fh.read()
    return texts


def _file(texts, lower_name):
    """The name of the file of texts called lower_name in any letter case, or None."""
    return next((n for n in texts if n.lower() == lower_name), None)


def master_statements(text):
    """[(first line number, [physical line numbers], statement)] of a Master.dss text: the
    statements of ev_control._logical_lines (~ continuation lines joined, ! comments
    removed), each with the 1-based numbers of its physical lines."""
    out = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("~") and out:
            first, numbers, statement = out[-1]
            out[-1] = (first, numbers + [number], statement + " " + line[1:].strip())
        else:
            out.append((number, [number], line))
    return out


def _element(rest):
    """The element of a Monitor or Energymeter statement: its element= value, else its
    first value without a property name."""
    props = dict((k.lower(), v) for k, v in _PROP_RE.findall(rest))
    if "element" in props:
        return props["element"]
    for token in rest.split():
        if "=" not in token:
            return token
        break
    return None


def _phase_nodes(bus):
    """The phase nodes (nodes other than 0) a bus name gives, as text."""
    return [n for n in str(bus).strip().strip("\"'").split(".")[1:] if n.isdigit() and n != "0"]


def _number(value):
    try:
        return float(str(value).strip("\"' "))
    except ValueError:
        return None


def read_feeder(texts):
    """What the rules need from the texts of a feeder folder:
    circuit (line, bus1, basekv, basekv_text) of the New Circuit statement of Master.dss;
    voltagebases (line, numbers, items) of its Set Voltagebases statement or None; heads,
    one (head, line, numbers, element) per Monitor m1, Monitor m2 and Energymeter m3
    statement; lines, the lower-case names of every New Line statement of the folder;
    transformers, one (name, phases, windings) per New Transformer statement of the
    folder, windings a list of (bus, kV) by winding number and phases None when the
    statement does not set it."""
    feeder = {"circuit": None, "voltagebases": None, "heads": [], "lines": set(), "transformers": []}
    master = _file(texts, MASTER)
    for first, numbers, st in master_statements(texts[master]) if master else []:
        m = re.match(r"(?i)^new\s+circuit\.\S+\s*(.*)$", st)
        if m and feeder["circuit"] is None:
            props = dict((k.lower(), v) for k, v in _PROP_RE.findall(m.group(1)))
            feeder["circuit"] = {"line": first, "numbers": numbers, "bus1": _bus(props.get("bus1", "")),
                                 "basekv": _number(props["basekv"]) if "basekv" in props else None}
        m = re.match(r"(?i)^set\s+voltagebases\s*=\s*(.*)$", st)
        if m:
            items = _array(m.group(1))
            feeder["voltagebases"] = {"line": first, "numbers": numbers, "items": items}
        m = HEAD_RE.match(st)
        if m:
            feeder["heads"].append({"head": m.group(1).lower(), "line": first, "numbers": numbers,
                                    "element": _element(m.group(2))})
    for name in texts:
        for st in _logical_lines(texts[name]):
            m = re.match(r"(?i)^new\s+(line|transformer)\.(\S+)\s*(.*)$", st)
            if not m:
                continue
            if m.group(1).lower() == "line":
                feeder["lines"].add(m.group(2).lower())
                continue
            wdg, buses, kvs, phases = 1, {}, {}, None
            for k, v in _PROP_RE.findall(m.group(3)):
                k = k.lower()
                if k == "wdg":
                    wdg = int(v)
                elif k == "bus":
                    buses[wdg] = v
                elif k == "kv":
                    kvs[wdg] = _number(v)
                elif k == "phases":
                    phases = int(v)
                elif k == "buses":
                    buses.update({i: b for i, b in enumerate(_array(v), start=1)})
                elif k == "kvs":
                    kvs.update({i: _number(x) for i, x in enumerate(_array(v), start=1)})
            feeder["transformers"].append({"name": m.group(2), "phases": phases, "windings": [
                (buses.get(i, ""), kvs.get(i)) for i in sorted(set(buses) | set(kvs))]})
    return feeder


def is_regulator(transformer):
    """A transformer with two or more windings whose windings all have the same kV."""
    kvs = [kv for _, kv in transformer["windings"]]
    return len(kvs) >= 2 and None not in kvs and len(set(kvs)) == 1


def transformer_voltage(feeder):
    """The transformer voltage of the feeder (see the module text), or None."""
    values = []
    for tr in feeder["transformers"]:
        known = [(kv, bus) for bus, kv in tr["windings"] if kv is not None]
        if is_regulator(tr) or not known:
            continue
        top = max(kv for kv, _ in known)
        bus = next(b for kv, b in known if kv == top)
        values.append(top * math.sqrt(3.0) if tr["phases"] == 1 and len(_phase_nodes(bus)) == 1 else top)
    return max(values) if values else None


def _replace_in(lines, numbers, pattern, new):
    """Replace the first match of pattern (group 2 is the value) in the physical lines
    numbers of lines (each a line without its ending) by group 1 + new. Returns True when
    a line changed."""
    for n in numbers:
        m = pattern.search(lines[n - 1])
        if m:
            lines[n - 1] = lines[n - 1][:m.start(2)] + new + lines[n - 1][m.end(2):]
            return True
    return False


def _statement(lines, numbers):
    """The statement held by the physical lines numbers, joined as master_statements does."""
    return master_statements("\n".join(lines[n - 1] for n in numbers))[0][2]


def head_meters_on_regulator(feeder, lines):
    """Repair A. Returns (changes, defects): changes [(head, numbers, new lines of those
    numbers)], defects [text] when the defect has no repair."""
    changes, defects = [], []
    source = feeder["circuit"]["bus1"] if feeder["circuit"] else None
    regulators = [tr for tr in feeder["transformers"] if is_regulator(tr) and tr["windings"]
                  and _bus(tr["windings"][0][0]) == source]
    for head in feeder["heads"]:
        element = head["element"] or ""
        if not element.lower().startswith("line."):
            continue
        name = element.split(".", 1)[1]
        if name.lower() in feeder["lines"]:
            continue
        where = f"Master.dss line {head['line']} puts {head['head']} on {element}, which no New Line statement " \
                f"of the feeder defines"
        if len(regulators) != 1:
            defects.append(f"{where}, and {len(regulators)} regulators (transformers whose windings all have one "
                           f"kV) have their first winding on the source bus {source}; exactly one is needed")
            continue
        regulator = regulators[0]["name"]
        if regulator.lower() != f"trans_{name}".lower():
            defects.append(f"{where}, and the one regulator on the source bus {source} is "
                           f"Transformer.{regulator}, not Transformer.trans_{name}")
            continue
        pattern = re.compile(r"(?<![^\s=])" + re.escape(element) + r"(?=\s|$)")
        new = list(lines)
        for n in head["numbers"]:
            m = pattern.search(new[n - 1])
            if m:
                new[n - 1] = new[n - 1][:m.start()] + f"Transformer.{regulator}" + new[n - 1][m.end():]
                break
        changes.append((head, new))
    return changes, defects


def source_voltage_from_transformers(feeder, lines):
    """Repair B. Returns (changes, defects) as head_meters_on_regulator; it has no
    defect without a repair."""
    circuit = feeder["circuit"]
    voltage = transformer_voltage(feeder)
    if circuit is None or circuit["basekv"] is None or voltage is None:
        return [], []
    old, now = circuit["basekv"], round(voltage, VOLTAGE_DECIMALS)
    if round(old, VOLTAGE_DECIMALS) == now:
        return [], []
    changes = []
    new = list(lines)
    _replace_in(new, circuit["numbers"], re.compile(r"(?i)(\bbasekv\s*=\s*)(\S+)"), repr(now))
    changes.append((circuit, new))
    bases = feeder["voltagebases"]
    if bases is not None:
        items = [x for x in bases["items"] if _number(x) != old]
        if not any(_number(x) == now for x in items):
            items.append(repr(now))
        items.sort(key=_number)
        new = list(lines)
        _replace_in(new, bases["numbers"],
                    re.compile(r"(?i)(\bvoltagebases\s*=\s*)(\[[^\]]*\]|\([^\)]*\)|\"[^\"]*\"|'[^']*'|\S+)"),
                    "[" + ", ".join(items) + "]")
        changes.append((bases, new))
    return changes, []


# The repairs, in the order they are applied. Each: (name, function, reason).
REPAIRS = [
    ("head_meters_on_regulator", head_meters_on_regulator,
     "the head meters name a Line that no file defines; the head element is the regulator"),
    ("source_voltage_from_transformers", source_voltage_from_transformers,
     "the source voltage disagrees with the voltage of the feeder's own transformers"),
]


def check(texts, feeder_name):
    """The repairs that apply to the texts of a feeder and its defects without a repair:
    (changes, defects). changes: one dict per changed statement, with feeder, repair,
    file, line (the statement's first line), was and now (the statement before and after),
    in the order of REPAIRS. defects: [(repair, text)]. The repairs change different
    statements, so each is found on the texts as they are."""
    master = _file(texts, MASTER)
    if master is None:
        return [], []
    lines = texts[master].splitlines()
    feeder = read_feeder(texts)
    changes, defects = [], []
    for name, rule, _ in REPAIRS:
        found, missing = rule(feeder, lines)
        defects.extend((name, text) for text in missing)
        for statement, new in found:
            changes.append({"feeder": feeder_name, "repair": name, "file": master, "line": statement["line"],
                            "numbers": statement["numbers"], "was": _statement(lines, statement["numbers"]),
                            "now": _statement(new, statement["numbers"]),
                            "new_lines": {n: new[n - 1] for n in statement["numbers"]}})
    return changes, defects


def repair_line(change):
    """The printed line of one change."""
    return (f"[repair] {change['feeder']}: {change['repair']}: {change['file']} line {change['line']}: "
            f"{change['was']} -> {change['now']}")


def fail_lines(feeder_name, defects):
    """The [FAIL] lines of a feeder: one per defect without a repair."""
    return [f"[FAIL] {feeder_name}: {repair}: {text}." for repair, text in defects]


def repaired_texts(texts, changes):
    """The texts of a feeder ({file name: text}) with the changes of check applied, in
    memory: a new dict in which each changed file holds the new statements and keeps
    every other character, line endings included. texts is not changed."""
    out = dict(texts)
    for change in changes:
        physical = out[change["file"]].splitlines(keepends=True)
        for n, text in change["new_lines"].items():
            body = physical[n - 1].rstrip("\r\n")
            physical[n - 1] = text + physical[n - 1][len(body):]
        out[change["file"]] = "".join(physical)
    return out


def repair_folder(folder, feeder_name):
    """Apply the repairs to the feeder folder on disk (repaired_texts). Rewrites only
    Master.dss, only the statements named, and keeps every other byte, line endings
    included. A folder without a defect is not written. Returns (changes, defects) of
    check."""
    texts = read_texts(folder)
    changes, defects = check(texts, feeder_name)
    if not changes:
        return changes, defects
    name = changes[0]["file"]
    path = os.path.join(folder, name)
    with open(path, "rb") as fh:
        raw = fh.read().decode("utf-8", errors="surrogateescape")
    with open(path, "wb") as fh:
        fh.write(repaired_texts({name: raw}, changes)[name].encode("utf-8", errors="surrogateescape"))
    return changes, defects


def write_table(path, changes):
    """Write the table of changes (TABLE_COLUMNS, one row per changed statement) to path;
    a header only when changes is empty."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(TABLE_COLUMNS)
        for c in changes:
            writer.writerow([c[k] for k in TABLE_COLUMNS])


def case_feeders(cfg):
    """[(feeder name, folder)] of the case, as Phase 7b finds them: the registry entries
    whose folder holds Loads.dss and LoadShapes.dss, without skip_circuits, at most
    max_feeders."""
    registry = load_feeder_registry()
    root = resolve_config_path(cfg["smart_ds_root"])
    skip = {int(n) for n in cfg.get("skip_circuits", [])}
    feeders = []
    for entry in registry["feeders"]:
        folder = root / Path(entry["original_path"])
        names = {n.lower() for n in os.listdir(folder)} if folder.is_dir() else set()
        if "loads.dss" not in names or "loadshapes.dss" not in names or int(entry["circuit_id"]) in skip:
            continue
        feeders.append((entry["feeder_name"], folder))
    if cfg.get("max_feeders") is not None:
        feeders = feeders[:int(cfg["max_feeders"])]
    return feeders


def main():
    parser = argparse.ArgumentParser(description="Phase pre: check the feeders of the case for the "
                                                 "defects of the SMART-DS release (read only).")
    parser.add_argument("--topology-id", required=True)
    parser.parse_args()  # the command of phase pre names the topology; the check needs no setting of it
    cfg = load_config()
    if not smartds_repairs_on(cfg):
        print("[repair] smartds_repairs is false in pipeline_config.yaml: no feeder is checked and no repair "
              "is made.")
        return 0
    feeders = case_feeders(cfg)
    n_changes, repaired, fails = 0, 0, []
    for feeder_name, folder in feeders:
        changes, defects = check(read_texts(folder), feeder_name)
        for change in changes:
            print(repair_line(change))
        n_changes += len(changes)
        repaired += 1 if changes else 0
        fails.extend(fail_lines(feeder_name, defects))
    print(f"[repair] {len(feeders)} feeders checked: {n_changes} statements to repair on {repaired} feeders.")
    for line in fails:
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
