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

`pre`, `1`, `2`, `3`, `4`, `5a`, `5b`, `5d`, `5b_variants`, `5c`, `5c_variants`, `6`, `6_variants`, `mix_days`, `7a`, `7b`, `7c`, `8`.

`configs/phases.yaml` defines the steps of each phase. `run_case.py` sets `PIPELINE_WORK_ROOT` to `<runs_root>/<case>/<season>/workspace/`, written `<ws>` below. `runs_root` comes from `configs/local.yaml` and is `runs` by default. Every phase reads and writes under `<ws>`. Before anything runs, `--all` checks the workspace of every requested season and refuses to start when any exists. Delete those folders to rerun the case-seasons. `--phase <id>` reruns one phase in the existing workspace. `--dry-run` prints the resolved variables and every command, and writes nothing.

`--all` does not run `0_experimental_design`. The mixes file is an input. Phase 7a copies the mixes file that `mixes_file` in `configs/defaults.yaml` names, the tracked `0_experimental_design/mixes_fixed.yaml`, into the workspace. https://github.com/DeltaE/j-uncertainty-grid-modernisation writes the mixes file of a designed experiment.

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

`run_case.py` copies `review_parquet_matches.csv` from Phase 2 into `<ws>/3_tolerance_matching/`. `phase3_match.py` then runs `match_smartds_parquets_impl.py`. It matches each SMART-DS loadshape to the donor's buildings by monthly peaks, in tolerance steps of 5 % up to 50 % (commercial) or 95 % (residential). A loadshape that matches no building within the largest step takes the buildings of the next 5 % step that matches; the script prints a `[phase3]` line and the `Tolerance` column records the step reached.

### Phase 4: Quota assignment (4_quota_assignment)

`phase4_cleanup.py` runs `clean_up_bldgs_impl.py`. `phase4_select.py` runs `select_representatives_impl.py`. Phase 4 writes `<STATE>_final_residential.csv` and `<STATE>_final_commercial.csv`.

### Phase 5a: EULP downloads (5a_eulp_downloads)

`run_case.py` copies the two Phase 4 final CSVs into `<ws>/5a_eulp_downloads/`. `phase5a_download_residential.py` and `phase5a_download_commercial.py` then download the EULP parquets from OEDI (open access) to the parquet data root.

### Phases 5b, 5d and 5b_variants: profile generation

- `5b` (`5b_profile_generation`): `phase5b_scale.py` runs `scale_feeder_curves_impl.py`. It reads the two Phase 4 final CSVs from `<ws>/4_quota_assignment/`. `phase5b_peak.py` runs `find_max_day_curve_impl.py --scenario baseline`. Together they build the baseline profiles.
- `5d` (`5d_scenario_controls`): `combine_scenarios.py` writes `<ws>/5d_scenario_controls/combine_scenarios/combined_scenarios.csv`. `get_scenario_csv_controls.py` then reads it and selects the controls for the dm and uncontrolled variants. dm is a heat pump that keeps a fuel backup: ResStock upgrade 4, ComStock upgrade 2 or 9. A home whose `in.heating_fuel` in the Phase 1 residential metadata is `Electricity` takes ResStock upgrade 1 as its dm profile, because upgrade 4 does not apply to it. uncontrolled (un) is a heat pump with electric backup: ResStock upgrade 1, ComStock upgrade 1 or 8. The upgrade names are in the OEDI lookup files https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/resstock_tmy3_release_2/upgrades_lookup.json and https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/upgrades_lookup.json.
- `5b_variants` (`5b_profile_generation`): `phase5b_variants_dm.py` and `phase5b_variants_uncontrolled.py` run `find_max_day_curve_impl.py` with `--scenario dm` and `--scenario uncontrolled`. They build the DM and uncontrolled profiles.

### Phases 5c and 5c_variants: CSV conversion (5c_csv_conversion)

`5c` runs `parquet_to_csv.py` for the baseline profiles. `5c_variants` runs it with `--scenario dm` and then with `--scenario uncontrolled`.

### Phases 6 and 6_variants: reactive power preparation (6_kvar_preparation)

- `6` runs `save_needed_sd_parquets.py`, `compute_kvar_kw_ratios.py` and `generate_kvar_csvs.py`.
- `6_variants` runs `compute_kvar_kw_ratios.py` and `generate_kvar_csvs.py` with `--scenario dm`, and then both again with `--scenario uncontrolled`.

Both phases write `_kvar_` CSVs beside the `_kw_` CSVs.

### Phase mix_days and the peak-day rules

`peak_day_rule` in `pipeline_config.yaml` sets the calendar day that each mixed or stress circuit is simulated on. Baseline circuits run on each feeder's baseline seasonal peak day under both values.

- `per_circuit`, the default: all heating groups of a circuit run on one day, the seasonal peak day of the circuit's building load under its mix. `mix_days.py` finds that day and writes `<ws>/mix_days/<STATE>_circuit_days.csv`, `<STATE>_circuit_labels.csv` and `<STATE>_circuit_weights.csv`. For each mix that is not 100 % baseline, it reruns the day-dependent steps of 5c, 5c_variants, 6, 6_variants and 7a into `<ws>/mix_days/<mix>/`. Phases 7b and 7c then read the circuit's day and its profiles from there.
- `per_group`: each heating group (baseline, dm, uncontrolled) runs on its own seasonal peak day. `mix_days.py` prints one line and writes nothing.

To switch, set `peak_day_rule` to `per_circuit` or `per_group` before the run. `run_case.py` stops on any other value. PV follows the day the circuit runs on. After `mix_days`, `run_case.py` runs the 5b and 5c checks of `verify_phase.py` for baseline, dm and uncontrolled in each `<ws>/mix_days/<mix>/` subtree, under `per_circuit` only.

### Phases 7a, 7b and 7c: circuit instantiation and simulation (7_circuit_instantiation)

- `7a` runs `bridge_phase5c_to_phase7.py` from the repository root. It builds the profile roots `<STATE>_4_profhp`, `<STATE>_6_profhp_dm` and `<STATE>_7_profhp_un` in `<ws>/7_circuit_instantiation/` from the Phase 5c CSVs. It copies the file in `PIPELINE_MIXES_FILE` (`mixes_file` in `configs/defaults.yaml`, the tracked `0_experimental_design/mixes_fixed.yaml`) byte for byte to `<ws>/7_circuit_instantiation/mixes.yaml`, keeping the extension of the mixes file (`.yaml`, `.yml` or `.json`), and exits 1 when that file is missing. It prints the mix names and the expected circuit folders from that file. It checks the feeder registry at `<ws>/feeder_registry.json`.
- `7b` runs `instantiate_circuits.py`. It reads `<ws>/7_circuit_instantiation/mixes.yaml` (`mixes.yml` or `mixes.json` for a mixes file with that extension) with `pipeline_utils.load_mixes`. For each feeder and mix, it prepares a circuit folder, assigns EV, PV, storage and heat pump profiles, and copies and patches the runner `power_flow_sim_daily_EV_STO_DG_deploy.py` into the folder. It writes `heating_assignment__SUMMARY.csv`, `heating_assignment__FULL.csv` and `heating_assignment__FULL.json` to `<ws>/7_circuit_instantiation/`.
  - The heating split counts the unit that `heating_label_unit` in `pipeline_config.yaml` names: `building` (the default), each yearly loadshape of the feeder gets one group, with exact counts over loadshapes; `customer`, the counts are over load names and a shared loadshape keeps the group of the last load dealt. Phase `mix_days` uses the same setting.
  - It classes each load as residential (every loadshape starts `res_`), commercial (every one starts `com_`) or unclassified with `heating_split.load_segment`, prints the counts per circuit, and draws the EV hosts among the residential loads: `ev_perc` of the mix is the share of homes.
  - A loadshape without a kW or kvar CSV stops the run with `[FAIL]`, the loadshape and the circuit. `<circuit>/missing_files_report.json` is still written and is empty.
  - It splits each customer's building curve over the customer's Load lines with `heating_split.line_shares`: each line takes as kW its share of the customer's SMART-DS kW and as kvar its share of the customer's SMART-DS kvar, read from the feeder's SMART-DS `Loads.dss` (for example https://oedi-data-lake.s3.amazonaws.com/SMART-DS/v1.0/2018/GSO/urban-suburban/scenarios/base_timeseries/opendss/uhs13_1247/uhs13_1247--udt4819/Loads.dss). A customer on two 120 V legs (`<customer>_1`, `<customer>_2`) draws its building once, half on each leg. A customer whose kvar sum is 0 takes its kW shares; a customer whose kW sum is 0 stops the run with `[FAIL]`. `Loads_original.dss` in the circuit folder keeps the SMART-DS lines.
- `7c` runs `run_circuits.py --root <ws>/7_circuit_instantiation`. It runs the patched runner in each circuit folder and logs to `<ws>/7_circuit_instantiation/run_log.txt`. No phase runs the runner in the repository folder.
- In each circuit, the runner builds one car per EV host from the source `ev_cars` names (README, "EV cars") and writes `<circuit>/EVControl/ev_cars.csv` and `ev_places.csv`. Under `evwatts_sessions` and `session_rows` it reads the EV WATTS extract in `PIPELINE_EVWATTS_EXTRACT_DIR` and stops when it is missing; under `evwatts_sessions` with `ev_work_share_case` above `low` it also reads the office extract `evwatts_office_l2_weekday.csv` there and stops when it is missing; under `nhts_days` and `session_rows` it reads `7_circuit_instantiation/data_ev_cars/<STATE>_nhts2017_vehicle_days.csv` in the repository. The work share of each group's charging cars charges at a commercial load of the circuit (README, "EV cars").
- In each circuit, the runner shapes the controlled EVs with the rule `ev_control` names (README, "EV control"). Under `valley_fill_feeder`, `valley_fill_transformer` and `water_fill_feeder` it first solves the circuit without EVs in `<circuit>/EVControl/base_solve/`, places the controlled cars in order of plug-in time on a forecast of each curve, then solves the circuit with EVs in `ModifiedCircuitData/` as before. Under `offpeak_start` it spreads the schedule times around the start of the cheap period, starts each car at the later of its schedule time and its plug-in, and reads `7_circuit_instantiation/data_tariffs/<STATE>_urdb_rate.json` in the repository and stops when it is missing. It writes `ev_control_cars.csv` and, under the valley rules, `ev_control_curves.csv` to `<circuit>/EVControl/` (see `docs/outputs.md`). Phase 8 reads only `ModifiedCircuitData/`.
- `fetch_tou_rates.py` is a maintainer step outside `--all`. It saves one URDB time-of-use rate per donor state to `7_circuit_instantiation/data_tariffs/`. It reads the OpenEI API key from the file that `openei_api_key_file` in `configs/local.yaml` names, and never prints or writes the key.
- `build_nhts_extract.py` and `build_evwatts_extract.py` are maintainer steps outside `--all`. The first writes the tracked 2017 NHTS weekday vehicle-day extracts of NC and TX and `nhts2017_extract.yaml` to `7_circuit_instantiation/data_ev_cars/`, from the folder `nhts2017_csv_dir` names. A vehicle-day with a driver trip faster than `nhts_max_trip_speed_mph` of `ev_inputs.yaml` is class iv, which no draw pool holds. The second writes `evwatts_residential_l2_weekday.csv` and `evwatts_extract.yaml` to the folder `evwatts_extract_dir` names, outside the repository, from the EV WATTS tables in `evwatts_raw_dir`; run a second time with `--venue office`, it writes `evwatts_office_l2_weekday.csv` and `evwatts_office_extract.yaml` there, the Business Office sessions the work cars draw from.

### Phase 8: results analysis

1. `aggregate_m1_m2_with_circuits.py` runs in `8_results_analysis/`. It writes `aggregate_m1.csv`, `aggregate_m2.csv` and `circuit_summary.csv` to `<ws>/7_circuit_instantiation/`.
2. `append_experiment_results.py` runs in `8_results_analysis/`. It reads `aggregate_m2.csv`, `circuit_summary.csv` and `heating_assignment__FULL.csv` from `<ws>/7_circuit_instantiation/`. It tags every row with the season, and with `design` set to the donor state. It writes `aggregate_m2_combined.csv`, `circuit_summary_combined.csv` and `heating_assignment__FULL_combined.csv` to `<ws>/8_results_analysis/`. It also writes `load_voltage_summary.csv` there, one row per circuit folder from its `load_voltage_loads.csv` (see `docs/outputs.md`). It exits with an error when an input file is missing.

Phase 8 covers one case-season. `gather_m2_cases.py` stacks `aggregate_m2_combined.csv` from all eight case-seasons into `m2_all_cases_all_seasons.csv` in the runs root (`runs_root` in `configs/local.yaml`, `runs/` by default). `gather_m2_cases.py` reads the workspaces under the runs root. `validate_2x2.py` checks that file. It exits 1 when it finds fewer than 12 `circuit_folder` values, before it writes anything. Otherwise it writes `peaks_per_combo.csv` to the runs root. `--all` runs neither script.

## 3.3 Configuration Highlights

- **Donor states:** NC and TX (`configs/donor_registry.yaml`).
- **Topologies:** `NC_GSO_urban_uhs13_1247` and `TX_AUS_urban_p2uhs12_1247` (`configs/topology_registry.yaml`).
- **Seasons:** summer and winter (`configs/defaults.yaml`).
- **Circuit filtering:** Phase 7b skips the circuits listed in `skip_circuits` in `pipeline_config.yaml`. The list is empty, so `--all` skips no circuit.
- **Scenario mixes:** `--all` uses the three fixed mixes in `0_experimental_design/mixes_fixed.yaml`, the file that `mixes_file` in `configs/defaults.yaml` names. A designed experiment names its own mixes file there; https://github.com/DeltaE/j-uncertainty-grid-modernisation writes it.

| Mix | EV (share of homes) | Storage (share of homes and of commercial loads) | PV (share of homes and of commercial loads) | Heat pump shares (baseline / DM / uncontrolled) |
| --- | --- | --- | --- | --- |
| `baseline` | 10% | 5% | 5% | 1.0 / 0.0 / 0.0 |
| `mixed` | 20% | 10% | 10% | 0.5 / 0.3 / 0.2 |
| `stress` | 30% | 15% | 15% | 0.2 / 0.2 / 0.6 |

- **EV cars:** `ev_cars` in `pipeline_config.yaml` (default `evwatts_sessions`; also `nhts_days`, `session_rows`), `ev_home_window` (default `true`), `ev_day` (default `typical`; also `stress`, the value set of `ev_inputs.yaml`) and `ev_work_share_case` (default `moderate`; also `low`, `high`, the share of the charging cars that charge at a workplace). Main runs use the defaults. See README, "EV cars".
- **EV control:** `ev_control` in `pipeline_config.yaml` (default `valley_fill_feeder`; also `uncontrolled`, `valley_fill_transformer`, `offpeak_start`, `water_fill_feeder`) and `ev_valley_base` (default `buildings_only`; also `after_pv`). Main runs use the defaults. See README, "EV control".
- **PV and storage:** Phase 7b draws the PV and storage hosts per segment (homes and commercial loads) with the mix shares `pv_res_perc`, `pv_com_perc`, `storage_res_perc` and `storage_com_perc`, the `der_sizing` switches and `storage_hosts` (default `with_pv`), and writes them per segment and as `pv_targets` and `storage_targets`. The runner `power_flow_sim_daily_EV_STO_DG_deploy.py` sizes them (`pv_rule_residential` and `pv_rule_commercial`, default `roof_and_use`; `sizing_case`, default `moderate`; `roof_area_source`, default `floor_stories`; `coverage_rule_commercial`, default `lbnl`) and controls storage (`storage_rule`, default `schedule`; `storage_view`, default `feeder`; `storage_order`, default `after_cars`; `storage_measure`, default `all_placed`; `storage_layer`, default `add_kw`). Main runs use the defaults. See README, "PV and storage".

```{admonition} Tip: Storage Controller Defaults (example)
:class: tip
- PV: the lesser of the roof cap and the annual use cap (moderate entries)
- Storage: 1.0 x PV kW (0.5 above 100 kW commercial), 2 h
- Rule: `schedule`, each host's start chosen on a grid from the reserve to full (`schedule_start: best`)
- Start and reserve: 20%
```

## 3.4 Running with `run_case.py`

This section describes what `python run_case.py --case <case> --all` runs. `configs/phases.yaml` defines every step.

### Setup

Copy `configs/local.yaml.example` to `configs/local.yaml`. Set the machine paths: `smart_ds_base` for the SMART-DS data root and `eulp_metadata_root` for the EULP metadata data root. Both are required. Under the default `ev_cars: evwatts_sessions` and under `session_rows`, also set `evwatts_extract_dir` (README, "Prerequisites for a cold clone").

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
| `PIPELINE_EVWATTS_EXTRACT_DIR` | Folder of the EV WATTS extract, from `evwatts_extract_dir` in `configs/local.yaml`; set only when that key is present. The Phase 7 deploy reads it under `ev_cars` `evwatts_sessions` and `session_rows`. |

`pipeline_config.yaml` holds the method parameters, one top-level key each:

- `random_seed` seeds representative building selection in Phase 4.
- `skip_circuits` lists numeric `circuit_id` values that Phase 7 skips.
- `quota` sets the Phase 4 quota rules.
- `eulp_release` names the ResStock and ComStock releases that Phase 5a downloads.
- `der_sizing` sets the PV and storage hosts (Phase 7b), their sizes, the storage control (with `schedule_start`, default `best`: under `schedule` each host's starting energy is the one of a grid that leaves the lowest forecast maximum) and the battery standby losses (`storage_standby_case`, default `moderate`; `storage_standby_element`, default `load`, a constant-power Load beside each battery, or `idling`, the battery's `%IdlingkW`) (Phase 7 deploy) (README, "PV and storage").
- `peak_day_rule` sets the day each mixed or stress circuit runs on (section 3.2, "Phase mix_days and the peak-day rules"; README, "Peak-day rules").
- `heating_label_unit` sets whether the heating split counts buildings or customers (section 3.2, Phase 7b; README, "Heating labels and EV hosts").
- `voltage_band` sets the band of the load voltage summaries.
- `ev_control` sets how the Phase 7 deploy shapes controlled EV charging (section 3.3; README, "EV control").
- `ev_valley_base` sets what the no-EV solve behind the valley rules holds (section 3.3; README, "EV control").
- `ev_cars` sets where each EV car comes from (section 3.3; README, "EV cars").
- `ev_home_window` keeps controlled charging inside the time the car is plugged in at home (section 3.3; README, "EV cars").
- `ev_day` picks the typical or stress value set of `ev_inputs.yaml` (section 3.3; README, "EV cars").
- `ev_work_share_case` picks the share of the charging cars that charge at a workplace, a commercial load of the circuit (section 3.3; README, "EV cars").

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
| 7c | `run_circuits.py` | OpenDSS monitor CSVs and the load voltage files (`Monitors_LoadVoltage.dss`, `load_voltages.parquet`, `load_voltage_steps.csv`, `load_voltage_loads.csv`) in each circuit folder |
| 8 | `aggregate_m1_m2_with_circuits.py`, `append_experiment_results.py` | `aggregate_m1.csv`, `aggregate_m2.csv`, `circuit_summary.csv` in `7_circuit_instantiation/`; combined CSVs and `load_voltage_summary.csv` in `8_results_analysis/` |

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
| `phase5b_peak.py` | `find_max_day_curve_impl.py --scenario baseline` |
| `phase5b_variants_dm.py` | `find_max_day_curve_impl.py --scenario dm` |
| `phase5b_variants_uncontrolled.py` | `find_max_day_curve_impl.py --scenario uncontrolled` |

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
- Phase 7a copies `0_experimental_design/mixes_fixed.yaml` to `7_circuit_instantiation/mixes.yaml` in the workspace. Phase 7b reads that copy.
- Phase 7 reads the profile roots `<STATE>_4_profhp`, `<STATE>_6_profhp_dm` and `<STATE>_7_profhp_un`. It indexes the CSVs under their `daily_csvs/` subfolders. Phase 7a builds these roots from the Phase 5c CSVs.
- Phase 8 reads the Phase 7 outputs from `7_circuit_instantiation/`.
