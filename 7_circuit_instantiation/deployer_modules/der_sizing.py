# -*- coding: utf-8 -*-
"""
der_sizing.py
-------------
PV and storage hosts and sizes for Phase 7b (instantiate_circuits.py) and the Phase 7
deploy, from der_sizing in pipeline_config.yaml. Every number comes from der_sizing;
the functions hold the rules only.

- der_switch(cfg, key), der_choice(cfg, key), der_number(cfg, key), der_value(cfg,
  segment, key): the setting readers; a missing or unknown value prints [FAIL] and
  exits 1.
- segment_count(perc, n_bases, enabled): hosts of one segment, round(perc x bases) with
  at least one when perc > 0 and the segment has bases.
- pick(seed, offset, items, k) and pick_hosts(...): the seeded draws of PV and storage
  hosts per segment, with the storage_hosts rule.
- loadshape_building(name): the building type and number of a daily loadshape name.
- day_peak(values, day): the peak of a profile, on one day of a window when day is
  given.
- annual_yield(values_kw_per_1000): kWh per kW of array per year of a SMART-DS solar
  file.
- roof_area_m2(...), pv_kw_roof_and_use(...), storage_size(...): the size rules.
- standby_pct(...): the %IdlingkW of a host's storage units from the standby setting.
"""
import math
import random
import re
import sys

FT2_TO_M2 = 0.09290304
SEGMENTS = ("residential", "commercial")
SIZING_CASES = ("low", "moderate", "high")
CHOICES = {
    "storage_hosts": ("with_pv", "independent", "apart"),
    "sizing_case": SIZING_CASES,
    "pv_rule_residential": ("roof_and_use", "peak_ratio"),
    "pv_rule_commercial": ("roof_and_use", "peak_ratio"),
    "roof_area_source": ("floor_stories", "metadata"),
    "coverage_rule_commercial": ("lbnl", "comstock"),
    "storage_rule": ("simple", "tuned", "schedule"),
    "storage_view": ("feeder", "transformer", "building"),
    "storage_order": ("after_cars", "before_cars", "same_measurement"),
    "storage_measure": ("all_placed", "buildings_only"),
    "storage_layer": ("add_kw", "solve"),
    "storage_standby_case": SIZING_CASES,
    "storage_standby_element": ("load", "idling"),
    "schedule_start": ("best", "best_window", "fixed"),
}


def _block(cfg):
    block = cfg.get("der_sizing")
    if not isinstance(block, dict):
        print("[FAIL] der_sizing is missing from pipeline_config.yaml.")
        sys.exit(1)
    return block


def der_switch(cfg, key):
    """der_sizing.<key> of the loaded pipeline_config.yaml, true or false. A missing or
    non-boolean value prints [FAIL] and exits 1."""
    value = _block(cfg).get(key)
    if not isinstance(value, bool):
        print(f"[FAIL] der_sizing.{key} in pipeline_config.yaml is {value!r}; expected true or false.")
        sys.exit(1)
    return value


def der_choice(cfg, key):
    """der_sizing.<key>, one of CHOICES[key]. A missing or unknown value prints [FAIL]
    and exits 1."""
    value = _block(cfg).get(key)
    if value not in CHOICES[key]:
        print(f"[FAIL] der_sizing.{key} in pipeline_config.yaml is {value!r}; "
              f"expected one of {', '.join(CHOICES[key])}.")
        sys.exit(1)
    return value


def der_number(cfg, key):
    """der_sizing.<key> as a float. A missing or non-numeric value prints [FAIL] and
    exits 1."""
    value = _block(cfg).get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        print(f"[FAIL] der_sizing.{key} in pipeline_config.yaml is {value!r}; expected a number.")
        sys.exit(1)
    return float(value)


def der_value(cfg, segment, key, case=None):
    """der_sizing.<segment>.<key> as a float: the entry of case (low, moderate or high)
    when case is given, else the entry value. A missing or non-numeric entry prints
    [FAIL] and exits 1."""
    seg = _block(cfg).get(segment)
    entry = seg.get(key) if isinstance(seg, dict) else None
    value = entry.get(case if case else "value") if isinstance(entry, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        print(f"[FAIL] der_sizing.{segment}.{key}.{case or 'value'} in pipeline_config.yaml is "
              f"{value!r}; expected a number.")
        sys.exit(1)
    return float(value)


def segment_count(perc, n_bases, enabled=True, min_one=True):
    """Hosts of one segment: round(perc x n_bases), at least 1 and at most n_bases when
    perc > 0 and n_bases > 0; 0 when the segment is switched off. With min_one False (the
    new loads of load growth) the count may be 0."""
    if not enabled or perc <= 0 or n_bases <= 0:
        return 0
    return max(1 if min_one else 0, min(int(round(perc * n_bases)), n_bases))


def pick(seed, offset, items, k):
    """The first k items after a shuffle with random.Random(seed + offset), the draw of
    Phase 7b (offset: _stable_seed_offset("<substation>|<feeder>"))."""
    if k <= 0 or len(items) == 0:
        return []
    rng = random.Random(int(seed) + offset)
    items_copy = list(items)
    rng.shuffle(items_copy)
    return items_copy[:min(k, len(items_copy))]


def pick_hosts(bases, n_pv, n_sto, pv_seed, storage_seed, offset, storage_hosts):
    """PV and storage hosts of one segment, bases sorted; every draw is pick(seed, offset,
    ...) with the given offset, written pick(seed, ...) below. PV: pick(pv_seed, bases, n_pv).
    Storage, by storage_hosts:
    - with_pv: pick(storage_seed, PV hosts, n_sto); when n_sto exceeds the PV hosts, the
      rest by pick(storage_seed, the other bases, n_sto - PV hosts);
    - independent: pick(storage_seed, bases, n_sto);
    - apart: pick(storage_seed, bases without PV, n_sto), or among all bases when every
      base has PV.
    Returns (pv_hosts, storage_hosts)."""
    pv = pick(pv_seed, offset, bases, n_pv)
    if storage_hosts == "with_pv":
        sto = pick(storage_seed, offset, pv, n_sto)
        if n_sto > len(pv):
            sto += pick(storage_seed, offset, [b for b in bases if b not in pv], n_sto - len(pv))
    elif storage_hosts == "independent":
        sto = pick(storage_seed, offset, bases, n_sto)
    else:
        pool = [b for b in bases if b not in pv]
        sto = pick(storage_seed, offset, pool if pool else list(bases), n_sto)
    return pv, sto


_LOADSHAPE_RE = re.compile(r"^(res|com)_kw_(.+)_pu$")


def loadshape_building(name):
    """(Yearly_Type, Yearly_Number) of the building of a daily loadshape name
    <res|com>_kw_<number>_pu, the number as text: the whole part between _kw_ and _pu,
    as Phase 5b links a loadshape to its building. SMART-DS v1.0 numbers are all digits
    (res_kw_9312_pu gives 9312); v0.9 Full Texas numbers carry text (res_kw_9312-North_pu
    gives 9312-North). None for any other name."""
    m = _LOADSHAPE_RE.match(str(name))
    return (m.group(1), m.group(2)) if m else None


def day_peak(values, day=None, steps_per_day=96):
    """The peak of a profile: the maximum of values. With day (a position from 0), the
    maximum of that day's steps_per_day values only, so a profile of several days gives
    the peak of the simulated peak day and not of the window."""
    if day is None:
        return float(max(values))
    return float(max(values[day * steps_per_day:(day + 1) * steps_per_day]))


def annual_yield(values, step_h):
    """kWh per kW of array per year: the sum of values (kW per kW of array, one per step
    of step_h hours over the year) times step_h."""
    return float(sum(values)) * step_h


def roof_area_m2(segment, source, floor_ft2, stories, metadata_roof, tilt_deg=None):
    """Roof area in m2. floor_stories: floor area (ft2, converted to m2) over stories,
    divided by cos(tilt_deg) for residential (a pitched roof), flat for commercial.
    metadata: the building model's roof column, ft2 for residential (converted to m2),
    m2 for commercial."""
    if source == "metadata":
        return metadata_roof * FT2_TO_M2 if segment == "residential" else metadata_roof
    footprint = floor_ft2 * FT2_TO_M2 / stories
    if segment == "residential":
        return footprint / math.cos(math.radians(tilt_deg))
    return footprint


def pv_kw_roof_and_use(roof_m2, coverage, kw_per_m2, use_share, annual_kwh, yield_kwh_per_kw):
    """Return (PV kW DC, roof cap, use cap, roof_binds): min(coverage x roof_m2 x
    kw_per_m2, use_share x annual_kwh / yield_kwh_per_kw)."""
    cap_roof = coverage * roof_m2 * kw_per_m2
    cap_use = use_share * annual_kwh / yield_kwh_per_kw
    return min(cap_roof, cap_use), cap_roof, cap_use, cap_roof < cap_use


def storage_size(pv_kw, ratio_small, ratio_large, large_pv_kw, hours):
    """Return (kW, kWh): kW = ratio x pv_kw, ratio_large when pv_kw > large_pv_kw else
    ratio_small; kWh = hours x kW."""
    kw = (ratio_large if pv_kw > large_pv_kw else ratio_small) * pv_kw
    return kw, hours * kw


def standby_pct(segment, host_storage_kw, standby_w, standby_pct_of_kw):
    """%IdlingkW of every storage unit of a host: residential 100 x standby_w /
    (1000 x host_storage_kw), the home system's standby W over the host's storage kW;
    commercial standby_pct_of_kw. The units of a two-leg host share its kW, so each
    takes the host's percent."""
    if segment == "residential":
        return 100.0 * standby_w / (1000.0 * host_storage_kw)
    return standby_pct_of_kw
