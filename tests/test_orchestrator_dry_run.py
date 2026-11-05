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
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = sorted(glob.glob(os.path.join(REPO_ROOT, "configs", "cases", "*.yaml")))


def _ensure_local_yaml():
    """run_case.py refuses to run without configs/local.yaml (gitignored,
    per-machine). Create a throwaway copy of the example if none exists yet.
    run_case.py also refuses an eulp_metadata_root that is not an existing
    folder, so the copy points it at an empty temporary folder; dry-run mode
    touches no other path inside it."""
    local_path = os.path.join(REPO_ROOT, "configs", "local.yaml")
    example_path = os.path.join(REPO_ROOT, "configs", "local.yaml.example")
    if os.path.exists(local_path):
        return local_path, None
    with open(example_path, encoding="utf-8") as f:
        content = f.read()
    metadata_dir = tempfile.mkdtemp()
    content = re.sub(r"(?m)^eulp_metadata_root:.*$",
                     f'eulp_metadata_root: "{Path(metadata_dir).as_posix()}"', content)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    return local_path, metadata_dir


def test_case_files_exist():
    assert CASES, "no case files found under configs/cases/"


def test_every_case_dry_runs_to_well_formed_posix_commands():
    local_path, metadata_dir = _ensure_local_yaml()
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
        if metadata_dir:
            os.remove(local_path)
            os.rmdir(metadata_dir)


def test_dry_run_verifies_every_day_file_set():
    """Under the committed per_circuit rule, --all verifies 5b and 5c for baseline, dm
    and uncontrolled in the workspace and in each mix_days/<mix>/ subtree that is not
    100 % baseline (mixed and stress in mixes_fixed.json). Under per_group, no --mix."""
    local_path, metadata_dir = _ensure_local_yaml()
    try:
        case_path = os.path.join(REPO_ROOT, "configs", "cases", "NC_GSO_urban__NC.yaml")
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "run_case.py"),
             "--case", case_path, "--all", "--season", "winter", "--dry-run"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        verify = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip().startswith("verify ")]
        expected = [f"verify --phase {p}{s}{m}"
                    for m in ("", " --mix mixed", " --mix stress")
                    for p in ("5b", "5c")
                    for s in ("", " --scenario dm", " --scenario uncontrolled")]
        for line in expected:
            assert verify.count(line) == 1, (line, verify)
        assert not any("baseline" in ln for ln in verify), verify
    finally:
        if metadata_dir:
            os.remove(local_path)
            os.rmdir(metadata_dir)

    sys.path.insert(0, REPO_ROOT)
    import yaml
    from run_case import verify_calls
    with open(os.path.join(REPO_ROOT, "configs", "phases.yaml"), encoding="utf-8") as f:
        mix_days = yaml.safe_load(f)["mix_days"]
    resolved = {"peak_day_rule": "per_group",
                "mixes_file": os.path.join(REPO_ROOT, "0_experimental_design", "mixes_fixed.json")}
    assert verify_calls(mix_days, resolved) == []
    resolved["peak_day_rule"] = "per_circuit"
    assert len(verify_calls(mix_days, resolved)) == 12


if __name__ == "__main__":
    tests =[(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
