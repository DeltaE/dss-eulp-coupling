# -*- coding: utf-8 -*-
"""
Tests of Phase 5d, 5d_scenario_controls/combine_scenarios.py: the rows of
combined_scenarios.csv are those of the case's own buildings, the ids of the two Phase 5b
files, whatever other buildings the shared download folders hold. The script runs in a
subprocess on a synthetic work folder and parquet pool. No pipeline run.
"""

import math
import os
import subprocess
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from pipeline_utils import SETTINGS_ENV, eulp_parquet_folder, load_config  # noqa: E402

SCRIPT = os.path.join(REPO_ROOT, "5d_scenario_controls", "combine_scenarios.py")
STATE, DATE = "NC", "20250330"
COLUMN = "out.electricity.total.energy_consumption"
# kWh per 15-minute step of each parquet: {(segment, building, upgrade): values}
ENERGY = {
    ("commercial", "100", "0"): [1.0, 2.0], ("commercial", "100", "1"): [1.5, 2.0],
    ("commercial", "100", "8"): [3.0, 3.0], ("commercial", "100", "2"): [0.5, 1.0],
    ("commercial", "100", "9"): [1.0, 1.0],
    ("commercial", "200", "0"): [2.0, 2.0], ("commercial", "200", "1"): [2.5, 2.0],   # not of the case
    ("commercial", "200", "2"): [1.0, 1.0],
    ("residential", "10", "0"): [0.5, 0.5], ("residential", "10", "1"): [0.75, 0.5],
    ("residential", "10", "4"): [0.25, 0.5],
    ("residential", "11", "0"): [1.0, 0.5], ("residential", "11", "1"): [0.5, 0.5],   # heated by electricity
    ("residential", "11", "4"): [0.25, 0.25],
    ("residential", "12", "1"): [1.0, 1.0],                                           # of the case, no baseline
    ("residential", "99", "0"): [0.5, 1.0], ("residential", "99", "1"): [0.5, 0.5],   # not of the case
    ("residential", "99", "4"): [0.5, 0.25],
}


def _folders():
    cfg = load_config()
    cfg["state"], cfg["eulp_download_date"] = STATE, DATE
    return {seg: eulp_parquet_folder(cfg, seg) for seg in ("commercial", "residential")}


def _setup(tmp_path, listed=True):
    work, pool = tmp_path / "ws", tmp_path / "parquet_data"
    folders = _folders()
    for (seg, bldg, upgrade), values in ENERGY.items():
        (pool / folders[seg]).mkdir(parents=True, exist_ok=True)
        pd.DataFrame({COLUMN: values}).to_parquet(pool / folders[seg] / f"{bldg}-{upgrade}.parquet")
    meta = work / "1_data_provenance" / "outputs" / "pipeline_state"
    meta.mkdir(parents=True)
    pd.DataFrame({"bldg_id": [10, 11, 12, 99], "in.heating_fuel": ["Natural Gas", "Electricity", "Natural Gas",
                                                                    "Natural Gas"]}).to_csv(
        meta / "residential_data_SELECT_STATES.csv", index=False)
    mapping = work / "5b_profile_generation"
    mapping.mkdir(parents=True)
    if listed:
        pd.DataFrame({"Feeder": ["f1", "f1"], "Parquet_Folder": [folders["commercial"], folders["residential"]],
                      "Parquet_File": ["100-0.parquet", "10-0.parquet"], "REAL_LOAD_COUNT": [1, 2]}).to_csv(
            mapping / f"{STATE}_required_parquets_per_feeder.csv", index=False)
        pd.DataFrame({"Feeder": ["f1", "f1", "f1"], "Parquet_Folder": [folders["residential"]] * 3,
                      "Parquet_File": ["10-0.parquet", "11-0.parquet", "12-0.parquet"]}).to_csv(
            mapping / f"{STATE}_parquet_and_bldgs.csv", index=False)
    return work, pool


def _run(work, pool):
    env = {k: v for k, v in os.environ.items() if k != SETTINGS_ENV}
    env.update({"PIPELINE_STATE": STATE, "PIPELINE_SEASON": "summer", "PIPELINE_WORK_ROOT": str(work),
                "PIPELINE_PARQUET_ROOT": str(pool), "PIPELINE_EULP_DOWNLOAD_DATE": DATE})
    return subprocess.run([sys.executable, SCRIPT], cwd=os.path.dirname(SCRIPT), capture_output=True, text=True,
                          timeout=120, env=env)


def _sum(seg, bldg, upgrade):
    return sum(v * 4 for v in ENERGY[(seg, bldg, upgrade)])


def test_rows_are_the_case_buildings_only(tmp_path):
    work, pool = _setup(tmp_path)
    proc = _run(work, pool)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = pd.read_csv(work / "5d_scenario_controls" / "combine_scenarios" / "combined_scenarios.csv",
                      dtype={"building_id": str})
    folders = _folders()
    # 200 and 99 are not in the Phase 5b files; 12 has no baseline parquet
    assert list(zip(out["folder"], out["building_id"])) == [(folders["commercial"], "100"),
                                                            (folders["residential"], "10"),
                                                            (folders["residential"], "11")]
    rows = {b: r for b, r in zip(out["building_id"], out.to_dict("records"))}
    # each row as the rule of the script gives it: un the largest change from baseline, dm the lowest use
    expected = {
        "100": ("commercial", "8", "2", "HP Boiler, Electric Backup",
                "Variable Speed HP RTU, Original Heating Fuel Backup"),
        "10": ("residential", "1", "4", "ENERGY STAR heat pump with elec backup",
               "ENERGY STAR heat pump with existing system as backup"),
        "11": ("residential", "1", "1", "ENERGY STAR heat pump with elec backup",
               "ENERGY STAR heat pump with elec backup"),
    }
    for bldg, (seg, un, dm, un_name, dm_name) in expected.items():
        r, base = rows[bldg], _sum(seg, bldg, "0")
        assert math.isclose(r["baseline_demand"], base)
        assert math.isclose(r["uncontrolled_demand"], _sum(seg, bldg, un))
        assert math.isclose(r["demand_management_demand"], _sum(seg, bldg, dm))
        assert math.isclose(r["uncontrolled_diff"], _sum(seg, bldg, un) - base)
        assert math.isclose(r["demand_management_diff"], _sum(seg, bldg, dm) - base)
        assert (r["uncontrolled_scenario_name"], r["demand_management_scenario_name"]) == (un_name, dm_name)
        assert (str(int(r["uncontrolled_scenario_id"])), str(int(r["demand_management_scenario_id"]))) == (un, dm)


def test_a_missing_phase5b_file_stops(tmp_path):
    work, pool = _setup(tmp_path, listed=False)
    proc = _run(work, pool)
    assert proc.returncode == 1
    assert "[FAIL]" in proc.stdout and "_required_parquets_per_feeder.csv" in proc.stdout
    assert not (work / "5d_scenario_controls" / "combine_scenarios" / "combined_scenarios.csv").exists()
