# -*- coding: utf-8 -*-
"""
test_environment_pins.py
--------------------------
Cheap canary against the worst Linux-port failure mode: someone runs the
pipeline under system Python (3.8.10 here) with whatever numpy/pandas/scipy/
pyarrow that interpreter happens to have, gets a result, and never notices it
doesn't match the validated Windows baseline. Asserts Python 3.11.x and the
exact pinned versions from requirements.txt / PROMPT_Linux_Port_v2.md SS0.

Run directly (no pytest needed): python tests/test_environment_pins.py
Or under pytest: pytest tests/test_environment_pins.py
"""
import sys

PINNED_VERSIONS = {
    "numpy": "1.26.4",
    "pandas": "2.1.4",
    "scipy": "1.11.4",
    "pyarrow": "14.0.2",
    "matplotlib": "3.8.0",
    "yaml": "6.0.1",       # PyYAML; __version__ lives on the `yaml` module
    "requests": "2.31.0",
    "urllib3": "2.0.7",
}


def test_python_is_3_11():
    assert sys.version_info[:2] == (3, 11), (
        f"running under Python {sys.version_info.major}.{sys.version_info.minor}, "
        f"but this pipeline is pinned to 3.11 -- see requirements.txt"
    )


def test_numerically_relevant_packages_are_pinned_versions():
    mismatches = []
    for module_name, expected in PINNED_VERSIONS.items():
        try:
            mod = __import__(module_name)
        except ImportError:
            mismatches.append(f"{module_name}: NOT INSTALLED (expected {expected})")
            continue
        actual = getattr(mod, "__version__", None)
        if actual != expected:
            mismatches.append(f"{module_name}: installed {actual!r}, expected {expected!r}")
    assert not mismatches, "version pin mismatch(es):\n  " + "\n  ".join(mismatches)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
