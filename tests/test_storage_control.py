# -*- coding: utf-8 -*-
"""
test_storage_control.py
-----------------------
storage_control.py (Phase 7 deploy, the storage rules) on a hand-made 96-step curve:
simple targets from the peak and mean, tuned targets whose energy above kWTarget equals
the batteries' usable energy and whose recharge below kWTargetLow returns them to their
start, a schedule that keeps kW, kWh and reserve and ends at its starting energy, and
the service line of each host in a small hand-written circuit.

Run directly (no pytest needed): python tests/test_storage_control.py
Or under pytest: pytest tests/test_storage_control.py
"""
import math
import os
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "7_circuit_instantiation", "deployer_modules"))
from storage_control import feeding_lines, schedule, simple_targets, tuned_targets  # noqa: E402

DT = 0.25
STEPS = np.arange(96)
# Night valley around 04:00, evening peak around 18:00 (kW)
CURVE = 1000.0 - 400.0 * np.cos((STEPS - 16) / 96.0 * 2.0 * np.pi)


def test_simple_targets():
    target, low = simple_targets(CURVE, 0.98, 0.80)
    assert math.isclose(target, 0.98 * CURVE.max())
    assert math.isclose(low, 0.80 * CURVE.mean())


def test_tuned_energy_above_target_equals_usable():
    kw, kwh, reserve, eff_c, eff_d = 200.0, 400.0, 0.2, 0.95, 0.95
    target, low, usable, delivered, recharge = tuned_targets(CURVE, kw, kwh, reserve, eff_c, eff_d, DT)
    assert math.isclose(usable, kwh * (1 - reserve) * eff_d)
    above = np.maximum(0.0, CURVE - target).sum() * DT
    assert math.isclose(above, usable, rel_tol=1e-6)
    assert target >= CURVE.max() - kw
    assert math.isclose(delivered, usable, rel_tol=1e-6)        # the kW limit does not bind here
    assert math.isclose(recharge, delivered / (eff_d * eff_c))
    below = np.minimum(kw, np.maximum(0.0, low - CURVE)).sum() * DT
    assert math.isclose(below, recharge, rel_tol=1e-6)
    assert low < target


def test_tuned_target_not_below_peak_minus_kw():
    # a small battery power: the target stays at the peak minus its kW
    target, _, _, delivered, _ = tuned_targets(CURVE, 10.0, 400.0, 0.2, 0.95, 0.95, DT)
    assert math.isclose(target, CURVE.max() - 10.0)
    assert delivered <= 10.0 * 96 * DT


def test_schedule_keeps_limits_and_ends_at_start():
    kw, kwh, start, reserve, eff_c, eff_d = 150.0, 300.0, 0.2, 0.2, 0.95, 0.95
    net, energy, x = schedule(CURVE, kw, kwh, start, reserve, eff_c, eff_d, DT)
    assert x > 0
    assert np.all(np.abs(net) <= kw + 1e-9)
    assert energy.min() >= reserve * kwh - 1e-6 and energy.max() <= kwh + 1e-6
    assert math.isclose(energy[0], start * kwh) and math.isclose(energy[-1], start * kwh, abs_tol=1e-6)
    # discharge at the peak, charge in the valley
    assert net[int(np.argmax(CURVE))] > 0 and net[int(np.argmin(CURVE))] < 0
    after = CURVE - net
    assert after.max() < CURVE.max() and after.min() > CURVE.min()


def test_schedule_without_room_is_empty():
    # start at the reserve on a falling curve: the peak comes before any valley, so the
    # battery has nothing to give at the peak and the schedule stays (almost) empty
    falling = np.linspace(2000.0, 500.0, 96)
    net, energy, x = schedule(falling, 100.0, 200.0, 0.2, 0.2, 0.95, 0.95, DT)
    assert x < 1e-6 and np.abs(net).max() < 1e-3 and np.allclose(energy, 40.0, atol=1e-6)


def test_feeding_lines():
    dss = """
New Transformer.t1 phases=1 windings=3 buses=[mv.1 sec.1.0 sec.0.2] kvs=[7.2 0.12 0.12]
New Line.drop_a bus1=sec.1.2 bus2=a.1.2 phases=2
New Line.drop_b bus1=b.1.2 bus2=a.1.2 phases=2
New Line.open bus1=sec.1.2 bus2=c.1.2 phases=2 enabled=n
New Line.drop_c bus1=c.1.2 bus2=sec.1.2 phases=2
"""
    out = feeding_lines([dss], {"h_a": ("a.1", "t1"), "h_b": ("b.2", "t1"), "h_c": ("c.1", "t1"),
                                "h_sec": ("sec.1", "t1"), "h_none": ("a.1", None)})
    assert out["h_a"] == ("drop_a", 1)
    assert out["h_b"] == ("drop_b", 2)     # bus2 of drop_b is the end nearer the transformer
    assert out["h_c"] == ("drop_c", 2)     # the switched-out line is left out
    assert out["h_sec"] is None and out["h_none"] is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
