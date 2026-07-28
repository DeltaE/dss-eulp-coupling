# -*- coding: utf-8 -*-
"""
test_import_sweep.py
----------------------
Catches residual Windows-only (or otherwise unavailable) imports across the
repo, beyond the already-known comtypes/win32 cases.

This resolves every top-level import *target* found by static analysis
(ast), rather than literally exec'ing each of the ~90 .py files in place: most
of them are CLI entry points with unguarded top-level code (argparse.parse_args(),
file I/O, network calls) that would fail for reasons having nothing to do with
platform portability -- e.g. "no --smartds-root given" is not a Linux-port bug.
Actually importing each module is what BLOCKER 1's audit trail was built on
(`import comtypes.client as cc` was found exactly this way); this sweep is the
generalization of that same check to every file, minus the false-positive
noise a literal execution sweep would produce.

Run directly (no pytest needed): python tests/test_import_sweep.py
Or under pytest: pytest tests/test_import_sweep.py
"""
import ast
import importlib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXCLUDE_DIRS = {".git", "archive", "__pycache__", "tests"}

# sys_platform markers a module's import is expected to be gated behind
# (checked informally here: if a name only exists in the win32-only set,
# skip it on this platform rather than fail).
_WIN32_ONLY_MODULES = {"comtypes", "win32com", "win32api", "pywintypes"}


def _iter_repo_python_files():
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


_ALL_PY_FILES = list(_iter_repo_python_files())
_LOCAL_MODULE_STEMS = {os.path.splitext(os.path.basename(p))[0] for p in _ALL_PY_FILES}


def _top_level_imports(path):
    """Return the set of top-level module names a file imports (the part
    before the first dot, matching what `import`/`importlib.import_module`
    resolves against)."""
    # utf-8-sig strips a leading BOM if present (behaves like plain utf-8
    # otherwise) -- ast.parse() rejects a literal U+FEFF at the start of a
    # str the way the real import machinery silently tolerates it in bytes,
    # so plain "utf-8" here would flag a BOM-prefixed-but-otherwise-fine file
    # as a syntax error.
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return set(), f"SyntaxError: {e}"
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import, not resolvable as a top-level name
            if node.module:
                names.add(node.module.split(".")[0])
    return names, None


def test_no_syntax_errors():
    failures = []
    for path in _ALL_PY_FILES:
        _, err = _top_level_imports(path)
        if err:
            failures.append(f"{os.path.relpath(path, REPO_ROOT)}: {err}")
    assert not failures, "syntax errors:\n  " + "\n  ".join(failures)


def test_every_top_level_import_resolves_on_this_platform():
    unresolved = {}  # module_name -> set of files that import it
    for path in _ALL_PY_FILES:
        names, err = _top_level_imports(path)
        if err:
            continue  # reported by test_no_syntax_errors
        for name in names:
            if name in _LOCAL_MODULE_STEMS:
                continue  # this repo's own module, not an installed package
            if name in sys.stdlib_module_names:
                continue
            if name in _WIN32_ONLY_MODULES and sys.platform != "win32":
                continue  # correctly gated elsewhere (sys_platform markers / try-except)
            try:
                importlib.import_module(name)
            except ImportError:
                unresolved.setdefault(name, set()).add(os.path.relpath(path, REPO_ROOT))

    if unresolved:
        detail = "\n".join(
            f"  {name}: imported by {sorted(files)}" for name, files in sorted(unresolved.items())
        )
        raise AssertionError(f"unresolved top-level import(s) on {sys.platform}:\n{detail}")


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
              if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED (swept {len(_ALL_PY_FILES)} files)")
