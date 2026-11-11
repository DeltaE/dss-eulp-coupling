# -*- coding: utf-8 -*-
"""
test_dss_engine_linux.py
-------------------------
Synthetic-circuit smoke test for dss_engine.py (BLOCKER 1). No SMART-DS/EULP
data needed -- builds a minimal circuit in code and solves it through the
shim, not opendssdirect directly, so it exercises the same code path
power_flow_sim_daily_EV_STO_DG_deploy.py does.

Run directly (no pytest needed): python tests/test_dss_engine_linux.py
Or under pytest: pytest tests/test_dss_engine_linux.py
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))

from dss_engine import create_dss_engine  # noqa: E402


def _build_and_solve(circuit_name="smoketest"):
    dss = create_dss_engine()
    dss.AllowForms = False
    dss.Start(0)
    text = dss.Text
    circuit = dss.ActiveCircuit

    text.Command = "clear"
    text.Command = f"new circuit.{circuit_name} basekv=12.47 pu=1.0 phases=3"
    text.Command = "new load.l1 bus1=sourcebus phases=3 kv=12.47 kw=100 kvar=30 model=1"
    text.Command = "set mode=daily"
    text.Command = "set stepsize=15m"
    text.Command = "set number=96"
    text.Command = "set controlmode=time"
    circuit.Solution.Solve()
    return dss, text, circuit


def test_daily_mode_96_step_converges():
    _, _, circuit = _build_and_solve()
    assert circuit.Solution.Converged is True
    assert circuit.Solution.Mode == 1           # daily
    assert circuit.Solution.Number == 96
    assert circuit.Solution.StepSize == 900.0   # 15 minutes, in seconds


def test_converged_is_real_bool_not_callable():
    """Guards BLOCKER 1's silent-bug risk: opendssdirect exposes Converged as
    a callable, so a missing pair of parens there silently returns a truthy
    bound method instead of raising. The shim exposes it as a Python
    property, making that mistake structurally impossible at call sites that
    go through this shim."""
    _, _, circuit = _build_and_solve()
    converged = circuit.Solution.Converged
    assert isinstance(converged, bool), f"expected bool, got {type(converged)}"
    assert converged is True


def test_result_reads_back_element_property():
    """.Command / .Result duck-type the COM settable-property / readable-
    property pair, matching the '? Load.x.kW' element-property query style
    the audit confirmed works identically on both backends."""
    _, text, _ = _build_and_solve(circuit_name="smoketest2")
    text.Command = "? Load.l1.kW"
    assert text.Result.strip() == "100"


def test_backend_override_rejects_unknown_value():
    try:
        create_dss_engine(backend="not-a-real-backend")
        raise AssertionError("expected ValueError for an unknown backend")
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
