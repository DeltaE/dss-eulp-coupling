# 7. API & Script Reference

You can document key scripts and functions, even if they are not a formal Python package.

## 7.1 Autodoc (optional)

If your modules are importable (e.g., your repo is a package or you add the repo root to `sys.path`), you can use `autodoc`:

```{code-block} rst
.. automodule:: 0_code_xlrm.run_mix_generator
   :members:
   :undoc-members:
   :show-inheritance:
```

**Important:** Read the Docs won't have OpenDSS or Windows COM. The `conf.py` sets `autodoc_mock_imports` so imports like `win32com` and `comtypes` won't break the build.

## 7.2 CLI / Script Docs

If you prefer documenting scripts by hand, create subpages like:

- `scripts/run_mix_generator.md`
- `scripts/match_smartds_parquets_NC.md`
- `scripts/instantiate_circuits_and_runs_APPLYFILTER.md`

Each page should include **Purpose**, **Inputs**, **Outputs**, **Key Flags/Parameters**, and **Examples**.
