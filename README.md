# DSS-EULP Coupling Pipeline

Open-data coupling of SMART-DS synthetic distribution feeders with NREL End-Use
Load Profiles (EULP) for distribution system planning under uncertainty.

## Configuration

Each value has one owner:

- `configs/local.yaml` holds the machine paths: `smart_ds_base`, `eulp_metadata_root` and `runs_root`. Copy it from `configs/local.yaml.example`.
- A case file in `configs/cases/` names a topology, a donor and `execution.max_feeders`. `configs/topology_registry.yaml` and `configs/donor_registry.yaml` hold the values of each topology and donor, such as the feeder folder, the donor state and `eulp_download_date`.
- `configs/defaults.yaml` holds the seasons, the phase order and `mixes_file`.
- `pipeline_config.yaml` holds the method parameters: `random_seed`, `skip_circuits` and `quota`.

`run_case.py` resolves these files and passes the run values to each script as `PIPELINE_*` environment variables. `docs/workflow.md`, section 3.4, lists them. A script that reads a run value whose variable is not set exits 1 and names the variable. Run the pipeline through `run_case.py`.

The primary runnable scripts are state-agnostic.

## Pipeline Phases

| Phase | Folder | Purpose |
| --- | --- | --- |
| pre | `0_download_smartds/` | Download SMART-DS feeders from OEDI and stage plain OpenDSS circuits |
| 0 | `0_experimental_design/` | Hold the fixed mixes (`mixes_fixed.json`); generate LHS and Sobol mixes (`mixes_lhs.json`, `mixes_sobol.json`) outside the repository |
| 1 | `1_data_provenance/` | Build state-specific EULP metadata CSVs |
| 2 | `2_circuit_matching/` | Flatten SMART-DS feeders and review parquet matches |
| 3 | `3_tolerance_matching/` | Match feeder peaks to EULP buildings |
| 4 | `4_quota_assignment/` | Filter, stratify, and select representative buildings |
| 5a | `5a_eulp_downloads/` | Download EULP parquet profiles from OEDI |
| 5b | `5b_profile_generation/` | Build baseline, DM, and uncontrolled peak-day parquet slices |
| 5c | `5c_csv_conversion/` | Convert daily parquet slices to OpenDSS CSV loadshapes |
| 5d | `5d_scenario_controls/` | Split baseline profile mappings into DM/uncontrolled controls |
| 6 | `6_kvar_preparation/` | Prepare kvar ratios and kvar CSV loadshapes |
| 7 | `7_circuit_instantiation/` | Instantiate circuits, run OpenDSS batches, QA, and aggregate |
| 8 | `8_results_analysis/` | Append experiment outputs and generate analysis figures |

## Prerequisites

- Python 3.9+ with `pip install -r requirements.txt`.
- SMART-DS feeder data from OEDI, with `smart_ds_base` in `configs/local.yaml` pointing to the data root.
- OEDI / NREL EULP metadata and profile access. The download scripts use public OEDI S3 endpoints.
- Enough local disk for parquet and CSV profile data.
- Windows + OpenDSS installed for phase 7 (`comtypes` uses the OpenDSS COM interface).

## Prerequisites for a cold clone

Copy `configs/local.yaml.example` to `configs/local.yaml`. Set the machine paths: `smart_ds_base` for the SMART-DS data root and `eulp_metadata_root` for the EULP metadata data root.

The pipeline resolves two SMART-DS topologies under `smart_ds_base`. Each provides a `base_timeseries/opendss/<feeder>` tree and a co-located `parquet_data` pool:

- `GSO/urban-suburban/` (feeder `uhs13_1247`)
- `AUS/P2U/` (feeder `p2uhs12_1247`)

Place the four EULP baseline metadata CSVs at these paths under `eulp_metadata_root`:

- `Metadata_NC_Residential/NC_baseline_metadata_and_annual_results.csv`
- `Metadata_NC_Commercial/NC_baseline_metadata_and_annual_results.csv`
- `Metadata_TX_Residential/TX_baseline_metadata_and_annual_results.csv`
- `Metadata_TX_Commercial/TX_baseline_metadata_and_annual_results.csv`

Keep the file names exactly as downloaded, because Phase 1 writes them into its outputs.

Each CSV downloads directly from OEDI. Each URL returns the exact bytes the pipeline uses:

- NC residential: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/resstock_tmy3_release_2/metadata_and_annual_results/by_state/state=NC/csv/NC_baseline_metadata_and_annual_results.csv
- NC commercial: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/metadata_and_annual_results/by_state/state=NC/csv/NC_baseline_metadata_and_annual_results.csv
- TX residential: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/resstock_tmy3_release_2/metadata_and_annual_results/by_state/state=TX/csv/TX_baseline_metadata_and_annual_results.csv
- TX commercial: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/metadata_and_annual_results/by_state/state=TX/csv/TX_baseline_metadata_and_annual_results.csv

Run these eight commands from the repository root:

```powershell
python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --season summer
python run_case.py --case configs/cases/NC_GSO_urban__TX.yaml --all --season summer
python run_case.py --case configs/cases/TX_AUS_urban__NC.yaml --all --season summer
python run_case.py --case configs/cases/TX_AUS_urban__TX.yaml --all --season summer
python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --season winter
python run_case.py --case configs/cases/NC_GSO_urban__TX.yaml --all --season winter
python run_case.py --case configs/cases/TX_AUS_urban__NC.yaml --all --season winter
python run_case.py --case configs/cases/TX_AUS_urban__TX.yaml --all --season winter
```

Each run writes its workspace to `<runs_root>/<case>/<season>/workspace/`. `--all` refuses to start when the workspace of any requested season already exists. `--dry-run` prints the resolved variables and every command, and writes nothing.

### Reproduction record

Verified on 2026-09-21. A fresh clone at `61461cd` reproduced all eight case-seasons on Windows, with Python 3.11.7 and OpenDSS 9.8.0.1 through the COM interface. The comparison covered 110,268 output files. All matched byte for byte. Eight `row_counts.csv` files are excluded because they record absolute paths. `validation_summary.csv` is no longer produced.

## Run Sequence

`run_case.py` runs every phase with the `PIPELINE_*` variables set. To run one phase by hand, run it through `run_case.py` from the repository root. `--phase <id>` runs that phase in the existing workspace:

```powershell
python run_case.py --case <case> --phase <id> --season <season>
```

`--all` runs these phases in this order:

```powershell
python run_case.py --case <case> --phase pre --season <season>          # SMART-DS registry and load scan
python run_case.py --case <case> --phase 1 --season <season>            # EULP metadata
python run_case.py --case <case> --phase 2 --season <season>            # circuit matching
python run_case.py --case <case> --phase 3 --season <season>            # tolerance matching
python run_case.py --case <case> --phase 4 --season <season>            # quota assignment
python run_case.py --case <case> --phase 5a --season <season>           # EULP parquet downloads
python run_case.py --case <case> --phase 5b --season <season>           # baseline profiles
python run_case.py --case <case> --phase 5d --season <season>           # scenario controls (combine_scenarios.py)
python run_case.py --case <case> --phase 5b_variants --season <season>  # DM and uncontrolled profiles
python run_case.py --case <case> --phase 5c --season <season>           # CSV conversion
python run_case.py --case <case> --phase 5c_variants --season <season>  # CSV conversion, DM and uncontrolled
python run_case.py --case <case> --phase 6 --season <season>            # kvar preparation
python run_case.py --case <case> --phase 6_variants --season <season>   # kvar preparation, DM and uncontrolled
python run_case.py --case <case> --phase 7a --season <season>           # profile bridge and mixes.json
python run_case.py --case <case> --phase 7b --season <season>           # circuit instantiation
python run_case.py --case <case> --phase 7c --season <season>           # OpenDSS runs
python run_case.py --case <case> --phase 8 --season <season>            # aggregation and results
```

`configs/phases.yaml` lists the scripts of each phase. Each phase reads the outputs of the phases before it, so a hand run starts with `pre` in an empty workspace.

These steps are outside the phases:

```powershell
# Download SMART-DS from OEDI into <smart_ds_base>/<region>/<subregion>/.
python .\0_download_smartds\download_smartds.py `
  --regions GSO AUS `
  --subregions urban-suburban P2U `
  --scenarios base_timeseries `
  --only-opendss `
  --output-dir <smart_ds_base>

# Generate LHS and Sobol mixes into <runs_root>/0_experimental_design/, or into the --out folder.
python .\0_experimental_design\run_mix_generator.py --out <folder>
```

`run_mix_generator.py` writes nothing inside the repository. `--all` does not use its output: Phase 7a copies the file that `mixes_file` in `configs/defaults.yaml` names.

## Key Handoffs

| Artifact | Producer | Consumer |
| --- | --- | --- |
| `commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv` | `1_data_provenance` cluster `pipeline_state` | `3_tolerance_matching/phase3_match.py` |
| `{STATE}_required_parquets_per_feeder_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5b_profile_generation/phase5b_variants_dm.py` |
| `{STATE}_parquet_and_bldgs_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5c_csv_conversion/parquet_to_csv.py` |
| `profiles_use_bench/` | `7_circuit_instantiation/instantiate_circuits.py` | `7_circuit_instantiation/power_flow_sim_daily_EV_STO_DG_deploy.py` |
| `0_experimental_design/mixes_fixed.json` (three hand-set mixes, tracked) | Set by hand, not by `run_mix_generator.py` | `bridge_phase5c_to_phase7.py` (Phase 7a) copies it to `<ws>/7_circuit_instantiation/mixes.json`, which `7_circuit_instantiation/instantiate_circuits.py` reads |

## Citation

If you use this pipeline, please cite:

```bibtex
@article{victorgallardo2026coupling,
  title={Open-Data Coupling of Synthetic Distribution Feeders with End-Use Load Profiles
         for Distribution System Planning Under Uncertainty},
  author={Victor-Gallardo, Luis and co-authors and Niet, Taco},
  journal={MethodsX},
  year={2026},
  note={Submitted}
}
```

## License

[Apache-2.0](LICENSE)
