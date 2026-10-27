# Phase 1: EULP metadata

Phase 1 builds the statewide building metadata tables that Phases 3 and 4 read.
It runs one cluster, `pipeline_state`. The code builds that cluster for the donor
state of the case, so it holds one state: NC or TX.

## Inputs

Phase 1 reads four CSV files under `eulp_metadata_root` in `configs/local.yaml`:

```
Metadata_NC_Residential/NC_baseline_metadata_and_annual_results.csv
Metadata_NC_Commercial/NC_baseline_metadata_and_annual_results.csv
Metadata_TX_Residential/TX_baseline_metadata_and_annual_results.csv
Metadata_TX_Commercial/TX_baseline_metadata_and_annual_results.csv
```

A run reads the residential and commercial pair of its donor state. README.md,
section "Prerequisites for a cold clone", gives the source of each file.

`config/workflow.yaml` names the folder pattern for each dataset and the columns
that Phase 1 keeps.

## How it runs

`run_case.py` runs Phase 1. It sets `PIPELINE_EULP_METADATA_ROOT` from
`eulp_metadata_root` and runs, from this folder with `PYTHONPATH=src`:

```
python -m eulp_metadata.build --cluster pipeline_state
```

Without `PIPELINE_EULP_METADATA_ROOT`, the command exits 1 and names
`eulp_metadata_root`.

These flags remain:

- `--check-inputs` reports whether the input CSVs exist. It exits 1 when one is
  missing.
- `--dry-run` prints the plan and writes nothing.
- `--list-clusters` prints the cluster names.
- `--config` selects another workflow YAML file.

## Outputs

Phase 1 writes four files to
`<workspace>/1_data_provenance/outputs/pipeline_state/`:

- `residential_data_SELECT_STATES.csv`
- `commercial_data_SELECT_STATES.csv`
- `manifest.json`: the plan, the inputs and a summary of each table.
- `row_counts.csv`: rows and columns of each table.
