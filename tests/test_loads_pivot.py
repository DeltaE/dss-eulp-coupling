# -*- coding: utf-8 -*-
"""
Tests of 0_download_smartds/generate_loads_pivot.py: the pivot holds one row per feeder and
load shape. A shape that serves loads of more than one phase count gives one row, in the place
of its lowest phase count, with Phases listing the counts and the counts summed. A file with
no shared shape gives the pivot of the earlier rule byte for byte. The script runs in a
subprocess on small parsed_loads.csv files written here. No pipeline run.
"""

import io
import os
import subprocess
import sys

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "0_download_smartds", "generate_loads_pivot.py")
HEADER = "Substation,Feeder,Load_Name,Phases,kW,kvar,Yearly_Type,Yearly_Number"
PIVOT_HEADER = "Feeder,Phases,Yearly_Type,Yearly_Number,Count_of_Load_Name,REAL_LOAD_COUNT,Parquet_Name"


def _loads(groups):
    """parsed_loads.csv text: groups is a list of (feeder, phases, yearly_type, yearly_number, lines)."""
    rows, k = [HEADER], 0
    for feeder, phases, ytype, ynum, lines in groups:
        for _ in range(lines):
            k += 1
            rows.append(f"sub,{feeder},load_{k},{phases},1.0,0.5,{ytype},{ynum}")
    return "\n".join(rows) + "\n"


def _run(tmp_path, groups):
    src, out = tmp_path / "parsed_loads.csv", tmp_path / "parsed_loads_SUMMARY.csv"
    src.write_text(_loads(groups), encoding="utf-8")
    proc = subprocess.run([sys.executable, SCRIPT, "--input", str(src), "--output", str(out)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return out.read_bytes(), proc.stdout


def _expected(lines):
    return ("\n".join([PIVOT_HEADER] + lines) + "\n").replace("\n", os.linesep).encode("utf-8")


def _one_row_per_shape(raw):
    df = pd.read_csv(io.BytesIO(raw), dtype=str)
    assert not df.duplicated(["Feeder", "Parquet_Name"]).any()


def test_no_shared_shape_gives_the_earlier_pivot(tmp_path):
    raw, stdout = _run(tmp_path, [
        ("f1", 3, "com", 5, 1), ("f1", 1, "res", 1, 4), ("f1", 1, "res", 2, 3),
        ("f2", 1, "res", 1, 2), ("f2", 3, "com", 6, 2),
    ])
    assert raw == _expected([
        "f1,1,res,1,4,2,res_1.parquet",
        "f1,1,res,2,3,1,res_2.parquet",
        "f1,3,com,5,1,1,com_5.parquet",
        "f2,1,res,1,2,1,res_1.parquet",
        "f2,3,com,6,2,2,com_6.parquet",
    ])
    assert "Feeders: 2" in stdout and "Total load count: 12" in stdout
    _one_row_per_shape(raw)


def test_shared_shape_merges_into_its_single_phase_row(tmp_path):
    raw, stdout = _run(tmp_path, [
        ("f1", 1, "com", 9, 8), ("f1", 3, "com", 9, 2), ("f1", 1, "res", 1, 2), ("f1", 3, "com", 4, 1),
    ])
    assert raw == _expected([
        "f1,1;3,com,9,10,6,com_9.parquet",
        "f1,1,res,1,2,1,res_1.parquet",
        "f1,3,com,4,1,1,com_4.parquet",
    ])
    assert "Feeders: 1" in stdout and "Total load count: 13" in stdout
    _one_row_per_shape(raw)


def test_same_shape_on_two_feeders_stays_one_row_per_feeder(tmp_path):
    raw, _ = _run(tmp_path, [
        ("f1", 1, "com", 9, 8), ("f1", 3, "com", 9, 2), ("f2", 1, "com", 9, 4), ("f2", 3, "com", 9, 1),
        ("f3", 3, "com", 9, 2),
    ])
    assert raw == _expected([
        "f1,1;3,com,9,10,6,com_9.parquet",
        "f2,1;3,com,9,5,3,com_9.parquet",
        "f3,3,com,9,2,2,com_9.parquet",
    ])
    _one_row_per_shape(raw)


def test_odd_single_phase_count_truncates(tmp_path):
    raw, _ = _run(tmp_path, [("f1", 1, "res", 1, 3), ("f1", 1, "com", 9, 5), ("f1", 3, "com", 9, 2)])
    assert raw == _expected([
        "f1,1;3,com,9,7,4,com_9.parquet",
        "f1,1,res,1,3,1,res_1.parquet",
    ])
    _one_row_per_shape(raw)
