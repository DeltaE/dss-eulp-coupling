# -*- coding: utf-8 -*-
"""
Tests of the Phase 8 counts of 8_results_analysis/aggregate_m1_m2_with_circuits.py on one
small hand-made circuit folder: the elements counted in n_loads, n_evs, n_storage and n_pv,
and, under load growth, how many of each belong to a new customer (n_loads_new, n_evs_new,
n_storage_new, n_pv_new), mapped through der_hosts.csv and EVControl/ev_cars.csv or by the
deploy's naming rule. No OpenDSS and no pipeline run.
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "8_results_analysis"))
import aggregate_m1_m2_with_circuits as agg  # noqa: E402


def _load(name, bus, phases=1):
    return (f"New Load.{name} conn=wye bus1={bus} kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 kW=1.0 kvar=0.2 "
            f"Phases={phases} daily=res_kw_1_pu\n")


def _ev(name, bus, shape):
    return f"New Load.{name} conn=wye bus1={bus} kV=0.12 Vminpu=0.8 Vmaxpu=1.2 model=1 phases=1 kW=0.5 pf=1 daily={shape}\n"


# load_a (an existing home with legs), load_a_gh1 (a new home with legs), load_c (an existing
# business), load_b_gb1 (a new business); cars: EVu_0 of load_a at home, EVu_1 of load_a_gh1 at
# work at load_c, EVc_0 of load_a at work at load_b_gb1, EVc_1 of load_a_gh1 at home
LOADS = ("".join(_load(n, b) for n, b in (("load_a_1", "a.1"), ("load_a_2", "a.2"), ("load_a_gh1_1", "agh.1"),
                                          ("load_a_gh1_2", "agh.2")))
         + _load("load_c", "c.1.2.3", 3) + _load("load_b_gb1", "bgb.1.2.3", 3)
         + "\n! EV Loads (mixed types)\n\n"
         + _ev("EVu_load_a_1", "a.1", "EVu_0") + _ev("EVu_load_a_2", "a.2", "EVu_0")
         + _ev("EVu_w1_load_c_1", "c.1.2.3", "EVu_1") + _ev("EVu_w1_load_c_2", "c.1.2.3", "EVu_1")
         + _ev("EVc_w0_load_b_gb1_1", "bgb.1.2.3", "EVc_0") + _ev("EVc_w0_load_b_gb1_2", "bgb.1.2.3", "EVc_0")
         + _ev("EVc_load_a_gh1_1", "agh.1", "EVc_1") + _ev("EVc_load_a_gh1_2", "agh.2", "EVc_1"))
STORAGE = ("New Storage.storage_load_a_gh1_1 phases=1 bus1=agh.1 kV=0.12 kWrated=2.5 kWhrated=5\n"
           "New Storage.storage_load_a_gh1_2 phases=1 bus1=agh.2 kV=0.12 kWrated=2.5 kWhrated=5\n"
           "New Load.standby_storage_load_a_gh1_1 phases=1 bus1=agh.1 kV=0.12 conn=wye kW=0.006 kvar=0 model=1\n"
           "New Storage.storage_load_c phases=3 bus1=c.1.2.3 kV=0.48 kWrated=5 kWhrated=10\n")
PV = ("New PVSystem.pv_load_a_gh1_1 phases=1 bus1=agh.1 kV=0.12 kVA=2 pmpp=2\n"
      "New PVSystem.pv_load_a_gh1_2 phases=1 bus1=agh.2 kV=0.12 kVA=2 pmpp=2\n"
      "New PVSystem.pv_load_b_gb1 phases=3 bus1=bgb.1.2.3 kV=0.48 kVA=20 pmpp=20\n"
      "New PVSystem.pv_load_a_1 phases=1 bus1=a.1 kV=0.12 kVA=2 pmpp=2\n"
      "New PVSystem.pv_load_a_2 phases=1 bus1=a.2 kV=0.12 kVA=2 pmpp=2\n")
CARS = ("car,host,group,place,place_load\nEVu_0,load_a,uncontrolled,home,load_a\n"
        "EVu_1,load_a_gh1,uncontrolled,work,load_c\nEVc_0,load_a,controlled,work,load_b_gb1\n"
        "EVc_1,load_a_gh1,controlled,home,load_a_gh1\n")
ASSIGN = {"ev_loads_uncontrolled": ["load_a"], "ev_loads_controlled": ["load_a"],
          "growth": {"new_customers": ["load_a_gh1", "load_b_gb1"], "ev_loads_uncontrolled": ["load_a_gh1"],
                     "ev_loads_controlled": ["load_a_gh1"]}}


def _circuit(tmp_path, cars=True, der=True, assign=ASSIGN):
    folder = Path(tmp_path) / "sub_circuit_1_baseline"
    mcd = folder / "ModifiedCircuitData"
    mcd.mkdir(parents=True)
    (mcd / "Loads.dss").write_text(LOADS, encoding="utf-8")
    (mcd / "Storage.dss").write_text(STORAGE, encoding="utf-8")
    (mcd / "PVSystems.dss").write_text(PV, encoding="utf-8")
    if der:
        (mcd / "der_hosts.csv").write_text("base,segment\nload_a_gh1,residential\nload_c,commercial\n"
                                           "load_b_gb1,commercial\nload_a,residential\n", encoding="utf-8")
    if cars:
        (folder / "EVControl").mkdir()
        (folder / "EVControl" / "ev_cars.csv").write_text(CARS, encoding="utf-8")
    (folder / "scenario_assignments.json").write_text(json.dumps(assign), encoding="utf-8")
    return folder


def _names(folder):
    return agg.count_names(sorted((folder / "ModifiedCircuitData").glob("*.dss")))


def test_counts_and_new_counts(tmp_path):
    folder = _circuit(tmp_path)
    loads, storage, pv, evs = _names(folder)
    assert len(loads) == 14 and "standby_storage_load_a_gh1_1" not in loads
    assert evs == {"evu_load_a_1", "evu_load_a_2", "evu_w1_load_c_1", "evu_w1_load_c_2", "evc_w0_load_b_gb1_1",
                   "evc_w0_load_b_gb1_2", "evc_load_a_gh1_1", "evc_load_a_gh1_2"}
    assert (len(storage), len(pv)) == (3, 5)
    records = agg.customer_records(folder)
    assert records[0] == {"load_a_gh1", "load_b_gb1"}
    assert records[2] == {("u", 0): "load_a", ("u", 1): "load_a_gh1", ("c", 0): "load_a", ("c", 1): "load_a_gh1"}
    # the loads of the new home and the new business, and the EVs of the new home's two cars
    # (one at work at an existing business); the EV of an existing home at the new business is
    # not new
    assert agg.new_counts((loads, storage, pv, evs), *records) == {"n_loads_new": 7, "n_evs_new": 4,
                                                                   "n_storage_new": 2, "n_pv_new": 3}
    assert agg.element_customer("evc_w0_load_b_gb1_1", records[1], records[2]) == "load_a"
    assert agg.element_customer("evu_w1_load_c_2", records[1], records[2]) == "load_a_gh1"
    assert agg.element_customer("storage_load_c", records[1], records[2]) == "load_c"
    assert agg.element_customer("pv_load_a_gh1_2", records[1], records[2]) == "load_a_gh1"
    assert agg.element_customer("load_a_gh1_1", records[1], records[2]) == "load_a_gh1"
    assert agg.element_customer("evu_w7_load_c_1", records[1], records[2]) is None   # a car not in ev_cars.csv


def test_naming_rule_without_the_records(tmp_path):
    # without ev_cars.csv the cars follow the deploy's host lists; without der_hosts.csv the hosts
    # follow the naming rule; the counts are the same
    folder = _circuit(tmp_path, cars=False, der=False)
    records = agg.customer_records(folder)
    assert records[1] == set()
    assert records[2] == {("u", 0): "load_a", ("u", 1): "load_a_gh1", ("c", 0): "load_a", ("c", 1): "load_a_gh1"}
    assert agg.new_counts(_names(folder), *records) == {"n_loads_new": 7, "n_evs_new": 4, "n_storage_new": 2,
                                                        "n_pv_new": 3}


def test_no_new_customers(tmp_path):
    folder = _circuit(tmp_path, assign=dict(ASSIGN, growth=dict(ASSIGN["growth"], new_customers=[]),))
    names = _names(folder)
    counts = agg.new_counts(names, *agg.customer_records(folder))
    assert counts == {"n_loads_new": 0, "n_evs_new": 0, "n_storage_new": 0, "n_pv_new": 0}
    # every customer new: each new count equals its count
    _, der_bases, car_hosts = agg.customer_records(folder)
    every = {"load_a", "load_a_gh1", "load_b_gb1", "load_c"}
    assert agg.new_counts(names, every, der_bases, car_hosts) == {"n_loads_new": 14, "n_evs_new": 8,
                                                                  "n_storage_new": 3, "n_pv_new": 5}
