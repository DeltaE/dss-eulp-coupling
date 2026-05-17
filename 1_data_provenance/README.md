# EULP Metadata Reproduction

This project is a copy-only clean workspace created from an existing local NREL/OEDI EULP metadata workflow.

Source copied from:

```
C:\Users\luisf\Dropbox\1_RESEARCH\1_FOCUS_PhD\6_Paper_3_Expander\workflow_download_metadata
```

The source folder was treated as read-only. Large local data are kept under `data_raw/` and `data_derived/historical/`, both gitignored.

## Reproduction CLI

The generalized workflow is configured in one file: `config/workflow.yaml`.

Examples:

```powershell
$env:PYTHONPATH = "src"
python -m eulp_metadata.build --list-clusters
python -m eulp_metadata.build --cluster paper3_baseline --check-inputs
python -m eulp_metadata.build --cluster paper3_baseline --dry-run
python -m eulp_metadata.build --cluster paper3_baseline --validate
python -m eulp_metadata.build --cluster canadian_proxy --validate
```

If the local `python` launcher is unavailable, the same commands work through `uv`:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
$env:PYTHONPATH = "src"
uv run --no-project python -m eulp_metadata.build --cluster paper3_baseline --validate
```

Generated CSVs, `manifest.json`, `row_counts.csv`, and validation reports are written under `outputs/<cluster_name>/`.

The workflow is cache-first: downloaded metadata CSVs under `data_raw/` are reused by default because downloading them is slow. The recovered download-stage entries in `config/workflow.yaml` are fallback/provenance instructions for rebuilding missing cached source folders.
