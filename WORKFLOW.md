# DSS-EULP Coupling Workflow

This document captures the current pipeline without changing script behavior.
Several scripts still have legacy names or local handoffs; those are called out
explicitly so a new user can reproduce the workflow and so future renames can be
reviewed safely.

## 1. Prerequisites

### Python and dependencies

Run from an Anaconda Prompt on Windows unless noted otherwise.

- Python 3.9 or newer.
- Install repository dependencies from the repo root:

```bat
cd /d D:\github\dss-eulp-coupling
pip install -r requirements.txt
```

Key packages are `pandas`, `numpy`, `pyarrow`, `PyYAML`, `matplotlib`,
`requests`, `urllib3`, and `selenium`. Phase 7 also needs `comtypes` on Windows
and an OpenDSS COM installation.

### `pipeline_config.yaml`

The root `pipeline_config.yaml` is the shared configuration source for the
parameterized scripts.

| Key | Meaning |
| --- | --- |
| `state` | Two-letter state code used for state-specific metadata, filenames, and output folder prefixes. |
| `season` | Active season label, usually `summer` or `winter`. Several scripts generate both seasonal slices, but Phase 7 folder naming and summaries use this label. |
| `smart_ds_root` | Root containing SMART-DS OpenDSS feeder folders. The registry stores paths relative to this root. |
| `parquet_data_root` | Root containing downloaded EULP parquet folders such as `parquet_residential_short_20250330_NC`. |
| `eulp_download_date` | Date stamp embedded in EULP download folder names. |
| `random_seed` | Shared seed used by representative selection and scenario generation. |
| `skip_circuits` | Optional list of numeric `circuit_id` values to skip in Phase 7. |
| `max_feeders` | Optional feeder limit for fire tests. Use `null` for a full run. |
| `feeder_registry_path` | Optional path to the generated feeder registry. Not present in the default file, but supported by `pipeline_utils.py`. |

Example NC configuration:

```yaml
state: "NC"
season: "summer"
smart_ds_root: "D:/lvg/GSO/rural/base_timeseries/opendss"
parquet_data_root: "D:/lvg/parquet_data"
eulp_download_date: "20250330"
random_seed: 555
skip_circuits: []
max_feeders: null
```

Example TX fire-test configuration:

```yaml
state: "TX"
season: "summer"
smart_ds_root: "D:/lvg/AUS/rural/base_timeseries/opendss"
parquet_data_root: "D:/lvg/parquet_data"
eulp_download_date: "20250330"
random_seed: 555
skip_circuits: []
max_feeders: 2
```

### Environment variable overrides

The following environment variables override `pipeline_config.yaml` for the
current Anaconda Prompt session:

| Variable | Overrides |
| --- | --- |
| `PIPELINE_STATE` | `state` |
| `PIPELINE_SEASON` | `season` |
| `PIPELINE_SMART_DS_ROOT` | `smart_ds_root` |
| `PIPELINE_SMART_DS_PARQUET_ROOT` | `smart_ds_parquet_root` |
| `PIPELINE_FEEDER_REGISTRY_PATH` | `feeder_registry_path` |
| `PIPELINE_MAX_FEEDERS` | `max_feeders`; use `none` or `null` to clear the limit |

Example:

```bat
set PIPELINE_STATE=NC
set PIPELINE_SEASON=summer
set PIPELINE_SMART_DS_ROOT=D:\lvg\GSO\rural\base_timeseries\opendss
set PIPELINE_MAX_FEEDERS=2
```

### SMART-DS data

SMART-DS data can be downloaded with `0_download_smartds/download_smartds.py`.
The source dataset is SMART-DS v1.0 on the public OEDI data lake under
`s3://oedi-data-lake/SMART-DS/v1.0/`.

Start with the focused download/staging instructions in
`0_download_smartds/README.md`. The scripts support two common layouts:

- Repo-local download root:
  `0_download_smartds\data_raw\smartds\...`
- Existing external data root:
  `D:\lvg\GSO\rural\base_timeseries\opendss`

The current matching scripts also expect SMART-DS source load parquets in a
local `parquet_data` folder for Phase 2, and Phase 6 reads original
reactive-power parquets from `smart_ds_parquet_root`
(`PIPELINE_SMART_DS_PARQUET_ROOT`). Those two paths are handoff points listed
below.

## 2. Phase-by-phase execution

All commands below assume this starting point:

```bat
cd /d D:\github\dss-eulp-coupling
```

For fire tests, append `--max-feeders N` to the Pre-phase staging and scanning
commands. For full runs, omit that option.

| Phase | Directory | Script(s) | Input | Output | Command |
| --- | --- | --- | --- | --- | --- |
| Pre | `0_download_smartds` | `download_smartds.py`, `stage_circuits_plain.py`, `scan_feeders.py`, `generate_loads_pivot.py` | SMART-DS OpenDSS feeders and optional downloaded SMART-DS load parquets | `feeder_registry.json`, optional staged circuits, `parsed_loads.csv`, `parsed_loads_SUMMARY.csv` | `python 0_download_smartds\stage_circuits_plain.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --registry feeder_registry.json --registry-only`<br>`python 0_download_smartds\scan_feeders.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --output parsed_loads.csv`<br>`python 0_download_smartds\generate_loads_pivot.py --input parsed_loads.csv --output parsed_loads_SUMMARY.csv` |
| 0 | `0_experimental_design` | `run_mix_generator.py` | `pipeline_config.yaml` | `mixes_lhs.json`, `mixes_sobol.json`, `mixes_compare_long.csv`, `lhs_vs_sobol_summary.csv`, QA plots | `python 0_experimental_design\run_mix_generator.py` |
| 1 | `1_data_provenance` | `src\eulp_metadata\build.py` | `1_data_provenance\data_raw`, `1_data_provenance\data_derived\historical`, `pipeline_config.yaml` | `1_data_provenance\outputs\pipeline_state\commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv`, manifests, row counts | `pushd 1_data_provenance`<br>`set PYTHONPATH=src`<br>`python -m eulp_metadata.build --cluster pipeline_state --validate`<br>`popd` |
| 2 | `2_circuit_matching` | `copy_circuits.py`, `circuit_make_daily_list_sets.py`, `review_parquet_matches.py` | `smart_ds_root`, SMART-DS source load parquets in `2_circuit_matching\parquet_data` | `2_circuit_matching\circuits_plain_format`, per-circuit `daily_list_set_*.pkl`, `2_circuit_matching\review_parquet_matches.csv`, root `feeder_registry.json` | `pushd 2_circuit_matching`<br>`python copy_circuits.py`<br>`python circuit_make_daily_list_sets.py`<br>`python review_parquet_matches.py`<br>`popd` |
| 3 | `3_tolerance_matching` | `match_smartds_parquets.py` | `review_parquet_matches.csv`, Phase 1 metadata outputs | `df_com_matches_out_%PIPELINE_STATE%.csv`, `df_res_matches_out_%PIPELINE_STATE%.csv` | `copy /Y 2_circuit_matching\review_parquet_matches.csv 3_tolerance_matching\review_parquet_matches.csv`<br>`pushd 3_tolerance_matching`<br>`python match_smartds_parquets.py`<br>`popd` |
| 4 | `4_quota_assignment` | `clean_up_bldgs.py`, `select_rep_family.py` | Phase 3 match outputs, Phase 1 metadata outputs | filtered metadata CSVs, source maps, `%PIPELINE_STATE%_final_commercial.csv`, `%PIPELINE_STATE%_final_residential.csv` | `pushd 4_quota_assignment`<br>`python clean_up_bldgs.py`<br>`python select_rep_family.py`<br>`popd` |
| 5a | `5a_eulp_downloads` | `download_parquets_homes_redo.py`, `download_parquets_commercial_redo.py` | Phase 4 filtered metadata copied into `5a_eulp_downloads`, OEDI EULP profile access | EULP parquet folders under `parquet_data_root` | `copy /Y 4_quota_assignment\residential_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\`<br>`copy /Y 4_quota_assignment\commercial_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\`<br>`pushd 5a_eulp_downloads`<br>`python download_parquets_homes_redo.py`<br>`python download_parquets_commercial_redo.py`<br>`popd` |
| 5b | `5b_profile_generation` | `scale_feeder_curves.py`, `find_max_day_curve.py` | root `parsed_loads_SUMMARY.csv`, root `feeder_registry.json`, Phase 4 final representative CSVs, Phase 5a EULP parquets | `%PIPELINE_STATE%_parquet_and_bldgs.csv`, `%PIPELINE_STATE%_required_parquets_per_feeder.csv`, baseline daily parquets | `copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_commercial.csv 5b_profile_generation\`<br>`copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_residential.csv 5b_profile_generation\`<br>`pushd 5b_profile_generation`<br>`python scale_feeder_curves.py`<br>`python find_max_day_curve.py`<br>`popd` |
| 5d | `5d_scenario_controls` | `plot_parquet_differences.py`, `get_scenario_csv_controls.py` | Phase 5a EULP parquets, Phase 5b baseline mapping CSVs | `plot_parquet_differences\combined_scenarios.csv`, `get_scenario_csv_controls\*_dm.csv`, `*_uncontrolled.csv` | `pushd 5d_scenario_controls`<br>`python plot_parquet_differences.py`<br>`python get_scenario_csv_controls.py`<br>`popd` |
| 5b variants | `5b_profile_generation` | `find_max_day_curve_dm.py`, `find_max_day_curve_uncontrolled.py` | Phase 5d DM/uncontrolled control CSVs and Phase 5a EULP parquets | DM and uncontrolled daily parquets under `5b_profile_generation\daily_parquets` | `pushd 5b_profile_generation`<br>`python find_max_day_curve_dm.py`<br>`python find_max_day_curve_uncontrolled.py`<br>`popd` |
| 5c | `5c_csv_conversion` | `parquet_to_csv.py` | `5b_profile_generation\daily_parquets`, root `feeder_registry.json`, Phase 5d DM mapping CSV | circuit loadshape CSV folders, `folder_timestamps.pkl`, `folder_equiv.pkl`, `folder_list_loadshapes.pkl` | `pushd 5c_csv_conversion`<br>`python parquet_to_csv.py`<br>`popd` |
| 6 | `6_kvar_preparation` | `save_needed_sd_parquets.py`, `rev_spec_kvar_kw_ratio.py`, `generate_kvar_csvs.py` | Phase 5b mapping CSV, Phase 5c CSV folders and `folder_timestamps.pkl`, original source parquets at `smart_ds_parquet_root` | `needed_parquets.pkl`, `kvar_ratios.pkl`, matching `_kvar_` CSVs beside `_kw_` CSVs | copy/symlink Phase 5c CSV folders and `folder_timestamps.pkl` into `6_kvar_preparation`, then:<br>`pushd 6_kvar_preparation`<br>`python save_needed_sd_parquets.py`<br>`python rev_spec_kvar_kw_ratio.py`<br>`python generate_kvar_csvs.py`<br>`popd` |
| 7 | `7_circuit_instantiation` | `instantiate_circuits_and_runs_APPLYFILTER.py`, `run_all_deploys_v2.py`, `check_monitor_outputs.py`, `aggregate_m1_m2_with_circuits.py` | root `feeder_registry.json`, `smart_ds_root`, `0_experimental_design\mixes_lhs.json`, profile roots `%PIPELINE_STATE%_4_profhp`, `%PIPELINE_STATE%_6_profhp_dm`, `%PIPELINE_STATE%_7_profhp_un` | prepared circuit folders, `profiles_use_bench`, OpenDSS monitor CSVs, `aggregate_m1.csv`, `aggregate_m2.csv`, `circuit_summary.csv`, heating assignment audit files | `pushd 7_circuit_instantiation`<br>`python instantiate_circuits_and_runs_APPLYFILTER.py`<br>`python run_all_deploys_v2.py`<br>`python check_monitor_outputs.py`<br>`python aggregate_m1_m2_with_circuits.py`<br>`popd` |
| 8 | `8_results_analysis` | `append_experiment_results.py`, `append_xlrm_long_format.py`, `figure_generation_methodsx_v3.py` | Phase 7 aggregate CSVs, Phase 0 scenario long CSV, Phase 3 commercial match CSV | combined CSVs and figure PNGs in `8_results_analysis` | `pushd 8_results_analysis`<br>`python append_experiment_results.py`<br>`python append_xlrm_long_format.py`<br>`python figure_generation_methodsx_v3.py`<br>`popd` |

## 3. Inter-phase handoffs

These are the fragile places where the current scripts depend on copied files,
symlinks, or a shared generated location.

| Source path | Destination path | Current handoff | Could be automated? |
| --- | --- | --- | --- |
| `0_download_smartds\parsed_loads_SUMMARY.csv` if generated from inside that folder | `parsed_loads_SUMMARY.csv` at repo root | Avoid this copy by running `generate_loads_pivot.py --output parsed_loads_SUMMARY.csv` from the repo root. | Yes. Make the output path config-driven and always root-relative. |
| `feeder_registry.json` from `stage_circuits_plain.py` or `2_circuit_matching\copy_circuits.py` | repo root `feeder_registry.json` | Must exist at the repo root unless `PIPELINE_FEEDER_REGISTRY_PATH` points elsewhere. | Mostly automated already; keep a single registry producer. |
| SMART-DS source load parquets | `2_circuit_matching\parquet_data` | `review_parquet_matches.py` hardcodes `./parquet_data`. Copy or symlink the needed SMART-DS load parquets before Phase 2 review. | Yes. Read from `pipeline_config.yaml` instead of a local folder. |
| `2_circuit_matching\review_parquet_matches.csv` | `3_tolerance_matching\review_parquet_matches.csv` | Manual copy required before running Phase 3. | Yes. Phase 3 can read from Phase 2 output path directly. |
| `4_quota_assignment\residential_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv` and commercial equivalent | `5a_eulp_downloads\` | Manual copy required because Phase 5a download scripts read filtered metadata from their current folder. | Yes. Phase 5a can search Phase 4 outputs or use config paths. |
| `4_quota_assignment\%PIPELINE_STATE%_final_commercial.csv` and `%PIPELINE_STATE%_final_residential.csv` | `5b_profile_generation\` | Manual copy required because `scale_feeder_curves.py` reads final representative CSVs from its current folder. | Yes. Read from Phase 4 output path. |
| `5b_profile_generation\%PIPELINE_STATE%_parquet_and_bldgs.csv` and `%PIPELINE_STATE%_required_parquets_per_feeder.csv` | `5d_scenario_controls\get_scenario_csv_controls.py` | No copy required if files remain in `5b_profile_generation`; Phase 5d already checks there. | Already partially automated. |
| `5d_scenario_controls\get_scenario_csv_controls\*_dm.csv` and `*_uncontrolled.csv` | `5b_profile_generation` and `5c_csv_conversion` | No copy required for the current wrappers; they read from the Phase 5d output folder. | Already partially automated. |
| `5b_profile_generation\daily_parquets` | `5c_csv_conversion` | No copy required; Phase 5c searches `..\5b_profile_generation\daily_parquets`. | Already automated. |
| Phase 5c circuit CSV folders plus `folder_timestamps.pkl` | `6_kvar_preparation\` | Manual copy or symlink required before Phase 6 because the Phase 6 scripts operate in their current folder. | Yes. Add an output root such as `daily_csvs` to config. |
| Original SMART-DS reactive-power parquets | `smart_ds_parquet_root` / `PIPELINE_SMART_DS_PARQUET_ROOT` | Point this config value or env var at the source parquets before Phase 6. | Automated. |
| Kvar-enriched profile folders from Phase 6 | `%PIPELINE_STATE%_4_profhp\daily_csvs`, `%PIPELINE_STATE%_6_profhp_dm\daily_csvs`, `%PIPELINE_STATE%_7_profhp_un\daily_csvs` | Manual staging required. Phase 7 expects these root folders and indexes CSVs under their `daily_csvs` subfolders. | Yes. Phase 5c/6 should write directly into the profile roots by variant. |
| `0_experimental_design\mixes_lhs.json` | Phase 7 fixed path | No copy required; Phase 7 reads the file directly. | Already automated, but the design file choice could be configurable. |
| `7_circuit_instantiation\aggregate_m2.csv`, `circuit_summary.csv`, `heating_assignment__FULL.csv` | `8_results_analysis` combined outputs | No copy required; Phase 8 reads from `7_circuit_instantiation`. | Already automated. |

## 4. Fire test quick-start

This is a 2-feeder NC smoke test. The prompt example used `PIPELINE_STATE=TX`,
but for an NC fire test the state must be `NC`. To run TX instead, change both
`PIPELINE_STATE` and `PIPELINE_SMART_DS_ROOT` to the TX/AUS source tree.

```bat
cd /d D:\github\dss-eulp-coupling

set PIPELINE_STATE=NC
set PIPELINE_SEASON=summer
set PIPELINE_SMART_DS_ROOT=D:\lvg\GSO\rural\base_timeseries\opendss
set PIPELINE_FEEDER_REGISTRY_PATH=feeder_registry.json
set PIPELINE_MAX_FEEDERS=2

:: Phase Pre: generate registry and load summary for two feeders.
python 0_download_smartds\stage_circuits_plain.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --registry feeder_registry.json --registry-only --max-feeders %PIPELINE_MAX_FEEDERS%
python 0_download_smartds\scan_feeders.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --max-feeders %PIPELINE_MAX_FEEDERS% --output parsed_loads.csv
python 0_download_smartds\generate_loads_pivot.py --input parsed_loads.csv --output parsed_loads_SUMMARY.csv

:: Phase 0: generate scenario mixes.
python 0_experimental_design\run_mix_generator.py

:: Phase 1: build state metadata.
pushd 1_data_provenance
set PYTHONPATH=src
python -m eulp_metadata.build --cluster pipeline_state --validate
popd

:: Phase 2: copy the two feeders and review SMART-DS parquet matches.
:: Before review, ensure 2_circuit_matching\parquet_data contains the SMART-DS source load parquets.
pushd 2_circuit_matching
python copy_circuits.py
python circuit_make_daily_list_sets.py
python review_parquet_matches.py
popd

:: Phase 3: tolerance matching.
copy /Y 2_circuit_matching\review_parquet_matches.csv 3_tolerance_matching\review_parquet_matches.csv
pushd 3_tolerance_matching
python match_smartds_parquets.py
popd

:: Phase 4: filter and select representative buildings.
pushd 4_quota_assignment
python clean_up_bldgs.py
python select_rep_family.py
popd

:: Phase 5a: download the selected EULP parquets.
copy /Y 4_quota_assignment\residential_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\
copy /Y 4_quota_assignment\commercial_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\
pushd 5a_eulp_downloads
python download_parquets_homes_redo.py
python download_parquets_commercial_redo.py
popd

:: Phase 5b: build baseline and variant daily parquet slices.
copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_commercial.csv 5b_profile_generation\
copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_residential.csv 5b_profile_generation\
pushd 5b_profile_generation
python scale_feeder_curves.py
python find_max_day_curve.py
popd

pushd 5d_scenario_controls
python plot_parquet_differences.py
python get_scenario_csv_controls.py
popd

pushd 5b_profile_generation
python find_max_day_curve_dm.py
python find_max_day_curve_uncontrolled.py
popd

:: Phase 5c: convert daily parquets to kW CSV loadshapes.
pushd 5c_csv_conversion
python parquet_to_csv.py
popd

:: Phase 6: add kvar CSVs.
:: Set PIPELINE_SMART_DS_PARQUET_ROOT or smart_ds_parquet_root to the original SMART-DS reactive-power parquets first.
copy /Y 5c_csv_conversion\folder_timestamps.pkl 6_kvar_preparation\
for /d %D in (5c_csv_conversion\%PIPELINE_STATE%_circuit_*_%PIPELINE_SEASON%) do xcopy /E /I /Y "%D" "6_kvar_preparation\%~nxD\"
pushd 6_kvar_preparation
python save_needed_sd_parquets.py
python rev_spec_kvar_kw_ratio.py
python generate_kvar_csvs.py
popd

:: Phase 7 expects profile roots. For a smoke test, stage the generated CSV folders.
mkdir %PIPELINE_STATE%_4_profhp\daily_csvs
mkdir %PIPELINE_STATE%_6_profhp_dm\daily_csvs
mkdir %PIPELINE_STATE%_7_profhp_un\daily_csvs
for /d %D in (6_kvar_preparation\%PIPELINE_STATE%_circuit_*_%PIPELINE_SEASON%) do xcopy /E /I /Y "%D" "%PIPELINE_STATE%_4_profhp\daily_csvs\%~nxD\"
for /d %D in (6_kvar_preparation\%PIPELINE_STATE%_circuit_*_%PIPELINE_SEASON%) do xcopy /E /I /Y "%D" "%PIPELINE_STATE%_6_profhp_dm\daily_csvs\%~nxD\"
for /d %D in (6_kvar_preparation\%PIPELINE_STATE%_circuit_*_%PIPELINE_SEASON%) do xcopy /E /I /Y "%D" "%PIPELINE_STATE%_7_profhp_un\daily_csvs\%~nxD\"

:: Phase 7: instantiate, run OpenDSS, check, and aggregate.
pushd 7_circuit_instantiation
python instantiate_circuits_and_runs_APPLYFILTER.py
python run_all_deploys_v2.py
python check_monitor_outputs.py
python aggregate_m1_m2_with_circuits.py
popd

:: Phase 8: combine and plot results.
pushd 8_results_analysis
python append_experiment_results.py
python append_xlrm_long_format.py
python figure_generation_methodsx_v3.py
popd
```

## Appendix A. Script naming audit

No files were renamed in this phase.

| Current name | Phase | Issue | Suggested action |
| --- | --- | --- | --- |
| `0_experimental_design/run_mix_generator.py` | 0 | Ambiguous: "mix" means scenario/DER design mix. | Keep for now; candidate rename `generate_scenario_mixes.py` after approval. |
| `1_data_provenance/copy_legacy_project.py` | 1 | One-time/bootstrap utility name is broad. | Keep as legacy utility or move under `scripts_legacy` after review. |
| `1_data_provenance/scripts_legacy/append_csvs_script.py` | 1 legacy | Ambiguous and duplicated by later append variants. | Keep only as legacy reference; do not use in simple workflow. |
| `1_data_provenance/scripts_legacy/append_csvs_script_V2.py` | 1 legacy | Version suffix and duplicate functionality. | Keep as legacy reference; prefer `src/eulp_metadata/build.py`. |
| `1_data_provenance/scripts_legacy/append_csvs_script_select_states.py` | 1 legacy | Ambiguous and overlaps with YAML-driven state filtering. | Keep as legacy reference; prefer `src/eulp_metadata/build.py`. |
| `1_data_provenance/scripts_legacy/download_residential_metadata.py` | 1 legacy | Legacy hardcoded download path/upgrades. | Keep as provenance reference only. |
| `1_data_provenance/scripts_legacy/download_residential_metadata_2.py` | 1 legacy | Numeric suffix and duplicated residential metadata download behavior. | Keep as provenance reference only. |
| `1_data_provenance/scripts_legacy/download_commercial_metadata.py` | 1 legacy | Legacy hardcoded download path/upgrades. | Keep as provenance reference only. |
| `1_data_provenance/scripts_legacy/download_commercial_metadata_19_20.py` | 1 legacy | Hardcoded upgrade suffix in name. | Keep as provenance reference only. |
| `1_data_provenance/scripts_legacy/folder_append_multiple.py` | 1 legacy | Ambiguous and too generic. | Keep as legacy reference or remove after confirming unused. |
| `1_data_provenance/scripts_legacy/slice_states_v2.py` | 1 legacy | Version suffix and duplicated state slicing. | Keep as legacy reference; prefer `pipeline_state` cluster. |
| `1_data_provenance/scripts_legacy/slice_states_v3.py` | 1 legacy | Version suffix and duplicated state slicing. | Keep as legacy reference; prefer `pipeline_state` cluster. |
| `2_circuit_matching/circuit_make_daily_list_sets.py` | 2 | Ambiguous and grammatically unclear; extracts yearly/daily loadshape names into pickles. | Candidate rename `extract_loadshape_name_sets.py`. |
| `2_circuit_matching/review_parquet_matches.py` | 2 | "Review" is vague; script computes monthly stats for matching. | Candidate rename `summarize_smartds_parquet_matches.py`. |
| `3_tolerance_matching/match_smartds_parquets_NC.py` | 3 | State in name even though code reads `pipeline_config.yaml`. | Keep behind wrapper for now; candidate rename `match_smartds_parquets_impl.py`. |
| `4_quota_assignment/clean_up_bldgs_NC.py` | 4 | State in name and "clean up" is vague. | Keep behind wrapper for now; candidate rename `filter_matched_buildings.py`. |
| `4_quota_assignment/select_rep_family_NC.py` | 4 | State in name; "family" is unclear for representative building selection. | Keep behind wrapper for now; candidate rename `select_representative_buildings.py`. |
| `5a_eulp_downloads/download_parquets_homes_NC.py` | 5a | State in name even though code is parameterized. | Keep as legacy implementation behind state-agnostic wrapper. |
| `5a_eulp_downloads/download_parquets_homes_NC_redo.py` | 5a | State in name plus "redo" suffix; overlaps with non-redo version. | Prefer wrapper `download_parquets_homes_redo.py`; candidate implementation rename after approval. |
| `5a_eulp_downloads/download_parquets_commercial_NC.py` | 5a | State in name even though code is parameterized. | Keep as legacy implementation behind state-agnostic wrapper. |
| `5a_eulp_downloads/download_parquets_commercial_NC_redo.py` | 5a | State in name plus "redo" suffix; overlaps with non-redo version. | Prefer wrapper `download_parquets_commercial_redo.py`; candidate implementation rename after approval. |
| `5b_profile_generation/scale_feeder_curves_NC.py` | 5b | State in name even though code is parameterized. | Keep behind wrapper for now; candidate rename `scale_feeder_curves_impl.py`. |
| `5b_profile_generation/find_max_day_curve_NC.py` | 5b | State in name even though code is parameterized. | Keep behind wrapper for now; candidate rename `find_max_day_curve_baseline.py`. |
| `5b_profile_generation/find_max_day_curve_NC_dm.py` | 5b variants | State in name even though code is parameterized. | Keep behind wrapper for now; candidate rename `find_max_day_curve_dm_impl.py`. |
| `5b_profile_generation/find_max_day_curve_MT_uncontrolled.py` | 5b variants | Wrong state in name for a parameterized uncontrolled script. | Keep behind wrapper for now; candidate rename `find_max_day_curve_uncontrolled_impl.py`. |
| `5d_scenario_controls/plot_parquet_differences.py` | 5d | Name says plot, but output drives scenario-control selection. | Candidate rename `summarize_profile_scenario_differences.py`. |
| `6_kvar_preparation/save_needed_sd_parquets.py` | 6 | Ambiguous abbreviation `sd`; output is a needed source parquet list. | Candidate rename `list_needed_source_parquets.py`. |
| `6_kvar_preparation/rev_spec_kvar_kw_ratio.py` | 6 | Ambiguous abbreviations and legacy name. | Candidate rename `derive_kvar_kw_ratios.py`. |
| `7_circuit_instantiation/instantiate_circuits_and_runs_APPLYFILTER.py` | 7 | Uppercase suffix and implementation detail in filename. | Candidate rename `instantiate_circuit_runs.py`. |
| `7_circuit_instantiation/run_all_deploys_v2.py` | 7 | Version suffix and "deploys" is vague for OpenDSS batch runs. | Candidate rename `run_prepared_circuits.py`. |
| `7_circuit_instantiation/power_flow_sim_daily_EV_STO_DG_deploy.py` | 7 | Long acronym-heavy name; "deploy" is unclear. | Keep until runner contract is stable; candidate rename `run_daily_power_flow.py`. |
| `8_results_analysis/append_xlrm_long_format.py` | 8 | `xlrm` is project shorthand and unclear to new users. | Candidate rename `combine_scenario_design_outputs.py`. |
| `8_results_analysis/figure_generation_methodsx_v3.py` | 8 | Version suffix and paper-specific naming. | Candidate rename `generate_methodsx_figures.py`. |
