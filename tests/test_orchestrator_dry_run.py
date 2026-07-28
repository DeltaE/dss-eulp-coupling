# -*- coding: utf-8 -*-
"""
test_orchestrator_dry_run.py
------------------------------
Exercises every case in configs/cases/ through run_case.py --dry-run and
confirms every emitted command is well-formed POSIX (shlex.split() doesn't
raise) and invokes this interpreter (sys.executable), not a bare "python"
(BLOCKER 3/4). Needs no SMART-DS/EULP data -- dry-run only prints commands,
it never executes or touches paths.

Run directly (no pytest needed): python tests/test_orchestrator_dry_run.py
Or under pytest: pytest tests/test_orchestrator_dry_run.py
"""
import glob
import os
import shlex
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = sorted(glob.glob(os.path.join(REPO_ROOT, "configs", "cases", "*.yaml")))


def _ensure_local_yaml():
    """run_case.py refuses to run without configs/local.yaml (gitignored,
    per-machine). Create a throwaway copy of the example if none exists yet
    -- dry-run mode never touches the paths inside it, so the example's
    placeholder Windows path is fine here."""
    local_path = os.path.join(REPO_ROOT, "configs", "local.yaml")
    example_path = os.path.join(REPO_ROOT, "configs", "local.yaml.example")
    if os.path.exists(local_path):
        return local_path, False
    with open(example_path, encoding="utf-8") as f:
        content = f.read()
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    return local_path, True


def test_case_files_exist():
    assert CASES, "no case files found under configs/cases/"


def test_every_case_dry_runs_to_well_formed_posix_commands():
    local_path, created = _ensure_local_yaml()
    try:
        for case_path in CASES:
            proc = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "run_case.py"),
                 "--case", case_path, "--all", "--dry-run"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
            )
            case_name = os.path.basename(case_path)
            assert proc.returncode == 0, (
                f"{case_name}: dry-run exited {proc.returncode}\nstderr:\n{proc.stderr}"
            )
            run_lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("run (")]
            assert run_lines, f"{case_name}: no 'run (...)' commands emitted"
            for ln in run_lines:
                cmd = ln.split(": ", 1)[1]
                tokens = shlex.split(cmd)  # must not raise -- well-formed POSIX argv
                assert tokens, f"{case_name}: empty command line: {ln!r}"
                assert tokens[0] == sys.executable, (
                    f"{case_name}: expected commands to invoke {sys.executable}, "
                    f"got {tokens[0]!r} in: {ln!r}"
                )
    finally:
        if created:
            os.remove(local_path)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
