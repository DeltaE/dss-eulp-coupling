# DSS-EULP Coupling Pipeline

Open-data coupling of SMART-DS synthetic distribution feeders with NREL End-Use
Load Profiles (EULP) for distribution system planning under uncertainty.

## Configuration

Edit `pipeline_config.yaml` at the repository root before running the pipeline:

```yaml
state: "NC"
season: "summer"
smart_ds_root: "../3_smartds"
parquet_data_root: "../parquet_data"
eulp_download_date: "20250330"
random_seed: 555
```

`PIPELINE_STATE` and `PIPELINE_SEASON` override the YAML values when set:

```powershell
$env:PIPELINE_STATE = "TX"
$env:PIPELINE_SEASON = "summer"
```

The primary runnable scripts are state-agnostic. Some original `*_NC.py` files
remain for provenance/compatibility, but they now read `pipeline_config.yaml`.

## Pipeline Phases

| Phase | Folder | Purpose |
| --- | --- | --- |
| pre | `0_download_smartds/` | Download SMART-DS feeders from OEDI and stage plain OpenDSS circuits |
| 0 | `0_experimental_design/` | Generate `mixes_lhs.json` for circuit instantiation |
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
- SMART-DS feeder data from OEDI, with `smart_ds_root` pointing to the extracted feeder root.
- OEDI / NREL EULP metadata and profile access. The download scripts use public OEDI S3 endpoints.
- Enough local disk for parquet and CSV profile data.
- Windows + OpenDSS installed for phase 7 (`comtypes` uses the OpenDSS COM interface).

## Run Sequence

Run these from the repository root unless the command uses `Push-Location`.

```powershell
# Optional pre-stage. Download SMART-DS and stage flat feeder folders.
python .\0_download_smartds\download_smartds.py `
  --regions GSO `
  --subregions rural `
  --scenarios base_timeseries `
  --only-opendss
python .\0_download_smartds\stage_circuits_plain.py `
  --smartds-root .\0_download_smartds\data_raw\smartds `
  --target .\ab_3b\circuits_plain_format `
  --registry .\feeder_registry.json

# 0. Experimental design
python .\0_experimental_design\run_mix_generator.py

# 1. State metadata from pipeline_config.yaml
Push-Location .\1_data_provenance
$env:PYTHONPATH = "src"
python -m eulp_metadata.build --cluster pipeline_state
Pop-Location

# 2. Circuit matching
Push-Location .\2_circuit_matching
python .\copy_circuits.py
python .\circuit_make_daily_list_sets.py
python .\review_parquet_matches.py
Pop-Location

# 3. Tolerance matching
Push-Location .\3_tolerance_matching
python .\match_smartds_parquets.py
Pop-Location

# 4. Quota assignment
Push-Location .\4_quota_assignment
python .\clean_up_bldgs.py
python .\select_rep_family.py
Pop-Location

# 5a. Download EULP parquets
Push-Location .\5a_eulp_downloads
python .\download_parquets_homes_redo.py
python .\download_parquets_commercial_redo.py
Pop-Location

# 5b. Baseline profiles
Push-Location .\5b_profile_generation
python .\scale_feeder_curves.py
python .\find_max_day_curve.py
Pop-Location

# 5d. Scenario controls for DM/uncontrolled variants
Push-Location .\5d_scenario_controls
python .\plot_parquet_differences.py
python .\get_scenario_csv_controls.py
Pop-Location

# 5b. DM and uncontrolled peak-day variants
Push-Location .\5b_profile_generation
python .\find_max_day_curve_dm.py
python .\find_max_day_curve_uncontrolled.py
Pop-Location

# 5c. CSV conversion
Push-Location .\5c_csv_conversion
python .\parquet_to_csv.py
Pop-Location

# 6. Kvar preparation
Push-Location .\6_kvar_preparation
python .\save_needed_sd_parquets.py
python .\rev_spec_kvar_kw_ratio.py
python .\generate_kvar_csvs.py
Pop-Location

# 7. Circuit instantiation, OpenDSS runs, QA, aggregation
Push-Location .\7_circuit_instantiation
python .\instantiate_circuits_and_runs_APPLYFILTER.py
python .\run_all_deploys_v2.py
python .\check_monitor_outputs.py
python .\aggregate_m1_m2_with_circuits.py
Pop-Location

# 8. Results analysis
Push-Location .\8_results_analysis
python .\append_experiment_results.py
python .\append_xlrm_long_format.py
python .\figure_generation_methodsx_v3.py
Pop-Location
```

## Key Handoffs

| Artifact | Producer | Consumer |
| --- | --- | --- |
| `commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv` | `1_data_provenance` cluster `pipeline_state` | `3_tolerance_matching/match_smartds_parquets.py` |
| `{STATE}_required_parquets_per_feeder_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5b_profile_generation/find_max_day_curve_dm.py` |
| `{STATE}_parquet_and_bldgs_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5c_csv_conversion/parquet_to_csv.py` |
| `profiles_use_bench/` | `7_circuit_instantiation/instantiate_circuits_and_runs_APPLYFILTER.py` | `7_circuit_instantiation/power_flow_sim_daily_EV_STO_DG_deploy.py` |
| `mixes_lhs.json` | `0_experimental_design/run_mix_generator.py` | `7_circuit_instantiation/instantiate_circuits_and_runs_APPLYFILTER.py` |

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
