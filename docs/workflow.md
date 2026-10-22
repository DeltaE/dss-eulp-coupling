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

### Phase 1: Experimental Design (0_experimental_design)
- Generate scenario dictionaries using DOE (LHS/Sobol). `N_CASES` controls scenario count.
- **Key script:** `run_mix_generator.py`
- **Outputs:** `mixes_lhs.json`, `mixes_sobol.json`

```bash
cd 0_experimental_design
python run_mix_generator.py
```

### Phase 2: Circuit ↔ Building Matching (2_circuit_matching to 4_quota_assignment)

**Sequential scripts:**
1. `copy_circuits.py` — Copy Smart-DS circuits to working dir  
2. `circuit_make_daily_list_sets.py` — Extract daily load patterns  
3. `review_parquet_matches.py` — Review available parquet files  
4. `match_smartds_parquets_impl.py` — Match circuits to EULP profiles  
5. `clean_up_bldgs_impl.py` — Filter/organize building data  
6. `select_rep_family_v2.py` — Select representative buildings

```bash
cd ../2_circuit_matching
python copy_circuits.py
python circuit_make_daily_list_sets.py
python review_parquet_matches.py
cd ../3_tolerance_matching
python match_smartds_parquets_impl.py
cd ../4_quota_assignment
python clean_up_bldgs_impl.py
python select_rep_family_v2.py
```

### Phase 3: Data Acquisition (5a_eulp_downloads)
Download EULP parquet files from OEDI (open access).

```bash
cd ../5a_eulp_downloads
python phase5a_download_homes.py
python phase5a_download_commercial.py
```

### Phase 4: Profile Generation (5b_profile_generation, 5d_scenario_controls)
Variants: **baseline** (`phase5b_peak.py`), **demand management** (`phase5b_variants_dm.py`), **uncontrolled** (`phase5b_variants_uncontrolled.py`), all in `5b_profile_generation`.

**Typical workflow:**
```bash
cd ../5b_profile_generation
python scale_feeder_curves_impl.py
python find_max_day_curve_impl.py
cd ../5d_scenario_controls
python plot_parquet_differences.py
python get_scenario_csv_controls.py
```

### Phase 5: Reactive Power Preparation (6_kvar_preparation)
Run the longer job to build reactive power ratios (kVAr/kW).

```bash
cd ../6_kvar_preparation
python rev_spec_kvar_kw_ratio.py   # ~579 minutes for full dataset
```

### Phase 6: Circuit Instantiation & Simulation (7_circuit_instantiation)
Create circuit instances, assign DERs, and run power flow simulations.

- **Main script:** `instantiate_circuits_and_runs_APPLYFILTER.py`
- **Runner:** `power_flow_sim_daily_EV_STO_DG_deploy.py`
- **Features:** EV assignments (controlled/uncontrolled), PV/storage placement, heat pump profiles (baseline/DM/uncontrolled)

```bash
cd ../7_circuit_instantiation
python instantiate_circuits_and_runs_APPLYFILTER.py
python power_flow_sim_daily_EV_STO_DG_deploy.py
```

### Phase 7: Results Analysis (8_results_analysis)
Aggregate across scenarios, seasons, and DOE designs.

```bash
cd ../8_results_analysis
python append_experiment_results.py
```

## 3.3 Configuration Highlights

- **States:** NC, TX, CA (with circuit filtering for connection issues)
- **Seasons:** Summer, Winter
- **Scenario parameters:** EV 5–80%, storage 0–20%, PV 0–20%, heat pump shares (baseline/DM/uncontrolled)
- **Storage control:** Peak shaving algorithm customizable (see `get_scenario_csv_controls.py` and instantiation scripts)

```{admonition} Tip — Storage Controller Defaults (example)
:class: tip
- Sizing vs. peak: 0.75×  
- Duration: 4 h  
- Peak target factor: 0.8  
- Reserve: 20%
```

## 3.4 Running with `run_case.py`

This section describes what `python run_case.py --case <case> --all` runs. `configs/phases.yaml` defines every step.

### Setup

Copy `configs/local.yaml.example` to `configs/local.yaml`. Set the machine paths, including the SMART-DS data root.

### Configuration

`run_case.py` sets `PIPELINE_*` environment variables. Each one overrides the matching key in `pipeline_config.yaml`.

| Variable | Meaning |
| --- | --- |
| `PIPELINE_STATE` | Two-letter code of the donor state. It sets state-specific metadata, file names and folder prefixes. |
| `PIPELINE_SMART_DS_ROOT` | Root of the SMART-DS OpenDSS feeder folders. The feeder registry stores paths relative to this root. |
| `PIPELINE_FEEDER_REGISTRY_PATH` | Path of the feeder registry. `run_case.py` sets it to `feeder_registry.json` in the workspace. |
| `PIPELINE_MAX_FEEDERS` | Feeder limit for fire tests. The value `none` or `null` removes the limit. |
| `PIPELINE_SMART_DS_PARQUET_ROOT` | Original SMART-DS load parquets with kW and kvar. Phase 6 reads them. |

These keys still come from `pipeline_config.yaml`:

- `eulp_download_date` is the date stamp in the EULP download folder names.
- `random_seed` seeds representative building selection in Phase 4.
- `skip_circuits` lists numeric `circuit_id` values that Phase 7 skips.

### Phase outputs

Outputs land in `runs/<case>/<season>/workspace/`. Phase 5a writes its EULP parquets to the parquet data root.

| Phase | Scripts | Outputs |
| --- | --- | --- |
| pre | `stage_circuits_plain.py --registry-only`, `scan_feeders.py`, `generate_loads_pivot.py` | `feeder_registry.json`, `parsed_loads.csv`, `parsed_loads_SUMMARY.csv` |
| 1 | `eulp_metadata.build --cluster pipeline_state` | `commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv`, a manifest and row counts in `1_data_provenance/outputs/pipeline_state/` |
| 2 | `copy_circuits.py`, `circuit_make_daily_list_sets.py`, `review_parquet_matches.py` | `circuits_plain_format/`, one `daily_list_set_*.pkl` per circuit, `review_parquet_matches.csv` |
| 3 | `phase3_match.py` | `df_com_matches_out_<STATE>.csv`, `df_res_matches_out_<STATE>.csv` |
| 4 | `phase4_cleanup.py`, `phase4_select.py` | Filtered metadata CSVs, building source maps, `<STATE>_final_commercial.csv`, `<STATE>_final_residential.csv` |
| 5a | `phase5a_download_homes.py`, `phase5a_download_commercial.py` | EULP parquet folders under the parquet data root |
| 5b | `phase5b_scale.py`, `phase5b_peak.py` | `<STATE>_parquet_and_bldgs.csv`, `<STATE>_required_parquets_per_feeder.csv`, baseline daily parquets |
| 5d | `plot_parquet_differences.py`, `get_scenario_csv_controls.py` | `plot_parquet_differences/combined_scenarios.csv`, `get_scenario_csv_controls/*_dm.csv` and `*_uncontrolled.csv` |
| 5b_variants | `phase5b_variants_dm.py`, `phase5b_variants_uncontrolled.py` | DM and uncontrolled daily parquets in `5b_profile_generation/daily_parquets/` |
| 5c | `parquet_to_csv.py` | Circuit loadshape CSV folders, `folder_timestamps.pkl`, `folder_equiv.pkl`, `folder_list_loadshapes.pkl` |
| 6 | `save_needed_sd_parquets.py`, `rev_spec_kvar_kw_ratio.py`, `generate_kvar_csvs.py` | `needed_parquets.pkl`, `kvar_ratios.pkl`, `_kvar_` CSVs beside the `_kw_` CSVs |
| 7b | `instantiate_circuits_and_runs_APPLYFILTER.py` | Prepared circuit folders, `profiles_use_bench/` |
| 7c | `run_all_deploys_v2.py` | OpenDSS monitor CSVs in each circuit folder |
| 8 | `aggregate_m1_m2_with_circuits.py`, `append_experiment_results.py` | `aggregate_m1.csv`, `aggregate_m2.csv`, `circuit_summary.csv` in `7_circuit_instantiation/`; combined CSVs in `8_results_analysis/` |

### Wrappers

The `phase*.py` scripts are thin wrappers around the implementation scripts.

| Wrapper | Implementation |
| --- | --- |
| `phase3_match.py` | `match_smartds_parquets_impl.py` |
| `phase4_cleanup.py` | `clean_up_bldgs_impl.py` |
| `phase4_select.py` | `select_rep_family_v2.py` |
| `phase5a_download_homes.py` | `download_parquets_homes_redo_impl.py` |
| `phase5a_download_commercial.py` | `download_parquets_commercial_redo_impl.py` |
| `phase5b_scale.py` | `scale_feeder_curves_impl.py` |
| `phase5b_peak.py` | `find_max_day_curve_impl.py` |
| `phase5b_variants_dm.py` | `find_max_day_curve_dm_impl.py` |
| `phase5b_variants_uncontrolled.py` | `find_max_day_curve_uncontrolled_impl.py` |

### Script notes

- `circuit_make_daily_list_sets.py` extracts the loadshape names of each circuit into a pickle.
- `review_parquet_matches.py` computes monthly statistics of the SMART-DS load parquets for matching.
- `plot_parquet_differences.py` produces the table that drives scenario-control selection.
- `save_needed_sd_parquets.py` lists the source parquets that Phase 6 needs.

### Handoffs

- `run_case.py` copies `review_parquet_matches.csv` from Phase 2 into `3_tolerance_matching/` before Phase 3.
- Phase 3 reads the Phase 1 metadata outputs.
- Phase 5b reads `parsed_loads_SUMMARY.csv`, the feeder registry, the Phase 4 final CSVs and the Phase 5a EULP parquets.
- Phase 5d reads the Phase 5b mapping CSVs from `5b_profile_generation/`.
- Phase 5b_variants and Phase 5c read the Phase 5d controls from `5d_scenario_controls/get_scenario_csv_controls/`.
- Phase 5c reads the daily parquets from `5b_profile_generation/daily_parquets/`.
- Phase 6 reads the Phase 5b mapping CSV, the Phase 5c CSV folders and `folder_timestamps.pkl`.
- Phase 7a copies `0_experimental_design/mixes_lhs.json` to `7_circuit_instantiation/mixes_lhs.json` in the workspace. Phase 7b reads that copy.
- Phase 7 reads the profile roots `<STATE>_4_profhp`, `<STATE>_6_profhp_dm` and `<STATE>_7_profhp_un`. It indexes the CSVs under their `daily_csvs/` subfolders. Phase 7a builds these roots from the Phase 5c CSVs.
- Phase 8 reads the Phase 7 outputs from `7_circuit_instantiation/`.
