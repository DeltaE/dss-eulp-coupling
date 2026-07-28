# -*- coding: utf-8 -*-
"""
test_case_sensitivity.py
-------------------------
BLOCKER 2's highest-value test. ext4 is genuinely case-sensitive (unlike the
Windows machine that produced the existing results), so this is meaningful
here in a way it never could be there: tests/fixtures/normal_case_feeder/ and
tests/fixtures/lower_case_feeder/ are the same circuit, one with the usual
SMART-DS casing (Master.dss/Loads.dss/LoadShapes.dss, 'Redirect Loads.dss'),
one with everything lowercased (master.dss/loads.dss/loadshapes.dss,
'Redirect loads.dss') -- asserting the pipeline handles both identically.

Run directly (no pytest needed): python tests/test_case_sensitivity.py
Or under pytest: pytest tests/test_case_sensitivity.py
"""
import ast
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
NORMAL_FEEDER = os.path.join(FIXTURES, "normal_case_feeder")
LOWER_FEEDER = os.path.join(FIXTURES, "lower_case_feeder")

sys.path.insert(0, REPO_ROOT)
from pipeline_utils import resolve_dss_file  # noqa: E402

sys.path.insert(0, REPO_ROOT)  # scan_topology_universe.py is import-safe (guarded __main__)
import scan_topology_universe as stu  # noqa: E402


def _extract_deploy_script_function(name):
    """The deploy script is copied per-instance into each circuit folder and
    is not import-safe (it runs top-level code immediately), so extract the
    one function under test by source instead of duplicating its logic here."""
    path = os.path.join(REPO_ROOT, "7_circuit_instantiation",
                         "power_flow_sim_daily_EV_STO_DG_deploy.py")
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            ns = {"os": os}
            exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
            return ns[name]
    raise AssertionError(f"{name} not found in {path}")


def test_resolve_dss_file_finds_normal_case():
    p = resolve_dss_file(NORMAL_FEEDER, "Loads.dss")
    assert p.name == "Loads.dss"
    assert p.exists()


def test_resolve_dss_file_finds_lower_case():
    p = resolve_dss_file(LOWER_FEEDER, "Loads.dss")
    assert p.name == "loads.dss"
    assert p.exists()


def test_resolve_dss_file_raises_clearly_when_absent():
    try:
        resolve_dss_file(NORMAL_FEEDER, "Storage.dss")
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as e:
        assert "Storage.dss" in str(e)


def test_deploy_script_is_feeder_dir_accepts_both_cases():
    is_feeder_dir = _extract_deploy_script_function("is_feeder_dir")
    assert is_feeder_dir(NORMAL_FEEDER) is True
    assert is_feeder_dir(LOWER_FEEDER) is True


def test_deploy_script_resolve_dss_file_matches_both_cases():
    resolve = _extract_deploy_script_function("resolve_dss_file")
    assert os.path.basename(resolve(NORMAL_FEEDER, "Loads.dss")) == "Loads.dss"
    assert os.path.basename(resolve(LOWER_FEEDER, "Loads.dss")) == "loads.dss"


def test_scan_topology_universe_has_required_dss_accepts_both_cases():
    from pathlib import Path
    assert stu.has_required_dss(Path(NORMAL_FEEDER)) is True
    assert stu.has_required_dss(Path(LOWER_FEEDER)) is True


def test_scan_topology_universe_count_loads_matches_both_cases():
    from pathlib import Path
    assert stu.count_loads(Path(NORMAL_FEEDER)) == 2
    assert stu.count_loads(Path(LOWER_FEEDER)) == 2


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
