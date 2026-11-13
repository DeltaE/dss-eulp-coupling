# -*- coding: utf-8 -*-
"""
growth_plan.py
--------------
Phase growth, between 4 and 5a in configs/phases.yaml. run_case.py runs it from the
repository root with the PIPELINE_* variables set and --topology-id <topology_id>.

With growth_years 0 in growth.yaml (growth off) it prints one line, writes nothing and
exits 0. With growth on it writes the plan of the run, one planning year growth_years
years after the data year, for every feeder of the case (the rules are in
7_circuit_instantiation/deployer_modules/growth.py).

Inputs
- configs/growth.yaml with the growth.yaml of the --settings folder merged over it
  (pipeline_utils.load_growth, growth_settings).
- random_seed, skip_circuits and max_feeders of pipeline_config.yaml; the feeder
  registry; each feeder's SMART-DS .dss files, found as Phase 7b finds them.
- <work_root>/4_quota_assignment/<STATE>_final_commercial.csv (Phase 4): the building
  of each business (Chosen_Parquet = <prefix>_<n>.parquet for loadshape
  <prefix>_kw_<n>_pu), with in.comstock_building_type, in.sqft,
  in.building_america_climate_zone and out.electricity.total.peak_demand.
- <work_root>/1_data_provenance/outputs/pipeline_state/commercial_data_SELECT_STATES.csv
  (Phase 1), read only when a named load's type is not in the Phase 4 selection.

Outputs, all under <work_root>/growth/
- growth_plan.json: the merged settings and, per feeder, its seed, factors, counts,
  the units (one per infill copy, block, companion or named load, each with its new
  Line and Transformer statements, its new Load lines, its new bus coordinates and its
  new customers), the loadshapes new to the feeder and their constant kvar over kW.
- growth_customers.csv, growth_blocks.csv, growth_named_loads.csv, growth_factors.csv,
  growth_summary.csv (columns in docs/outputs.md).

A building new to a feeder (a named load whose building no load of the feeder uses) is
added to what Phases 5a onward read, under the loadshape name com_kw_g<bldg_id>_pu: one
row in <work_root>/4_quota_assignment/<STATE>_final_commercial.csv (its metadata row with
Chosen_Parquet com_g<bldg_id>.parquet) and one row per feeder in
<work_root>/parsed_loads_SUMMARY.csv with a REAL_LOAD_COUNT of 0, so every curve that
weights buildings by that count keeps its values. Rows of an earlier call of this phase
are removed first; every other line of both files is kept as text.

Stops with [FAIL] (exit 1): a bad growth setting; a named_loads or load_factors entry
whose feeder is not in the case, or whose load is not a customer of the feeder; a
block_attach_buses or named_loads bus that is not a three-phase medium-voltage bus; a
named load whose type has no building in the Phase 4 selection and none in the Phase 1
metadata of the state in the most common climate zone of the feeder's businesses (or
metadata without the zone column); a feeder without a business to copy a named load's
connection from.
"""

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
from pipeline_utils import (GROWTH_PLAN_DIR, GROWTH_PLAN_FILE, growth_infill_share, growth_on, growth_rates,
                            growth_settings, load_config, load_feeder_registry, load_growth,
                            resolve_config_path, resolve_work_path)

sys.path.insert(0, str(REPO_ROOT / "7_circuit_instantiation"))
sys.path.insert(0, str(REPO_ROOT / "7_circuit_instantiation" / "deployer_modules"))
import growth

GROWTH_ROW = re.compile(r",com_g\d+\.parquet\s*$")
TYPE_COL, AREA_COL, ZONE_COL = "in.comstock_building_type", "in.sqft", "in.building_america_climate_zone"
PEAK_COL = "out.electricity.total.peak_demand"


def fail(message):
    print(f"[FAIL] growth: {message}")
    sys.exit(1)


def case_feeders(cfg):
    """The feeder folders of the case, as Phase 7b finds them."""
    registry = load_feeder_registry()
    root = resolve_config_path(cfg["smart_ds_root"])
    skip = {int(n) for n in cfg.get("skip_circuits", [])}
    feeders = []
    for entry in registry["feeders"]:
        child = root / Path(entry["original_path"])
        names = {nm.lower() for nm in os.listdir(child)} if child.is_dir() else set()
        if "loads.dss" not in names or "loadshapes.dss" not in names or int(entry["circuit_id"]) in skip:
            continue
        feeders.append(child)
    if cfg.get("max_feeders") is not None:
        feeders = feeders[:int(cfg.get("max_feeders"))]
    return feeders, registry["circuit_name_map"]


def read_rows(path):
    """(header, rows as dicts, lines as text) of a CSV, the rows of an earlier call of
    this phase left out."""
    with open(path, encoding="utf-8", newline="") as f:
        lines = [ln for ln in f.read().splitlines(keepends=True) if not GROWTH_ROW.search(ln)]
    reader = csv.reader(io.StringIO("".join(lines)))
    header = next(reader)
    return header, [dict(zip(header, r)) for r in reader if r], lines


def write_lines(path, lines, new_rows):
    """Write lines followed by new_rows (lists of fields), with the line ending of the
    file. Nothing is written when the text is the file's own."""
    ending = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=ending).writerows(new_rows)
    text = "".join(lines)
    if new_rows and text and not text.endswith(("\n", "\r")):
        text += ending
    text += buffer.getvalue()
    with open(path, encoding="utf-8", newline="") as f:
        if f.read() == text:
            return
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def shape_parquet(shape):
    """Parquet_Name of a yearly loadshape <prefix>_kw_<n>_pu: <prefix>_<n>.parquet."""
    m = re.match(r"^(.+)_kw_(.+)_pu$", shape or "")
    return f"{m.group(1)}_{m.group(2)}.parquet" if m else None


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Phase growth: the load growth plan of the run.")
    parser.add_argument("--topology-id", required=True)
    args = parser.parse_args()
    g = growth_settings(load_growth(), args.topology_id)
    if not growth_on(g):
        print("[growth] growth_years is 0: growth is off, phase growth skipped, nothing written.")
        return
    cfg = load_config()
    state, years = cfg["state"], g["growth_years"]
    rates = growth_rates(g)
    share = growth_infill_share(g, args.topology_id)
    factors = growth.segment_factors(rates, years)
    feeders, circuit_of = case_feeders(cfg)
    names = [f.name for f in feeders]
    for key in ("named_loads", "load_factors"):
        for i, entry in enumerate(g[key]):
            if entry["feeder"] not in names:
                fail(f"{key}[{i}].feeder is {entry['feeder']!r}; the feeders of this case are {', '.join(names)}.")

    final_path = resolve_work_path("4_quota_assignment", f"{state}_final_commercial.csv")
    final_header, final_rows, final_lines = read_rows(final_path)
    by_parquet = {r["Chosen_Parquet"]: r for r in final_rows}
    summary_path = resolve_work_path("parsed_loads_SUMMARY.csv")
    summary_header, _, summary_lines = read_rows(summary_path)
    metadata = None  # read on first use

    plan = {"settings": json.loads(json.dumps(g)), "growth_years": years, "state": state,
            "topology_id": args.topology_id, "rates": rates, "infill_share": share, "factors": factors,
            "feeders": {}, "kvar_ratios": {}}
    t_customers, t_blocks, t_named, t_factors, t_summary = [], [], [], [], []
    new_final, new_summary = {}, []

    for feeder_dir in feeders:
        feeder, substation = feeder_dir.name, feeder_dir.parent.name
        texts = {fn.lower(): (feeder_dir / fn).read_text(encoding="utf-8")
                 for fn in sorted(os.listdir(feeder_dir)) if fn.lower().endswith(".dss")}
        try:
            net = growth.read_feeder(texts)
        except growth.GrowthError as e:
            fail(f"{feeder}: {e}.")
        seed = growth.growth_seed(cfg["random_seed"], substation, feeder)
        cust = net["customers"]
        homes = sorted(b for b, c in cust.items() if c["segment"] == "residential")
        businesses = sorted(b for b, c in cust.items() if c["segment"] == "commercial")
        others = sorted(b for b, c in cust.items() if c["segment"] is None)
        tr_map, served = growth.transformer_map(net, texts)

        # The building of each business, from the Phase 4 selection
        buildings, zones, own_ids = {}, Counter(), {}
        for b in businesses:
            row = by_parquet.get(shape_parquet(sorted(cust[b]["shapes"])[0]))
            if row is None or number(row.get(AREA_COL)) is None:
                continue
            buildings[b] = {"type": row.get(TYPE_COL, ""), "sqft": number(row[AREA_COL]),
                            "bldg_id": str(int(float(row["bldg_id"])))}
            zones[row.get(ZONE_COL, "")] += 1
            own_ids.setdefault(buildings[b]["bldg_id"], sorted(cust[b]["shapes"])[0])
        zone = sorted(zones, key=lambda z: (-zones[z], z))[0] if zones else ""

        n = growth.counts(len(homes), len(businesses), rates, years, g["companions"], g["companions_national"], share)
        pool, bound, mean_area = growth.companion_pool(businesses, buildings, n["companions"],
                                                       g["companion_excluded_types"])

        load_factors = {}
        for i, entry in enumerate(g["load_factors"]):
            if entry["feeder"] != feeder:
                continue
            if entry["load"] not in cust:
                fail(f"load_factors[{i}].load is {entry['load']!r}; it is not a customer of feeder {feeder}.")
            load_factors[entry["load"]] = {"factor": float(entry["factor"]),
                                           "peak_factor": float(entry["peak_factor"]) if "peak_factor" in entry else None}
        for b in sorted(cust):
            lf = load_factors.get(b)
            t_factors.append({"Feeder": feeder, "customer": b, "segment": cust[b]["segment"] or "",
                              "factor": lf["factor"] if lf else factors.get(cust[b]["segment"], 1.0),
                              "peak_factor": "" if not lf or lf["peak_factor"] is None else lf["peak_factor"]})

        units = []

        def add_unit(label, kind, elements, customers, remainder=False, shift=None):
            coords = growth.shifted_coords(net, elements["buses"], *(shift or (None, None)))
            units.append({"unit": label, "kind": kind, "remainder": remainder, "lines": elements["lines"],
                          "transformers": elements["transformers"], "loads": elements["loads"],
                          "coords": {b: list(xy) for b, xy in sorted(coords.items())}, "customers": customers})

        def customer_row(label, kind, new_base, template, elements, remainder=False, building="", btype="",
                         shape=None):
            seg = cust[template]["segment"]
            loads = [ld for ld in elements["loads"] if ld["base"] == new_base]
            info = buildings.get(template, {})
            t_customers.append({
                "Feeder": feeder, "unit": label, "name": new_base, "kind": kind, "remainder": int(remainder),
                "copied_customer": template, "building": building or info.get("bldg_id", ""), "segment": seg,
                "type": btype or info.get("type", ""), "factor": factors[seg],
                "bus": loads[0]["bus1"].split(".")[0] if loads else "",
                "transformer": elements.get("transformer_of", {}).get(new_base, elements.get("transformer", "")),
                "pattern": elements.get("pattern", "block"),
                "new_lines": len(elements["lines"]) if kind != "block" else "",
                "new_transformers": len(elements["transformers"]) if kind != "block" else ""})
            return {"name": new_base, "template": template, "segment": seg, "factor": factors[seg],
                    "shape": shape or sorted(cust[template]["shapes"])[0]}

        def copy_one(label, kind, template, remainder=False, at=None):
            conn = growth.customer_connection(net, template, tr_map, served)
            elements = growth.copy_customer(net, template, label, conn, at=at, own_transformer=at is not None)
            shift = None
            if at is not None and elements["pattern"] != "own_bus":
                up = conn["up"] if elements["pattern"] == "mv_line" else conn["transformer"]["windings"][0][1]
                shift = (up, at)
            new_base = growth.new_name(template, label)
            add_unit(label, kind, elements, [customer_row(label, kind, new_base, template, elements, remainder)],
                     remainder, shift)

        # 1. Infill homes: the first n of one seeded order of the circuit's homes
        home_order = growth.seeded_order(homes, "infill_homes", seed)
        for i, template in enumerate(growth.take(home_order, n["infill_homes"]), start=1):
            copy_one(f"h{i}", "infill", template)

        # 2. Blocks
        try:
            blocks, remainder, companions_left = growth.place_blocks(
                net, growth.find_laterals(net), n["block_homes"], n["block_companions"], pool, seed,
                g["block_attach_buses"].get(feeder, []))
        except growth.GrowthError as e:
            fail(f"{feeder}: {e}.")
        built = [b for b in blocks if b["attach"] is not None]
        for blk in blocks:
            lat = blk["template"]
            label = f"b{blk['k']}"
            row = {"Feeder": feeder, "block": blk["k"], "unit": label if blk["attach"] else "",
                   "built": int(blk["attach"] is not None), "template_root": lat["root"], "template_tap": lat["tap"],
                   "kind": lat["kind"], "homes": lat["homes"], "businesses": lat["businesses"],
                   "attach_bus": blk["attach"] or "", "attach_given": int(blk["given"]),
                   "bearing_deg": "" if blk["given"] else blk["bearing_deg"], "radius_m": blk["radius_m"],
                   "lines": len(lat["lines"]), "transformers": len(lat["transformers"]),
                   "customers": len(lat["customers"]), "companions_dealt": 0,
                   "attach_distance_m": growth.path_length_m(net, blk["attach"]) if blk["attach"] else ""}
            blk["row"] = row
            t_blocks.append(row)
            if blk["attach"] is None:
                continue
            elements = growth.copy_lateral(net, lat, label, blk["attach"])
            elements["transformer_of"] = {}
            for base in lat["customers"]:
                names_tr = {tr_map.get(ld["name"]) for ld in cust[base]["loads"]}
                tr_name = names_tr.pop() if len(names_tr) == 1 else None
                elements["transformer_of"][growth.new_name(base, label)] = growth.new_name(tr_name, label) if tr_name else ""
            add_unit(label, "block", elements,
                     [customer_row(label, "block", growth.new_name(base, label), base, elements)
                      for base in lat["customers"]], shift=(lat["tap"], blk["attach"]))

        # 3. Block companions still due, dealt to the blocks in build order
        if built:
            dealt = growth.take(growth.seeded_order(pool, "block_companions", seed), companions_left)
            for i, template in enumerate(dealt, start=1):
                blk = built[(i - 1) % len(built)]
                blk["row"]["companions_dealt"] += 1
                copy_one(f"d{i}", "companion", template, at=blk["attach"])
            n_block_companions, extra_infill = len(dealt), 0
        else:
            n_block_companions, extra_infill = 0, companions_left

        # 4. Block homes that no block took: infill homes, next in the same order
        for i, template in enumerate(growth.take(home_order, n["infill_homes"] + remainder)[n["infill_homes"]:],
                                     start=n["infill_homes"] + 1):
            copy_one(f"h{i}", "infill", template, remainder=True)

        # 5. Infill companions (and the block companions when no block is built)
        order = growth.seeded_order(pool, "infill_companions", seed)
        infill_companions = growth.take(order, n["infill_companions"] + extra_infill)
        for i, template in enumerate(infill_companions, start=1):
            copy_one(f"c{i}", "companion", template, remainder=i > n["infill_companions"])

        # 6. Named loads
        new_shapes, n_named = {}, 0
        for e, entry in enumerate(g["named_loads"], start=1):
            if entry["feeder"] != feeder or int(entry["year"]) > years:
                continue
            def read_metadata():
                nonlocal metadata
                if metadata is None:
                    metadata = read_rows(resolve_work_path("1_data_provenance", "outputs", "pipeline_state",
                                                           "commercial_data_SELECT_STATES.csv"))
                return metadata[0], metadata[1]

            try:
                candidates, source = growth.named_candidates(final_rows, read_metadata, entry["type"], zone, state,
                                                             TYPE_COL, ZONE_COL)
            except growth.GrowthError as err:
                fail(f"named_loads[{e - 1}]: {err}.")
            for j in range(1, int(entry["count"]) + 1):
                label = f"n{e}x{j}"
                bldg = growth.named_building(candidates, f"named_building_{e}_{j}", seed)
                row = candidates[bldg]
                peak_kw = number(row.get(PEAK_COL))
                if peak_kw is None:
                    fail(f"named_loads[{e - 1}]: building {bldg} has no {PEAK_COL}.")
                peak_kw *= factors["commercial"]
                found = growth.named_template(net, peak_kw, tr_map, served)
                if found is None:
                    fail(f"named_loads[{e - 1}]: feeder {feeder} has no business whose connection a new load can copy.")
                template, conn = found
                ratio = cust[template]["kvar"] / cust[template]["kw"]
                peak_kva = peak_kw * math.sqrt(1.0 + ratio * ratio)
                try:
                    bus, why = growth.named_bus(net, g["named_load_bus"], f"named_bus_{e}_{j}", seed, entry.get("bus"))
                except growth.GrowthError as err:
                    fail(f"named_loads[{e - 1}]: {err}.")
                new_to_feeder = bldg not in own_ids
                shape = f"com_kw_g{bldg}_pu" if new_to_feeder else own_ids[bldg]
                if new_to_feeder:
                    new_shapes.setdefault(shape, {"bldg_id": bldg, "parquet_name": f"com_g{bldg}.parquet",
                                                  "kvar_per_kw": ratio, "source": source})
                    ratio_used = new_shapes[shape]["kvar_per_kw"]
                    if source == "metadata_zone":
                        if metadata[0] != final_header[:-1]:
                            fail(f"the columns of the Phase 1 metadata differ from those of {final_path}.")
                        new_final.setdefault(bldg, [row[c] for c in metadata[0]] + [f"com_g{bldg}.parquet"])
                    else:
                        new_final.setdefault(bldg, [row[c] for c in final_header[:-1]] + [f"com_g{bldg}.parquet"])
                    phases = cust[template]["loads"][0]["phases"]
                    fields = dict(zip(summary_header, [feeder, phases, "com", f"g{bldg}", 0, 0, f"com_g{bldg}.parquet"]))
                    if [fields[c] for c in summary_header] not in new_summary:
                        new_summary.append([fields[c] for c in summary_header])
                else:
                    ratio_used = ""
                elements = growth.connect_named(net, label, template, conn, bus, peak_kva, shape)
                up = conn["up"] if elements["pattern"] == "mv_line" else conn["transformer"]["windings"][0][1]
                new_base = growth.new_name(template, label)
                add_unit(label, "named", elements,
                         [customer_row(label, "named", new_base, template, elements, building=bldg,
                                       btype=entry["type"], shape=shape)], shift=(up, bus))
                n_named += 1
                t_named.append({
                    "Feeder": feeder, "entry": e, "number": j, "unit": label, "name": new_base, "type": entry["type"],
                    "bldg_id": bldg, "drawn_from": source, "candidates": len(candidates), "zone": zone,
                    "new_to_feeder": int(new_to_feeder), "loadshape": shape, "bus": bus, "bus_rule": why,
                    "bus_impedance_ohm": growth.path_impedance(net, bus), "template": template,
                    "template_kw": cust[template]["kw"], "pattern": elements["pattern"], "peak_kw": peak_kw,
                    "kvar_per_kw_template": ratio, "kvar_per_kw_constant": ratio_used, "peak_kva": peak_kva,
                    "transformer": elements["transformer"], "transformer_kva": elements["transformer_kva"] or "",
                    "transformer_large_enough": int(elements["large_enough"]), "factor": factors["commercial"]})

        tag = circuit_of.get(feeder, "")
        plan["feeders"][feeder] = {
            "substation": substation, "circuit": tag, "seed": seed, "homes": len(homes),
            "businesses": len(businesses), "others": others, "counts": n, "factors": factors,
            "load_factors": load_factors, "units": units, "new_shapes": new_shapes}
        if new_shapes:
            plan["kvar_ratios"][tag] = {v["parquet_name"]: v["kvar_per_kw"] for v in new_shapes.values()}
        t_summary.append({
            "Feeder": feeder, "growth_years": years, "case": g["case"], "homes": len(homes),
            "businesses": len(businesses), "others": len(others),
            **{f"rate_{k}": v for k, v in rates.items()},
            "factor_homes": factors["residential"], "factor_businesses": factors["commercial"],
            "companions_rule": g["companions"], "infill_share": share, **n,
            "mean_floor_area_ft2": mean_area, "floor_area_bound_ft2": bound,
            "businesses_with_building": len(buildings), "pool": len(pool),
            "laterals": len(growth.find_laterals(net)), "blocks_drawn": len(blocks), "blocks_built": len(built),
            "block_homes_built": sum(b["template"]["homes"] for b in built),
            "block_businesses_built": sum(b["template"]["businesses"] for b in built),
            "remainder_homes": remainder, "block_companions_dealt": n_block_companions,
            "infill_companions_placed": len(infill_companions),
            "companions_not_placed": n["companions"] - sum(b["template"]["businesses"] for b in built)
            - n_block_companions - len(infill_companions),
            "named_loads": n_named, "new_customers": sum(len(u["customers"]) for u in units),
            "climate_zone": zone, "seed": seed})
        print(f"[growth] {feeder}: {len(homes)} homes, {len(businesses)} businesses; new homes {n['new_homes']} "
              f"(infill {n['infill_homes']}, blocks {n['block_homes']}, remainder {remainder}), companions "
              f"{n['companions']}, blocks built {len(built)} of {len(blocks)}, named loads {n_named}, "
              f"units {len(units)}")

    out_dir = resolve_work_path(GROWTH_PLAN_DIR)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, GROWTH_PLAN_FILE), "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, indent=1)
        f.write("\n")
    tables = (("growth_customers.csv", t_customers, [
                  "Feeder", "unit", "name", "kind", "remainder", "copied_customer", "building", "segment", "type",
                  "factor", "bus", "transformer", "pattern", "new_lines", "new_transformers"]),
              ("growth_blocks.csv", t_blocks, [
                  "Feeder", "block", "unit", "built", "template_root", "template_tap", "kind", "homes", "businesses",
                  "attach_bus", "attach_given", "bearing_deg", "radius_m", "lines", "transformers", "customers",
                  "companions_dealt", "attach_distance_m"]),
              ("growth_named_loads.csv", t_named, [
                  "Feeder", "entry", "number", "unit", "name", "type", "bldg_id", "drawn_from", "candidates", "zone",
                  "new_to_feeder", "loadshape", "bus", "bus_rule", "bus_impedance_ohm", "template", "template_kw",
                  "pattern", "peak_kw", "kvar_per_kw_template", "kvar_per_kw_constant", "peak_kva", "transformer",
                  "transformer_kva", "transformer_large_enough", "factor"]),
              ("growth_factors.csv", t_factors, ["Feeder", "customer", "segment", "factor", "peak_factor"]),
              ("growth_summary.csv", t_summary, list(t_summary[0]) if t_summary else ["Feeder"]))
    for name, rows, columns in tables:
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    # A building new to a feeder joins the lists that Phases 5a onward read
    write_lines(final_path, final_lines, [new_final[b] for b in sorted(new_final)])
    write_lines(summary_path, summary_lines, new_summary)
    print(f"[growth] plan written: {os.path.join(out_dir, GROWTH_PLAN_FILE)}; buildings new to a feeder: "
          f"{len(new_final)} ({', '.join(sorted(new_final)) or 'none'})")


if __name__ == "__main__":
    main()
