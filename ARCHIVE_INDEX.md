# Archive index

This branch stores files removed from `main` before v1.0.0 for retrieval; it is never merged and is not meant to run.

The branch starts at `102bc61`. One commit restores every tracked file deleted from `main` between `1987d04` and `102bc61` and absent at `102bc61`, each at its last version before the deletion. Renames are excluded.

## Files restored by this branch (98)

| Path | Removed by | Date | Subject |
| --- | --- | --- | --- |
| `0_download_smartds/parsed_loads.csv` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `0_download_smartds/parsed_loads.twbx` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `0_download_smartds/parsed_loads_PIVOT.xlsx` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `1_data_provenance/copy_legacy_project.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/append_csvs_script.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/append_csvs_script_select_states.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/append_csvs_script_V2.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/download_commercial_metadata.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/download_commercial_metadata_19_20.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/download_residential_metadata.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/download_residential_metadata_2.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/folder_append_multiple.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/pds_database_address.txt` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/preview_csvs.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/slice_states_v2.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/scripts_legacy/slice_states_v3.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_data_provenance/seed_validation_baselines.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `1_experimental_design/run_mix_generator.py` | `1cefb39` | 2026-03-17 | Remove experimental design (belongs in DMDU repo, not coupling pipeline) |
| `3_tolerance_matching/compare_outputs.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `3_tolerance_matching/match_smartds_parquets_NC_GOLDEN.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `3_tolerance_matching/review_parquet_matches.csv` | `89702ff` | 2026-06-11 | fix(instantiation): derive per-topology parquet root, untrack generated output |
| `3_tolerance_matching/test_tolerance_match.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `4_quota_assignment/clean_up_bldgs.py` | `a73f19d` | 2026-09-18 | refactor: align script names with phases.yaml; fix chain description in docs |
| `4_quota_assignment/select_rep_family_NC.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `5a_eulp_downloads/download_parquets_commercial.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `5a_eulp_downloads/download_parquets_commercial_NC.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `5a_eulp_downloads/download_parquets_homes.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `5a_eulp_downloads/download_parquets_homes_NC.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `5a_eulp_downloads/pds_database_address.txt` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `5a_eulp_downloads/TX_final_commercial.csv` | `89702ff` | 2026-06-11 | fix(instantiation): derive per-topology parquet root, untrack generated output |
| `5a_eulp_downloads/TX_final_residential.csv` | `89702ff` | 2026-06-11 | fix(instantiation): derive per-topology parquet root, untrack generated output |
| `5b_profile_generation/old_files/find_max_day_curve_MT_uncontrolled.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `5b_profile_generation/old_files/find_max_day_curve_NC.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `5b_profile_generation/old_files/find_max_day_curve_NC_dm.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `7_circuit_instantiation/check_monitor_outputs.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `add_shared_placeholders.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/uhs0_1247_circuit_1_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_summer/uhs0_1247_circuit_2_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/uhs0_1247_circuit_1_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/mi_8_winter/uhs0_1247_circuit_2_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/uhs0_1247_circuit_1_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_summer/uhs0_1247_circuit_2_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/uhs0_1247_circuit_1_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/vt_8_winter/uhs0_1247_circuit_2_2/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/uhs0_1247_circuit_3_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_summer/uhs0_1247_circuit_3_1/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/profiles_use_bench/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/uhs0_1247_circuit_1_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/uhs0_1247_circuit_2_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/uhs0_1247_circuit_3_0/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive/wa_8_winter/uhs0_1247_circuit_3_1/data_ev/.gitkeep` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `archive_multistate.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `CHECK_PATHS.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `configs/cases/NC_GSO_rural__NC.yaml` | `6515370` | 2026-06-11 | feat: wire real NC/TX urban feeders into 2x2 case matrix |
| `configs/cases/NC_GSO_rural__TX.yaml` | `6515370` | 2026-06-11 | feat: wire real NC/TX urban feeders into 2x2 case matrix |
| `configs/cases/TX__NC.yaml` | `6515370` | 2026-06-11 | feat: wire real NC/TX urban feeders into 2x2 case matrix |
| `configs/cases/TX__TX.yaml` | `6515370` | 2026-06-11 | feat: wire real NC/TX urban feeders into 2x2 case matrix |
| `CORRECTNESS_AUDIT.md` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `diagnose_tx_columns.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `dump_eulp_metadata.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `dump_workflow_and_sources.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `EXTRACTION_LOG.txt` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `FIRE_TEST_CHEATSHEET.md` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `m2_all_cases.csv` | `812408e` | 2026-06-16 | Fix verify cwd resolution; add validate_2x2.py; drop old single-run CSV |
| `m2_all_cases_all_seasons.csv` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `parsed_loads.csv` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `parsed_loads_SUMMARY.csv` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `parsed_loads_SUMMARY_TEST.csv` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `patch_season.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `scan_paths.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `scan_topology_universe.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `structure.txt` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `topology_inventory_AUS.csv` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `topology_inventory_GSO.csv` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `verify_phase6_outputs.py` | `42fdeff` | 2026-10-12 | chore: remove unreferenced scratch and superseded files |
| `verify_phase7_readiness.py` | `d64804f` | 2026-09-18 | chore: remove files not executed by phases.yaml |
| `WORKFLOW.md` | `0efcd48` | 2026-10-15 | docs: carry run_case.py facts from WORKFLOW.md into docs/workflow.md |

## Files that job 4 removes from main (7)

This branch holds these files because it starts at `102bc61`. The commits are on the branch `fix/dead-code`.

| Path | Removed by | Subject |
| --- | --- | --- |
| `1_data_provenance/docs/copy_manifest.json` | `ddd8413` | job4: Phase 1 trim |
| `1_data_provenance/docs/local_source_inventory.md` | `ddd8413` | job4: Phase 1 trim |
| `5b_profile_generation/TX_final_commercial.csv` | `cc160c8` | job4: Remove tracked leftovers |
| `5b_profile_generation/TX_final_residential.csv` | `cc160c8` | job4: Remove tracked leftovers |
| `2_circuit_matching/README.txt` | `cc160c8` | job4: Remove tracked leftovers |
| `5a_eulp_downloads/README.txt` | `cc160c8` | job4: Remove tracked leftovers |
| `6_kvar_preparation/README.txt` | `cc160c8` | job4: Remove tracked leftovers |
