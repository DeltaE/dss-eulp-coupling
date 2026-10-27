# TX Fire Test — Execution Cheat Sheet

Drop both files in repo root: `D:\github\dss-eulp-coupling\`
- `verify_fire_test.py` — verification runner
- `FIRE_TEST_CHEATSHEET.md` — this file (optional, for reference)

Open **Anaconda Prompt**, then copy-paste block by block.

---

## Setup (once per session)

```bat
cd /d D:\github\dss-eulp-coupling
set PIPELINE_STATE=TX
set PIPELINE_SEASON=summer
set PIPELINE_SMART_DS_ROOT=D:\lvg\GSO\rural\base_timeseries\opendss
set PIPELINE_MAX_FEEDERS=2
set PYTHONIOENCODING=utf-8
```

---

## Phase Pre (skip if dry-run artifacts still on disk)

```bat
python 0_download_smartds\stage_circuits_plain.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --registry feeder_registry.json --registry-only --max-feeders 2
python 0_download_smartds\scan_feeders.py --smartds-root "%PIPELINE_SMART_DS_ROOT%" --max-feeders 2 --output parsed_loads.csv
python 0_download_smartds\generate_loads_pivot.py --input parsed_loads.csv --output parsed_loads_SUMMARY.csv
python verify_fire_test.py --phase pre
```

## Phase 1

```bat
pushd 1_data_provenance
set PYTHONPATH=src
python -m eulp_metadata.build --cluster pipeline_state --validate
popd
python verify_fire_test.py --phase 1
```

## Phase 2

```bat
pushd 2_circuit_matching
python copy_circuits.py
python circuit_make_daily_list_sets.py
python review_parquet_matches.py
popd
python verify_fire_test.py --phase 2
```

## Phase 3

```bat
copy /Y 2_circuit_matching\review_parquet_matches.csv 3_tolerance_matching\review_parquet_matches.csv
pushd 3_tolerance_matching
python match_smartds_parquets.py
popd
python verify_fire_test.py --phase 3
```

## Phase 4

```bat
pushd 4_quota_assignment
python clean_up_bldgs.py
python select_rep_family.py
popd
python verify_fire_test.py --phase 4
```

## Phase 5a (downloads — may take a while)

```bat
copy /Y 4_quota_assignment\residential_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\
copy /Y 4_quota_assignment\commercial_data_SELECT_STATES_FILTERED_%PIPELINE_STATE%.csv 5a_eulp_downloads\
pushd 5a_eulp_downloads
python download_parquets_homes_redo.py
python download_parquets_commercial_redo.py
popd
python verify_fire_test.py --phase 5a
```

## Phase 5b

```bat
copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_commercial.csv 5b_profile_generation\
copy /Y 4_quota_assignment\%PIPELINE_STATE%_final_residential.csv 5b_profile_generation\
pushd 5b_profile_generation
python scale_feeder_curves.py
python find_max_day_curve.py
popd
python verify_fire_test.py --phase 5b
```

## Phase 5d

```bat
pushd 5d_scenario_controls
python plot_parquet_differences.py
python get_scenario_csv_controls.py
popd
python verify_fire_test.py --phase 5d
```

## Phase 5b variants (after 5d)

```bat
pushd 5b_profile_generation
python find_max_day_curve_dm.py
python find_max_day_curve_uncontrolled.py
popd
```

## Phase 5c — KEY MILESTONE

```bat
pushd 5c_csv_conversion
python parquet_to_csv.py
popd
python verify_fire_test.py --phase 5c
```

If you see `FIRE TEST PASSED`, you're done. Commit and push.

---

## Full verify (after everything, or to check current state)

```bat
python verify_fire_test.py --all
```
