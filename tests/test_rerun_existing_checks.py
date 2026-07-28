# -*- coding: utf-8 -*-
"""
test_rerun_existing_checks.py
--------------------------------
The two pre-existing checks the audit calls out by name as needing to pass
on Linux: verify_phase7_readiness.py (diagnostic sweep) and
3_tolerance_matching/test_tolerance_match.py (synthetic-data correctness
harness, no real data needed). Both are plain scripts, not pytest suites;
this just re-runs them as subprocesses and asserts a clean exit, so a future
change that breaks either shows up here instead of only being caught by
someone running them by hand.

Run directly (no pytest needed): python tests/test_rerun_existing_checks.py
Or under pytest: pytest tests/test_rerun_existing_checks.py
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_verify_phase7_readiness_runs_clean():
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "verify_phase7_readiness.py")],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "REPORT COMPLETE" in proc.stdout


def test_tolerance_match_harness_passes():
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "3_tolerance_matching", "test_tolerance_match.py")],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "ALL TESTS PASSED" in proc.stdout


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
