# 7. API & Script Reference

You can document key scripts and functions, even if they are not a formal Python package.

## 7.1 Autodoc (optional)

If your modules are importable (e.g., your repo is a package or you add the repo root to `sys.path`), you can use `autodoc`.

**Important:** Read the Docs won't have OpenDSS or Windows COM. The `conf.py` sets `autodoc_mock_imports` so imports like `win32com` and `comtypes` won't break the build.

## 7.2 CLI / Script Docs

The scripts carry their own module docstrings. `docs/workflow.md` lists which script each
phase runs. There are no per-script pages under `docs/scripts/`.
