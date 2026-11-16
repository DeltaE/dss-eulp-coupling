# -*- coding: utf-8 -*-
"""
test_given_days.py
------------------
peak_day_rule given: read_given_days on a valid file and each of its stops,
uses_mix_days for every rule, peak_day_rule accepting given, and run_case.py --dry-run
with a settings folder that holds given_days.csv, lacks it, or holds it without the
rule. Needs no SMART-DS/EULP data.

Run directly (no pytest needed): python tests/test_given_days.py
Or under pytest: pytest tests/test_given_days.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_utils import (GIVEN_DAYS_FILE, SETTINGS_ENV, STEPS_PER_DAY, peak_day_rule,  # noqa: E402
                            read_given_days, shared_peak_day, uses_mix_days)
from test_caller_settings import _ensure_local_yaml  # noqa: E402

HEADER = "Feeder,Season,Month,Day\n"
VALID = HEADER + "uhs13_1247--udt4015,summer,6,19\nuhs13_1247--udt4015,winter,2,16\n"


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def _read(text, bom=False):
    """read_given_days on a temporary folder holding text as given_days.csv: the dict,
    or "stop" when it exits 1."""
    folder = tempfile.mkdtemp()
    try:
        with open(os.path.join(folder, GIVEN_DAYS_FILE), "w", encoding="utf-8-sig" if bom else "utf-8") as f:
            f.write(text)
        try:
            return read_given_days(folder)
        except SystemExit as e:
            assert e.code == 1
            return "stop"
    finally:
        shutil.rmtree(folder)


def test_read_given_days_valid():
    expected = {("uhs13_1247--udt4015", "summer"): (6, 19), ("uhs13_1247--udt4015", "winter"): (2, 16)}
    assert _read(VALID) == expected
    assert _read(VALID, bom=True) == expected


def test_read_given_days_stops():
    folder = tempfile.mkdtemp()
    try:
        try:
            read_given_days(folder)
            missing = "read"
        except SystemExit as e:
            missing = e.code
        assert missing == 1
    finally:
        shutil.rmtree(folder)
    assert _read("Feeder,Season,Month\nf,summer,6\n") == "stop"
    assert _read(HEADER) == "stop"
    assert _read(HEADER + ",summer,6,19\n") == "stop"
    assert _read(HEADER + "f,spring,4,19\n") == "stop"
    assert _read(HEADER + "f,summer,x,19\n") == "stop"
    assert _read(HEADER + "f,winter,2,29\n") == "stop"
    assert _read(HEADER + "f,summer,10,1\n") == "stop"
    assert _read(HEADER + "f,summer,6,19\nf,summer,7,1\n") == "stop"


def test_uses_mix_days():
    assert uses_mix_days("given", True)
    assert uses_mix_days("given", False)
    assert not uses_mix_days("per_circuit", True)
    assert uses_mix_days("per_circuit", False)
    assert not uses_mix_days("per_group", True)
    assert not uses_mix_days("per_group", False)
    # per_substation: every mix, 100 % baseline included, with or without growth
    assert uses_mix_days("per_substation", True) and uses_mix_days("per_substation", False)
    assert uses_mix_days("per_substation", True, True)


def _year(peaks):
    """A 365-day year of 15-minute values, 1.0 everywhere apart from {(day of year from 0,
    step of the day): value}."""
    values = [1.0] * (365 * STEPS_PER_DAY)
    for (day, step), value in peaks.items():
        values[day * STEPS_PER_DAY + step] = value
    return values


def test_shared_peak_day_of_two_curves():
    """peak_day_rule per_substation: the peak day of the sum of the curves, not of either."""
    # 1 July is day 181, 10 July day 190, 20 July day 200 (a 365-day year)
    a = _year({(181, 40): 9.0, (190, 60): 6.0})          # its own peak day: 1 July
    b = _year({(200, 50): 8.0, (190, 60): 5.0})          # its own peak day: 20 July
    assert shared_peak_day([a], (6, 7, 8))[:2] == (7, 1)
    assert shared_peak_day([b], (6, 7, 8))[:2] == (7, 20)
    assert shared_peak_day([a, b], (6, 7, 8)) == (7, 10, 11.0)     # 6 + 5 at the same step
    # the months of the season bound the search; winter is January, February and December
    c = _year({(10, 5): 4.0, (350, 5): 7.0, (190, 60): 50.0})
    assert shared_peak_day([c], (12, 1, 2)) == (12, 17, 7.0)
    assert shared_peak_day([c], (1, 2)) == (1, 11, 4.0)
    # a tie takes the first day of the year; no curve or no whole day of the months gives None
    assert shared_peak_day([_year({})], (6, 7, 8))[:2] == (6, 1)
    assert shared_peak_day([], (6, 7, 8)) is None
    assert shared_peak_day([[1.0] * STEPS_PER_DAY], (6, 7, 8)) is None


def test_peak_day_rule_accepts_given():
    assert peak_day_rule({"peak_day_rule": "given"}) == "given"


def _dry_run(folder):
    env = {k: v for k, v in os.environ.items() if k != SETTINGS_ENV}
    case_path = os.path.join(REPO_ROOT, "configs", "cases", "NC_GSO_urban__NC.yaml")
    return subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "run_case.py"), "--case", case_path,
         "--all", "--season", "summer", "--dry-run", "--settings", folder],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


def test_dry_run_given_days():
    local_path, metadata_dir = _ensure_local_yaml()
    folder = tempfile.mkdtemp()
    try:
        _write(folder, "pipeline_config.yaml", "peak_day_rule: given\n")
        _write(folder, GIVEN_DAYS_FILE, VALID)
        proc = _dry_run(folder)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        lines = [ln.strip() for ln in proc.stdout.splitlines()]
        assert ("settings given_days.csv: uhs13_1247--udt4015 summer 06-19, "
                "uhs13_1247--udt4015 winter 02-16") in lines, proc.stdout
        assert any("verify" in ln and "--phase 5b --mix baseline" in ln for ln in lines), proc.stdout

        os.remove(os.path.join(folder, GIVEN_DAYS_FILE))
        proc = _dry_run(folder)
        assert proc.returncode == 1
        assert f"[FAIL] peak_day_rule given: {Path(folder).resolve().as_posix()}/given_days.csv not found." \
            in proc.stdout

        os.remove(os.path.join(folder, "pipeline_config.yaml"))
        _write(folder, GIVEN_DAYS_FILE, VALID)
        proc = _dry_run(folder)
        assert proc.returncode == 1
        assert "[FAIL]" in proc.stdout and "peak_day_rule is per_circuit" in proc.stdout, proc.stdout

        # per_substation: accepted without given_days.csv; the mix_days checks cover every mix
        os.remove(os.path.join(folder, GIVEN_DAYS_FILE))
        _write(folder, "pipeline_config.yaml", "peak_day_rule: per_substation\n")
        proc = _dry_run(folder)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        lines = [ln.strip() for ln in proc.stdout.splitlines()]
        assert "peak_day_rule=per_substation" in lines, proc.stdout
        for mix in ("baseline", "mixed", "stress"):
            for phase in ("5b", "5c"):
                assert any("verify" in ln and ln.endswith(f"--phase {phase} --mix {mix}") for ln in lines), \
                    (mix, phase, proc.stdout)
    finally:
        shutil.rmtree(folder)
        if metadata_dir:
            os.remove(local_path)
            os.rmdir(metadata_dir)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
