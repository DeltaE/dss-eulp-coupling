# 3. Workflow Guide

This section describes the end-to-end workflow and provides runnable commands you can adapt.

```{admonition} Quick Start
:class: important
Adjust paths, states, and design variants as needed. Example commands assume your repo layout matches the folders below.
```

## 3.1 Repository Layout

```
dss-eulp-coupling/
├── 0_download_smartds/       # SMART-DS download and staging
├── 0_experimental_design/    # Experimental design generation
├── 1_data_provenance/        # EULP metadata
├── 2_circuit_matching/       # Circuit-building matching
├── 3_tolerance_matching/     # Feeder peak matching
├── 4_quota_assignment/       # Representative building selection
├── 5a_eulp_downloads/        # EULP data acquisition
├── 5b_profile_generation/    # Profile generation (baseline, DM, uncontrolled)
├── 5c_csv_conversion/        # OpenDSS CSV loadshapes
├── 5d_scenario_controls/     # DM and uncontrolled controls
├── 6_kvar_preparation/       # Reactive power ratios
├── 7_circuit_instantiation/  # Instantiation & simulation
└── 8_results_analysis/       # Aggregation & analysis
```

## 3.2 Phase-by-Phase

`python run_case.py --case configs/cases/<case>.yaml --all --season <season>` runs the phases below. `phase_order` in `configs/defaults.yaml` sets the order:

`pre`, `1`, `2`, `3`, `4`, `5a`, `5b`, `5d`, `5b_variants`, `5c`, `5c_variants`, `6`, `6_variants`, `7a`, `7b`, `7c`, `8`.

`configs/phases.yaml` defines the steps of each phase. `run_case.py` sets `PIPELINE_WORK_ROOT` to `<runs_root>/<case>/<season>/workspace/`, written `<ws>` below. `runs_root` comes from `configs/local.yaml` and is `runs` by default. Every phase reads and writes under `<ws>`. Before anything runs, `--all` checks the workspace of every requested season and refuses to start when any exists. Delete those folders to rerun the case-seasons. `--phase <id>` reruns one phase in the existing workspace. `--dry-run` prints the resolved variables and every command, and writes nothing.

`--all` does not run `0_experimental_design`. Phase 7a copies the mixes file that `mixes_file` in `configs/defaults.yaml` names, the tracked `0_experimental_design/mixes_fixed.json`, into the workspace. `run_mix_generator.py --out <folder>` writes LHS and Sobol mixes to that folder, by default `<runs_root>/0_experimental_design/`.

### Phase pre: SMART-DS staging (0_download_smartds)

- `stage_circuits_plain.py --registry-only` writes `<ws>/feeder_registry.json`.
- `scan_feeders.py` writes `<ws>/parsed_loads.csv`.
- `generate_loads_pivot.py` writes `<ws>/parsed_loads_SUMMARY.csv`.

### Phase 1: EULP metadata (1_data_provenance)

Phase 1 runs `python -m eulp_metadata.build --cluster pipeline_state` with `PYTHONPATH=src`. Its inputs are four EULP baseline metadata CSVs under `eulp_metadata_root`: `Metadata_<ST>_Residential/<ST>_baseline_metadata_and_annual_results.csv` and `Metadata_<ST>_Commercial/<ST>_baseline_metadata_and_annual_results.csv`, for ST = NC and TX. A run reads the pair for its donor state. The residential files come from the OEDI ResStock TMY3 release 2 and the commercial files from the OEDI ComStock AMY2018 release 1, both in the 2024 End-Use Load Profiles collection. `README.md`, section "Prerequisites for a cold clone", gives the direct URLs. Phase 1 writes `residential_data_SELECT_STATES.csv`, `commercial_data_SELECT_STATES.csv`, `manifest.json` and `row_counts.csv` to `<ws>/1_data_provenance/outputs/pipeline_state/`. The manifest and the row counts give output paths relative to the runs root, with forward slashes.

### Phase 2: Circuit matching (2_circuit_matching)

1. `copy_circuits.py` copies the SMART-DS feeders to `<ws>/2_circuit_matching/circuits_plain_format/` and rewrites `<ws>/feeder_registry.json`.
2. `circuit_make_daily_list_sets.py <ws>/2_circuit_matching/circuits_plain_format` extracts the loadshape names of each circuit. Without the argument, the script reads `circuits_plain_format/` under the current folder.
3. `review_parquet_matches.py` writes `review_parquet_matches.csv`.

### Phase 3: Tolerance matching (3_tolerance_matching)

`run_case.py` copies `review_parquet_matches.csv` from Phase 2 into `<ws>/3_tolerance_matching/`. `phase3_match.py` then runs `match_smartds_parquets_impl.py`.

### Phase 4: Quota assignment (4_quota_assignment)

`phase4_cleanup.py` runs `clean_up_bldgs_impl.py`. `phase4_select.py` runs `select_representatives_impl.py`. Phase 4 writes `<STATE>_final_residential.csv` and `<STATE>_final_commercial.csv`.

### Phase 5a: EULP downloads (5a_eulp_downloads)

`run_case.py` copies the two Phase 4 final CSVs into `<ws>/5a_eulp_downloads/`. `phase5a_download_residential.py` and `phase5a_download_commercial.py` then download the EULP parquets from OEDI (open access) to the parquet data root.

### Phases 5b, 5d and 5b_variants: profile generation

- `5b` (`5b_profile_generation`): `phase5b_scale.py` runs `scale_feeder_curves_impl.py`. It reads the two Phase 4 final CSVs from `<ws>/4_quota_assignment/`. `phase5b_peak.py` runs `find_max_day_curve_impl.py`. Together they build the baseline profiles.
- `5d` (`5d_scenario_controls`): `combine_scenarios.py` writes `<ws>/5d_scenario_controls/combine_scenarios/combined_scenarios.csv`. `get_scenario_csv_controls.py` then reads it and selects the controls for the demand management (DM) and uncontrolled variants.
- `5b_variants` (`5b_profile_generation`): `phase5b_variants_dm.py` and `phase5b_variants_uncontrolled.py` build the DM and uncontrolled profiles.

### Phases 5c and 5c_variants: CSV conversion (5c_csv_conversion)

`5c` runs `parquet_to_csv.py` for the baseline profiles. `5c_variants` runs it with `--scenario dm` and then with `--scenario uncontrolled`.

### Phases 6 and 6_variants: reactive power preparation (6_kvar_preparation)

- `6` runs `save_needed_sd_parquets.py`, `compute_kvar_kw_ratios.py` and `generate_kvar_csvs.py`.
- `6_variants` runs `compute_kvar_kw_ratios.py` and `generate_kvar_csvs.py` with `--scenario dm`, and then both again with `--scenario uncontrolled`.

Both phases write `_kvar_` CSVs beside the `_kw_` CSVs.

### Phases 7a, 7b and 7c: circuit instantiation and simulation (7_circuit_instantiation)

- `7a` runs `bridge_phase5c_to_phase7.py` from the repository root. It builds the profile roots `<STATE>_4_profhp`, `<STATE>_6_profhp_dm` and `<STATE>_7_profhp_un` in `<ws>/7_circuit_instantiation/` from the Phase 5c CSVs. It copies the file in `PIPELINE_MIXES_FILE` (`mixes_file` in `configs/defaults.yaml`, the tracked `0_experimental_design/mixes_fixed.json`) byte for byte to `<ws>/7_circuit_instantiation/mixes.json`, and exits 1 when that file is missing. It prints the mix names and the expected circuit folders from that file. It checks the feeder registry at `<ws>/feeder_registry.json`.
- `7b` runs `instantiate_circuits.py`. It reads `<ws>/7_circuit_instantiation/mixes.json`. For each feeder and mix, it prepares a circuit folder, assigns EV, PV, storage and heat pump profiles, and copies and patches the runner `power_flow_sim_daily_EV_STO_DG_deploy.py` into the folder. It writes `heating_assignment__SUMMARY.csv`, `heating_assignment__FULL.csv` and `heating_assignment__FULL.json` to `<ws>/7_circuit_instantiation/`.
- `7c` runs `run_circuits.py --root <ws>/7_circuit_instantiation`. It runs the patched runner in each circuit folder and logs to `<ws>/7_circuit_instantiation/run_log.txt`. No phase runs the runner in the repository folder.

### Phase 8: results analysis

1. `aggregate_m1_m2_with_circuits.py` runs in `7_circuit_instantiation/`. It writes `aggregate_m1.csv`, `aggregate_m2.csv` and `circuit_summary.csv` to `<ws>/7_circuit_instantiation/`.
2. `append_experiment_results.py` runs in `8_results_analysis/`. It reads `aggregate_m2.csv`, `circuit_summary.csv` and `heating_assignment__FULL.csv` from `<ws>/7_circuit_instantiation/`. It tags every row with the season, and with `design` set to the donor state. It writes `aggregate_m2_combined.csv`, `circuit_summary_combined.csv` and `heating_assignment__FULL_combined.csv` to `<ws>/8_results_analysis/`. It exits with an error when an input file is missing.

Phase 8 covers one case-season. `gather_m2_cases.py` stacks `aggregate_m2_combined.csv` from all eight case-seasons into `m2_all_cases_all_seasons.csv` in the runs root (`runs_root` in `configs/local.yaml`, `runs/` by default). `gather_m2_cases.py` reads the workspaces under the runs root. `validate_2x2.py` checks that file. It exits 1 when it finds fewer than 12 `circuit_folder` values, before it writes anything. Otherwise it writes `peaks_per_combo.csv` to the runs root. `--all` runs neither script.

## 3.3 Configuration Highlights

- **Donor states:** NC and TX (`configs/donor_registry.yaml`).
- **Topologies:** `NC_GSO_urban_uhs13_1247` and `TX_AUS_urban_p2uhs12_1247` (`configs/topology_registry.yaml`).
- **Seasons:** summer and winter (`configs/defaults.yaml`).
- **Circuit filtering:** Phase 7b skips the circuits listed in `skip_circuits` in `pipeline_config.yaml`. The list is empty, so `--all` skips no circuit.
- **Scenario mixes:** `--all` uses the three fixed mixes in `0_experimental_design/mixes_fixed.json`, the file that `mixes_file` in `configs/defaults.yaml` names. `run_mix_generator.py` in the same folder generates LHS and Sobol mixes outside the repository, but `--all` does not run it.

| Mix | EV | Storage (3-phase loads) | PV (3-phase loads) | Heat pump shares (baseline / DM / uncontrolled) |
| --- | --- | --- | --- | --- |
| `fire_baseline` | 10% | 5% | 5% | 1.0 / 0.0 / 0.0 |
| `fire_mixed` | 20% | 10% | 10% | 0.5 / 0.3 / 0.2 |
| `fire_stress` | 30% | 15% | 15% | 0.2 / 0.2 / 0.6 |

- **Storage control:** The runner `power_flow_sim_daily_EV_STO_DG_deploy.py` sizes and controls storage. Phase 7b picks the storage hosts and writes them as `storage_targets`.

```{admonition} Tip: Storage Controller Defaults (example)
:class: tip
- Sizing vs. peak: 0.75×  
- Duration: 4 h  
- Peak target factor: 0.8  
- Reserve: 20%
```

## 3.4 Running with `run_case.py`

This section describes what `python run_case.py --case <case> --all` runs. `configs/phases.yaml` defines every step.

### Setup

Copy `configs/local.yaml.example` to `configs/local.yaml`. Set the machine paths: `smart_ds_base` for the SMART-DS data root and `eulp_metadata_root` for the EULP metadata data root. Both are required.

### Configuration

`run_case.py` sets `PIPELINE_*` environment variables. The scripts read the run values only from these variables. A script that reads a run value whose variable is not set exits 1 and names the variable.

| Variable | Meaning |
| --- | --- |
| `PIPELINE_STATE` | Two-letter code of the donor state, from `donor_state` in `configs/donor_registry.yaml`. It sets state-specific metadata, file names and folder prefixes. |
| `PIPELINE_SEASON` | `summer` or `winter`, from `--season` or `seasons` in `configs/defaults.yaml`. |
| `PIPELINE_WORK_ROOT` | The workspace, `<runs_root>/<case>/<season>/workspace`. |
| `PIPELINE_RUNS_ROOT` | `runs_root` from `configs/local.yaml`, absolute, with forward slashes. Phase 1 writes its output paths relative to it. |
| `PIPELINE_SMART_DS_ROOT` | Root of the SMART-DS OpenDSS feeder folders: `smart_ds_base` from `configs/local.yaml`, then `smart_ds_relpath` and `circuit_folder` from `configs/topology_registry.yaml`. The feeder registry stores paths relative to this root. |
| `PIPELINE_FEEDER_REGISTRY_PATH` | Path of the feeder registry. `run_case.py` sets it to `feeder_registry.json` in the workspace. |
| `PIPELINE_MAX_FEEDERS` | Feeder limit, from `execution.max_feeders` in the case file. The value `none` or `null` removes the limit. |
| `PIPELINE_PARQUET_ROOT` | EULP parquet pool of the topology: the `parquet_data` folder beside its OpenDSS tree under `smart_ds_base`, or `parquet_relpath` in `configs/topology_registry.yaml`. Phases 2, 5a, 5b, 5d and 5b_variants use it. |
| `PIPELINE_SMART_DS_PARQUET_ROOT` | Original SMART-DS load parquets with kW and kvar, the same folder as `PIPELINE_PARQUET_ROOT`. Phase 6 reads them. |
| `PIPELINE_EULP_METADATA_ROOT` | Folder of the four EULP baseline metadata CSVs, from `eulp_metadata_root` in `configs/local.yaml`. Phase 1 reads them. |
| `PIPELINE_EULP_DOWNLOAD_DATE` | Date stamp in the EULP download folder names, from `eulp_download_date` of the donor in `configs/donor_registry.yaml`. |
| `PIPELINE_MIXES_FILE` | Mixes file that Phase 7a copies, from `mixes_file` in `configs/defaults.yaml`, absolute, with forward slashes. |

`pipeline_config.yaml` holds only the method parameters:

- `random_seed` seeds representative building selection in Phase 4 and case `0` of `run_mix_generator.py`.
- `skip_circuits` lists numeric `circuit_id` values that Phase 7 skips.
- `quota` sets the Phase 4 quota rules.

### Phase outputs

Outputs land in `<runs_root>/<case>/<season>/workspace/`. Phase 5a writes its EULP parquets to the parquet data root.

| Phase | Scripts | Outputs |
| --- | --- | --- |
| pre | `stage_circuits_plain.py --registry-only`, `scan_feeders.py`, `generate_loads_pivot.py` | `feeder_registry.json`, `parsed_loads.csv`, `parsed_loads_SUMMARY.csv` |
| 1 | `eulp_metadata.build --cluster pipeline_state` | `commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv`, a manifest and row counts in `1_data_provenance/outputs/pipeline_state/` |
| 2 | `copy_circuits.py`, `circuit_make_daily_list_sets.py`, `review_parquet_matches.py` | `circuits_plain_format/`, one `daily_list_set_*.pkl` per circuit, `review_parquet_matches.csv` |
| 3 | `phase3_match.py` | `df_com_matches_out_<STATE>.csv`, `df_res_matches_out_<STATE>.csv` |
| 4 | `phase4_cleanup.py`, `phase4_select.py` | Filtered metadata CSVs, building source maps, `<STATE>_final_commercial.csv`, `<STATE>_final_residential.csv` |
| 5a | `phase5a_download_residential.py`, `phase5a_download_commercial.py` | EULP parquet folders under the parquet data root |
| 5b | `phase5b_scale.py`, `phase5b_peak.py` | `<STATE>_parquet_and_bldgs.csv`, `<STATE>_required_parquets_per_feeder.csv`, baseline daily parquets |
| 5d | `combine_scenarios.py`, `get_scenario_csv_controls.py` | `combine_scenarios/combined_scenarios.csv`, `get_scenario_csv_controls/*_dm.csv` and `*_uncontrolled.csv` |
| 5b_variants | `phase5b_variants_dm.py`, `phase5b_variants_uncontrolled.py` | DM and uncontrolled daily parquets in `5b_profile_generation/daily_parquets/` |
| 5c | `parquet_to_csv.py` | Circuit loadshape CSV folders, `folder_timestamps.pkl`, `folder_equiv.pkl`, `folder_list_loadshapes.pkl` |
| 6 | `save_needed_sd_parquets.py`, `compute_kvar_kw_ratios.py`, `generate_kvar_csvs.py` | `needed_parquets.pkl`, `kvar_ratios.pkl`, `_kvar_` CSVs beside the `_kw_` CSVs |
| 7b | `instantiate_circuits.py` | Prepared circuit folders, `profiles_use_bench/` |
| 7c | `run_circuits.py` | OpenDSS monitor CSVs in each circuit folder |
| 8 | `aggregate_m1_m2_with_circuits.py`, `append_experiment_results.py` | `aggregate_m1.csv`, `aggregate_m2.csv`, `circuit_summary.csv` in `7_circuit_instantiation/`; combined CSVs in `8_results_analysis/` |

### Wrappers

The `phase*.py` scripts are thin wrappers around the implementation scripts.

| Wrapper | Implementation |
| --- | --- |
| `phase3_match.py` | `match_smartds_parquets_impl.py` |
| `phase4_cleanup.py` | `clean_up_bldgs_impl.py` |
| `phase4_select.py` | `select_representatives_impl.py` |
| `phase5a_download_residential.py` | `download_parquets_residential_impl.py` |
| `phase5a_download_commercial.py` | `download_parquets_commercial_impl.py` |
| `phase5b_scale.py` | `scale_feeder_curves_impl.py` |
| `phase5b_peak.py` | `find_max_day_curve_impl.py` |
| `phase5b_variants_dm.py` | `find_max_day_curve_dm_impl.py` |
| `phase5b_variants_uncontrolled.py` | `find_max_day_curve_uncontrolled_impl.py` |

### Script notes

- `circuit_make_daily_list_sets.py` extracts the loadshape names of each circuit into a pickle.
- `review_parquet_matches.py` computes monthly statistics of the SMART-DS load parquets for matching.
- `combine_scenarios.py` produces the table that drives scenario-control selection.
- `save_needed_sd_parquets.py` lists the source parquets that Phase 6 needs.

### Handoffs

- `run_case.py` copies `review_parquet_matches.csv` from Phase 2 into `3_tolerance_matching/` before Phase 3.
- Phase 3 reads the Phase 1 metadata outputs.
- Phase 5b reads `parsed_loads_SUMMARY.csv`, the feeder registry, the Phase 4 final CSVs and the Phase 5a EULP parquets.
- Phase 5d reads the Phase 5b mapping CSVs from `5b_profile_generation/`.
- Phase 5b_variants and Phase 5c read the Phase 5d controls from `5d_scenario_controls/get_scenario_csv_controls/`.
- Phase 5c reads the daily parquets from `5b_profile_generation/daily_parquets/`.
- Phase 6 reads the Phase 5b mapping CSV, the Phase 5c CSV folders and `folder_timestamps.pkl`.
- Phase 7a copies `0_experimental_design/mixes_fixed.json` to `7_circuit_instantiation/mixes.json` in the workspace. Phase 7b reads that copy.
- Phase 7 reads the profile roots `<STATE>_4_profhp`, `<STATE>_6_profhp_dm` and `<STATE>_7_profhp_un`. It indexes the CSVs under their `daily_csvs/` subfolders. Phase 7a builds these roots from the Phase 5c CSVs.
- Phase 8 reads the Phase 7 outputs from `7_circuit_instantiation/`.
