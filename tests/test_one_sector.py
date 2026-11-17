# -*- coding: utf-8 -*-
"""
Tests of a case with one kind of customer (only businesses or only homes). Phases 3 and 4
write every file of the sector without loads with its usual header and no rows, the Phase 3
and Phase 4 checks of verify_phase.py accept zero rows for that sector only, and a sector with
loads and no match row or no building stops at the check with a [FAIL] line that names it.
The scripts run in subprocesses on small made-up work folders. No pipeline run, no EULP data.
"""

import json
import os
import subprocess
import sys

import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from pipeline_utils import SETTINGS_ENV  # noqa: E402

STATE = "TX"
PHASE3 = os.path.join(REPO_ROOT, "3_tolerance_matching", "match_smartds_parquets_impl.py")
CLEANUP = os.path.join(REPO_ROOT, "4_quota_assignment", "clean_up_bldgs_impl.py")
SELECT = os.path.join(REPO_ROOT, "4_quota_assignment", "select_representatives_impl.py")
SCALE = os.path.join(REPO_ROOT, "5b_profile_generation", "scale_feeder_curves_impl.py")
VERIFY = os.path.join(REPO_ROOT, "verify_phase.py")
COM_PEAKS = [f"out.qoi.maximum_daily_peak_{m}..kw" for m in
             ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")]
# The files Phases 3 and 4 write for each sector.
SECTOR_FILES = {
    "com": ["3_tolerance_matching/df_com_matches_out_TX.csv",
            "4_quota_assignment/commercial_data_SELECT_STATES_FILTERED_TX.csv",
            "4_quota_assignment/commercial_building_source_map_TX.csv",
            "4_quota_assignment/TX_final_commercial.csv"],
    "res": ["3_tolerance_matching/df_res_matches_out_TX.csv",
            "4_quota_assignment/residential_data_SELECT_STATES_FILTERED_TX.csv",
            "4_quota_assignment/residential_data_SELECT_STATES_FILTERED_low_TX.csv",
            "4_quota_assignment/residential_data_SELECT_STATES_FILTERED_mid_TX.csv",
            "4_quota_assignment/residential_data_SELECT_STATES_FILTERED_high_TX.csv",
            "4_quota_assignment/residential_building_source_map_TX.csv",
            "4_quota_assignment/TX_final_residential.csv"],
}


def _workspace(root, sectors):
    """A work folder whose feeder f1 has loads of the given sectors (com, res)."""
    work = root / "ws"
    meta = work / "1_data_provenance" / "outputs" / "pipeline_state"
    for sub in (meta, work / "3_tolerance_matching", work / "4_quota_assignment", work / "5b_profile_generation"):
        sub.mkdir(parents=True)
    com = pd.DataFrame({"bldg_id": [100, 101, 102], "State": STATE,
                        "in.comstock_building_type": ["Office", "Retail", "Office"]})
    for c, col in enumerate(COM_PEAKS):
        com[col] = [10.0, 10.4, 50.0]
    com.to_csv(meta / "commercial_data_SELECT_STATES.csv", index=False)
    pd.DataFrame({"bldg_id": [10, 11, 12], "State": STATE,
                  "in.area_median_income": ["80-100%", "0-30%", "150%+"],
                  "in.vacancy_status": ["Occupied", "Occupied", "Vacant"],
                  "in.geometry_building_type_acs": ["Single-Family Detached", "Mobile Home",
                                                    "Single-Family Detached"],
                  "out.electricity.winter.peak.kw": [5.0, 5.1, 5.0],
                  "out.electricity.summer.peak.kw": [5.0, 5.1, 5.0]}).to_csv(
        meta / "residential_data_SELECT_STATES.csv", index=False)
    review, pivot = [], []
    for kind, number, peak, phases, count in (("com", 1, 10.0, 3, 1), ("res", 1, 5.0, 1, 4)):
        if kind in sectors:
            review += [{"Month": m, "Monthly_Peak": peak, "Source_File": f"{kind}_{number}.parquet", "Type": kind}
                       for m in range(1, 13)]
            pivot.append({"Feeder": "f1", "Phases": phases, "Yearly_Type": kind, "Yearly_Number": number,
                          "Count_of_Load_Name": count, "REAL_LOAD_COUNT": count // phases if phases == 1 else count,
                          "Parquet_Name": f"{kind}_{number}.parquet"})
    pd.DataFrame(review).to_csv(work / "3_tolerance_matching" / "review_parquet_matches.csv", index=False)
    pd.DataFrame(pivot).to_csv(work / "parsed_loads_SUMMARY.csv", index=False)
    (work / "feeder_registry.json").write_text(json.dumps({"feeders": [{"feeder_name": "f1"}]}), encoding="utf-8")
    return work


def _env(work):
    env = {k: v for k, v in os.environ.items() if k != SETTINGS_ENV and k != "PIPELINE_MIX"}
    env.update({"PIPELINE_STATE": STATE, "PIPELINE_SEASON": "summer", "PIPELINE_WORK_ROOT": str(work),
                "PIPELINE_PARQUET_ROOT": str(work / "parquet_data"), "PIPELINE_EULP_DOWNLOAD_DATE": "20250330",
                "PIPELINE_FEEDER_REGISTRY_PATH": str(work / "feeder_registry.json")})
    return env


def _run(script, work, *args):
    cwd = REPO_ROOT if script == VERIFY else os.path.dirname(script)
    return subprocess.run([sys.executable, script, *args], cwd=cwd, capture_output=True, text=True,
                          timeout=300, env=_env(work))


def _phases_3_4(work):
    for script in (PHASE3, CLEANUP, SELECT):
        proc = _run(script, work)
        assert proc.returncode == 0, f"{os.path.basename(script)}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}"


def _header(path):
    with open(path, encoding="utf-8") as fh:
        return fh.readline().rstrip("\r\n")


def _rows(path):
    return len(pd.read_csv(path))


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    work = _workspace(tmp_path_factory.mktemp("both"), {"com", "res"})
    _phases_3_4(work)
    return work


@pytest.mark.parametrize("present,empty", [("res", "com"), ("com", "res")])
def test_writers_give_header_only_files_for_an_empty_sector(tmp_path, both, present, empty):
    work = _workspace(tmp_path, {present})
    _phases_3_4(work)
    for rel in SECTOR_FILES[empty]:
        assert _header(work / rel) == _header(both / rel) != "", rel
        assert _rows(work / rel) == 0, rel
    for rel in SECTOR_FILES[present]:
        assert _header(work / rel) == _header(both / rel), rel
    assert _rows(work / SECTOR_FILES[present][-1]) == 1


@pytest.mark.parametrize("present,empty", [("res", "com"), ("com", "res")])
def test_checks_pass_for_an_empty_sector(tmp_path, present, empty):
    work = _workspace(tmp_path, {present})
    _phases_3_4(work)
    for phase in ("3", "4"):
        proc = _run(VERIFY, work, "--phase", phase)
        assert proc.returncode == 0, proc.stdout
        assert "[FAIL]" not in proc.stdout
        assert f"sector {empty}" in proc.stdout and "has no load" in proc.stdout


@pytest.mark.parametrize("missing", ["com", "res"])
def test_phase3_check_fails_for_a_sector_with_loads_and_no_match_row(tmp_path, missing):
    work = _workspace(tmp_path, {"com", "res"})
    _phases_3_4(work)
    rel = SECTOR_FILES[missing][0]
    pd.read_csv(work / rel).iloc[0:0].to_csv(work / rel, index=False)
    proc = _run(VERIFY, work, "--phase", "3")
    assert proc.returncode == 1
    assert f"[FAIL]   rows=0: sector {missing} has loads and no match row" in proc.stdout


@pytest.mark.parametrize("missing", ["com", "res"])
def test_phase4_check_fails_for_a_sector_with_loads_and_no_building(tmp_path, missing):
    work = _workspace(tmp_path, {"com", "res"})
    _phases_3_4(work)
    rel = SECTOR_FILES[missing][-1]
    pd.read_csv(work / rel).iloc[0:0].to_csv(work / rel, index=False)
    proc = _run(VERIFY, work, "--phase", "4")
    assert proc.returncode == 1
    assert f"[FAIL]   rows=0: sector {missing} (" in proc.stdout and "has loads and no building" in proc.stdout


@pytest.mark.parametrize("missing", ["com", "res"])
def test_no_matched_building_stops_at_the_phase4_check(tmp_path, missing):
    """Every shape of a sector with loads has an empty Matched_Buildings: Phase 3 and its
    check pass, Phase 4 writes header-only files for the sector and its check fails."""
    work = _workspace(tmp_path, {"com", "res"})
    proc = _run(PHASE3, work)
    assert proc.returncode == 0, proc.stderr
    rel = work / SECTOR_FILES[missing][0]
    df = pd.read_csv(rel)
    df["Matched_Buildings"] = "[]"
    df.to_csv(rel, index=False)
    assert _run(VERIFY, work, "--phase", "3").returncode == 0
    for script in (CLEANUP, SELECT):
        proc = _run(script, work)
        assert proc.returncode == 0, proc.stderr
    assert _rows(work / SECTOR_FILES[missing][-1]) == 0
    proc = _run(VERIFY, work, "--phase", "4")
    assert proc.returncode == 1
    assert f"[FAIL]   rows=0: sector {missing} (" in proc.stdout and "has loads and no building" in proc.stdout


@pytest.mark.parametrize("present", ["res", "com"])
def test_phase5b_scaling_reads_a_header_only_final_list(tmp_path, present):
    work = _workspace(tmp_path, {present})
    _phases_3_4(work)
    proc = _run(SCALE, work)
    assert proc.returncode == 0, proc.stderr
    out = pd.read_csv(work / "5b_profile_generation" / "TX_parquet_and_bldgs.csv")
    assert len(out) == 1 and out["Yearly_Type"].tolist() == [present]
    req = pd.read_csv(work / "5b_profile_generation" / "TX_required_parquets_per_feeder.csv")
    assert req["REAL_LOAD_COUNT"].tolist() == out["REAL_LOAD_COUNT"].tolist()
