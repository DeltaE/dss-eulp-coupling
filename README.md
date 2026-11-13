# DSS-EULP Coupling Pipeline

Open-data coupling of SMART-DS synthetic distribution feeders with NREL End-Use
Load Profiles (EULP) for distribution system planning under uncertainty.

## Configuration

Each value has one owner:

- `configs/local.yaml` holds the machine paths: `smart_ds_base`, `eulp_metadata_root`, `runs_root` and `evwatts_extract_dir` (see "EV cars"), `openei_api_key_file` for the tariff fetch only (see "EV control"), and `nhts2017_csv_dir` and `evwatts_raw_dir` for the two extract scripts only. Copy it from `configs/local.yaml.example`.
- A case file in `configs/cases/` names a topology, a donor and `execution.max_feeders`. `configs/topology_registry.yaml` and `configs/donor_registry.yaml` hold the values of each topology and donor, such as the feeder folder, the donor state and `eulp_download_date`.
- `configs/defaults.yaml` holds the seasons, the phase order and `mixes_file`.
- `configs/growth.yaml` holds the load growth settings: `growth_years` (default 0, growth off), the growth rates, the infill share, the companion businesses, the named loads and the planning limits (see "Load growth over planning years").
- `pipeline_config.yaml` holds the method parameters: `random_seed`, `skip_circuits`, `quota`, `eulp_release` (the ResStock and ComStock release names with their OEDI years `residential_year` and `commercial_year`, see "Settings from a caller"), `der_sizing` (PV and storage hosts, sizes and control, see "PV and storage"), `peak_day_rule` (default `per_circuit`; `per_group` and `given` remain available, see "Peak-day rules"), `heating_label_unit` (default `building`; `customer` remains available, see "Heating labels and EV hosts"), `voltage_band` (the band for the load voltage summaries), `ev_cars`, `ev_home_window`, `ev_day` and `ev_work_share_case` (defaults `evwatts_sessions`, `true`, `typical` and `moderate`, see "EV cars"), and `ev_control` and `ev_valley_base` (defaults `valley_fill_feeder` and `buildings_only`, see "EV control").

`run_case.py` resolves these files and passes the run values to each script as `PIPELINE_*` environment variables. `docs/workflow.md`, section 3.4, lists them. A script that reads a run value whose variable is not set exits 1 and names the variable. Run the pipeline through `run_case.py`.

The primary runnable scripts are state-agnostic.

## Pipeline Phases

| Phase | Folder | Purpose |
| --- | --- | --- |
| pre | `0_download_smartds/` | Download SMART-DS feeders from OEDI and stage plain OpenDSS circuits |
| 0 | `0_experimental_design/` | Hold the fixed mixes (`mixes_fixed.yaml`). The mixes file is an input; https://github.com/DeltaE/j-uncertainty-grid-modernisation writes the mixes file of a designed experiment |
| 1 | `1_data_provenance/` | Build state-specific EULP metadata CSVs |
| 2 | `2_circuit_matching/` | Flatten SMART-DS feeders and review parquet matches |
| 3 | `3_tolerance_matching/` | Match feeder peaks to EULP buildings. A loadshape that matches no building within the largest tolerance takes the buildings of the next 5 % step that matches |
| 4 | `4_quota_assignment/` | Filter, stratify, and select representative buildings |
| growth | `growth_plan.py` | Plan the load growth of the planning year from `configs/growth.yaml`. Writes nothing with `growth_years: 0` |
| 5a | `5a_eulp_downloads/` | Download EULP parquet profiles from OEDI |
| 5b | `5b_profile_generation/` | Build baseline, dm and uncontrolled peak-day parquet slices |
| 5c | `5c_csv_conversion/` | Convert daily parquet slices to OpenDSS CSV loadshapes |
| 5d | `5d_scenario_controls/` | Pick each building's dm and uncontrolled (un) profile. dm is a heat pump that keeps a fuel backup: ResStock upgrade 4 (upgrade 1 for a home heated by electricity, to which upgrade 4 does not apply), ComStock upgrade 2 or 9. un is a heat pump with electric backup: ResStock upgrade 1, ComStock upgrade 1 or 8 |
| 6 | `6_kvar_preparation/` | Prepare kvar ratios and kvar CSV loadshapes |
| 7 | `7_circuit_instantiation/` | Instantiate circuits and run OpenDSS batches |
| 8 | `8_results_analysis/` | Aggregate monitor outputs, append experiment outputs and generate analysis figures |

The upgrade names are in the OEDI lookup files of each release: https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/resstock_tmy3_release_2/upgrades_lookup.json and https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2024/comstock_amy2018_release_1/upgrades_lookup.json. The code keys stay `dm`, `uncontrolled` and `demand_management`.

## Prerequisites

- Python 3.11 with `pip install -r requirements.txt`.
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

The EV cars of the default `ev_cars: evwatts_sessions`, and of `session_rows`, need the EV WATTS public database (https://doi.org/10.15483/1970735). Create a free account at https://livewire.energy.gov/ds/evwatts/evwatts.public and download its session and evse tables (`evwatts.public.session.csv`, `evwatts.public.evse.csv`). Set `evwatts_raw_dir` to their folder and `evwatts_extract_dir` to a folder outside the repository, then run `python 7_circuit_instantiation/build_evwatts_extract.py` from the repository root, once as is for the residential extract and a second time with `--venue office` for the Business Office extract that the work cars draw from. The EV WATTS data stays outside the repository. The 2017 NHTS extract in `7_circuit_instantiation/data_ev_cars/` is tracked; `python 7_circuit_instantiation/build_nhts_extract.py` rebuilds it from https://nhts.ornl.gov/assets/2016/download/Csv.zip, unpacked into the folder that `nhts2017_csv_dir` names. A run with `horizon_days` above 1, the default, also needs the weekend residential extract: run `python 7_circuit_instantiation/build_evwatts_extract.py --day-type weekend` once (see "The multi-day window"). `--venue office --day-type weekend` builds the office weekend extract, which no run reads; it backs the weekend shares in `ev_inputs.yaml`. The NHTS weekend extract is tracked; `build_nhts_extract.py --day-type weekend` rebuilds it.

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

Then run these three scripts from the repository root:

```powershell
python gather_m2_cases.py
python validate_2x2.py
python gen_results_table.py
```

- `gather_m2_cases.py` stacks the eight `aggregate_m2_combined.csv` files into `<runs_root>/m2_all_cases_all_seasons.csv`.
- `validate_2x2.py` prints the cross-case checks on that file and writes `<runs_root>/peaks_per_combo.csv`.
- `gen_results_table.py` writes Table 2 as `table2.csv` and `table2.md` to `<runs_root>/`.

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
python run_case.py --case <case> --phase growth --season <season>       # load growth plan; real work only with growth_years above 0
python run_case.py --case <case> --phase 5a --season <season>           # EULP parquet downloads
python run_case.py --case <case> --phase 5b --season <season>           # baseline profiles
python run_case.py --case <case> --phase 5d --season <season>           # scenario controls (combine_scenarios.py)
python run_case.py --case <case> --phase 5b_variants --season <season>  # DM and uncontrolled profiles
python run_case.py --case <case> --phase 5c --season <season>           # CSV conversion
python run_case.py --case <case> --phase 5c_variants --season <season>  # CSV conversion, DM and uncontrolled
python run_case.py --case <case> --phase 6 --season <season>            # kvar preparation
python run_case.py --case <case> --phase 6_variants --season <season>   # kvar preparation, DM and uncontrolled
python run_case.py --case <case> --phase mix_days --season <season>     # circuit days and their profiles; real work only under per_circuit
python run_case.py --case <case> --phase 7a --season <season>           # profile bridge and mixes copy
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
```

The saved time-of-use rates in `7_circuit_instantiation/data_tariffs/` are tracked, so a cold clone needs no API key. To fetch them again, set `openei_api_key_file` in `configs/local.yaml` to a text file that holds an OpenEI API key and run `python 7_circuit_instantiation/fetch_tou_rates.py` from the repository root. `--all` does not run it.

The mixes file is an input. Phase 7a copies the file that `mixes_file` in `configs/defaults.yaml` names, by default `0_experimental_design/mixes_fixed.yaml`. https://github.com/DeltaE/j-uncertainty-grid-modernisation writes the mixes file of a designed experiment.

## Settings from a caller

A program that calls this repository can change settings without editing its files. In this example the folder `my_settings/` sets the low work share and the runs folder.

1. The caller writes only the keys it changes, in files named as the repository's settings files: `topology_registry.yaml`, `donor_registry.yaml`, `defaults.yaml`, `local.yaml`, `pipeline_config.yaml` and `growth.yaml`. Here `my_settings/pipeline_config.yaml` holds `ev_work_share_case: low` and `my_settings/local.yaml` holds `runs_root: <folder>`.
2. `python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --settings my_settings` checks the folder and the key paths before any phase runs. It stops with `[FAIL]` on a missing folder, on a `.yaml` or `.yml` file with another name, on a file that is not a mapping, on a key that is a mapping on one side only, and on a key path of `pipeline_config.yaml` or a top-level key of `defaults.yaml` that the repository's file lacks. `growth.yaml` is merged over `configs/growth.yaml` and is strict as `pipeline_config.yaml`, except under its maps `infill_share_metro` and `block_attach_buses`, which take new keys. Other files, such as a README, are ignored.
3. Each settings file is merged over the repository's file of the same name. Mappings merge key by key. Any other value (a number, a string, a list, null) replaces the repository's value. The registries and `local.yaml` take new keys, such as a new topology, a new donor or a machine path. `configs/local.yaml` may be absent when the folder holds `local.yaml`.
4. The merged values reach `run_case.py` and, through `PIPELINE_SETTINGS_DIR`, every phase: `pipeline_utils.load_config` merges the folder's `pipeline_config.yaml` in each script, and `pipeline_utils.load_growth` its `growth.yaml`.
5. `run_case.py` prints the folder and the key paths of each settings file. `<run_dir>/resolved_case.yaml` gains a `settings` block with the folder and the key paths of each file, and `<run_dir>/settings/` holds a copy of each settings file.

The folder may also hold `given_days.csv`, the day the caller gives each feeder and season under `peak_day_rule: given` (see "Peak-day rules").

Without `--settings` a run is as before.

`eulp_release` in `pipeline_config.yaml` names the ResStock and ComStock releases and their OEDI year folders (`residential_year` and `commercial_year`, both 2024). The current releases, 2024 `resstock_tmy3_release_2` and 2024 `comstock_amy2018_release_1`, keep the folder names `Metadata_<ST>_Residential`, `Metadata_<ST>_Commercial`, `parquet_residential_short_<date>_<ST>` and `parquet_commercial_<date>_comm_<ST>`. Any other release adds `_<year>_<release>` to the metadata folder and to the download folder of its dataset, so the files of two releases never mix. Phase 1 stops with `[FAIL]` when the metadata folder of such a release is missing under `eulp_metadata_root`.

## Peak-day rules

`peak_day_rule` in `pipeline_config.yaml` sets the calendar day that each circuit is simulated on. Under `per_circuit` and `per_group`, baseline circuits run on each feeder's baseline seasonal peak day and the rule sets the day of each mixed or stress circuit.

- `per_circuit`, the default: all heating groups of a circuit run on one day, the seasonal peak day of the circuit's building load under its mix. Phase `mix_days` finds that day and writes `<ws>/mix_days/<ST>_circuit_days.csv`, `<ST>_circuit_labels.csv` and `<ST>_circuit_weights.csv`. For each mix that is not 100 % baseline, it also writes the subtree `<ws>/mix_days/<mix>/` with the 5b, 5c, 6 and 7a outputs for that day. With load growth on, the day is the peak day of the grown curve and the subtree of every mix is written (see "Load growth over planning years").
- `per_group`: each heating group (baseline, dm, uncontrolled) runs on its own seasonal peak day. Phase `mix_days` writes nothing.
- `given`: the caller names the day of every circuit. In this example the caller runs both feeders of a substation of `NC_GSO_urban__NC`, `uhs13_1247--udt4015` and `uhs13_1247--udt4819`, on 15 July.
  1. The settings folder `my_settings/` holds `pipeline_config.yaml` with `peak_day_rule: given` and `given_days.csv` with the columns `Feeder`, `Season`, `Month` and `Day`. Each row gives one feeder, named as its SMART-DS feeder folder (as in `<ST>_peak_days.csv`), one season, and a month and day without a year. Here the rows are `uhs13_1247--udt4015,summer,7,15` and `uhs13_1247--udt4819,summer,7,15`.
  2. `python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --season summer --settings my_settings` checks the file before any phase runs.
  3. Phase `mix_days` takes the given day for every mix, 100 % baseline mixes included, and cuts the profiles of every heating group on it. `<ws>/mix_days/<ST>_circuit_days.csv` records the day with the largest value of the mix's feeder curve on it as `Peak_kW`.
  4. Phases 7b and 7c read the day and the profiles of every circuit from `<ws>/mix_days/<mix>/`. PV follows the day.
  5. `run_case.py` prints the rows. `<run_dir>/resolved_case.yaml` lists them in its `settings` block, and `<run_dir>/settings/` holds a copy of `given_days.csv`.

  `run_case.py` stops with `[FAIL]` when the rule is `given` without `--settings` or without `given_days.csv` in the folder, when the folder holds `given_days.csv` under another rule, and on a wrong header, no data row, an empty feeder, a season other than `summer` or `winter`, a month or day that is not a whole number, a month and day that are not a date of a 365-day year (29 February stops), a month outside the season (6 to 8 for summer, 12, 1 and 2 for winter) or a feeder and season given twice; phase `mix_days` stops when a feeder of the case has no row for the run's season.

To switch, set `peak_day_rule` to `per_circuit`, `per_group` or `given` before the run. `run_case.py` stops on any other value. PV follows the day the circuit runs on.

## The multi-day window

`horizon_days` in `pipeline_config.yaml` sets how many days each circuit is simulated on. OpenDSS solves them as one continuous run of 96 x `horizon_days` steps. The documented values are 1, 7 and 14, and the default is 7. With `horizon_days: 1` a run is the one-day run on the peak day and every output is as before.

- The window holds `horizon_days` consecutive days around the simulated peak day, day X, with day X at position ceil(`horizon_days` / 2): X-3 to X+3 for 7 days, X-6 to X+7 for 14 days.
- The window stays inside the season and inside one stretch of the data year: summer 1 June to 31 August; winter 1 January to 28 February, or 1 to 31 December. A window that would leave its stretch is shifted back into it, so it never crosses 31 December. The season months are those of Phase 5b (`WINTER_MONTHS` and `SUMMER_MONTHS` in `find_max_day_curve_impl.py`).
- Day X is picked as before, under every value of `peak_day_rule`. Under `given` the caller's day is day X. Under `per_group` each heating group has its own window around its own day X, and the circuit's window, PV and day types follow the baseline group.
- The dates are those of 2018, the calendar of the building curves, so each window day is a weekday or a weekend day. A federal holiday keeps the day type of its weekday. Day X always runs as in the one-day run, with weekday sessions, whatever its date.
- `run_case.py` stops with `[FAIL]` on a value that is not a whole number of days, 1 or above. A window longer than its stretch stops with `[FAIL]` in Phase 5b.

ASSUMPTION: the multi-day window is 7 days, three days either side of the simulated peak day, kept inside the season. It covers Winter Storm Elliott (21 to 26 December 2022, 6 days, with load shed in the Carolinas) and the average recent heat wave in large U.S. cities (about 4 days) with lead-in days; Winter Storm Uri in Texas lasted 13 days (8 to 20 February 2021), so `horizon_days` 14 is the longer option, and a shorter window gives batteries fewer days to run down. The building curves use typical-year and 2018 weather, so the window holds no historical storm.

What each phase does with a window:

1. Phase 5b, and phase `mix_days` for each mix, cut every building profile on each window day as they cut day X, and join the days in date order.
2. Phases 5c, 6 and 7b carry 96 x `horizon_days` values per loadshape. Phase 6 takes the kvar to kW ratio of each step from its own timestamp.
3. In Phase 7c each PV array takes each day's shape from that day's own month and day of the solar file. The EV cars charge day after day (see "EV cars"), the controlled cars are placed on each day (see "EV control"), and the batteries carry their energy from one day to the next (see "PV and storage"). Under `pv_rule_<segment>: peak_ratio` a host's peak is that of day X, so the window changes no size.
4. Each circuit folder gets `window_days.csv`: one row per window day with its date, weekday, day type, day index, a flag on day X and the holiday name, if any. The per-step tables get `date`, `day_index` and `day_type`. Phase 8 adds the same columns to `aggregate_m1.csv` and `aggregate_m2.csv` and writes the steps of day X as `day_x_first_step` and `day_x_last_step` in `circuit_summary.csv` and in the summary rows (see `docs/outputs.md`).

A caller that wants the one-day run sets `horizon_days: 1` in the `pipeline_config.yaml` of its `--settings` folder.

## Heating labels and EV hosts

Phase 7b and phase `mix_days` deal the heating groups (baseline, dm, uncontrolled) of each feeder and mix with `7_circuit_instantiation/heating_split.py`. `heating_label_unit` in `pipeline_config.yaml` sets what is counted:

- `building`, the default: each building profile (yearly loadshape) of the feeder gets one group, the group counts are exact over buildings by largest remainder, and every customer of a building runs in its group.
- `customer`: the counts are over customers (load names), and a building shared by several customers takes the group of the last one dealt.

Phase 7b and phase `mix_days` stop on any other value. Every load runs on a building profile: Phase 7b stops with `[FAIL]` and the loadshape name when a loadshape has no kW or kvar CSV, and `missing_files_report.json` stays empty.

SMART-DS writes a customer on a 120/240 V service as two Load lines, `<customer>_1` and `<customer>_2`, one on each 120 V leg, for example `load_p1ulv10415_1` and `load_p1ulv10415_2` in https://oedi-data-lake.s3.amazonaws.com/SMART-DS/v1.0/2018/GSO/urban-suburban/scenarios/base_timeseries/opendss/uhs13_1247/uhs13_1247--udt4819/Loads.dss. Phase 7b splits each customer's building curve over its Load lines: each line takes as kW its share of the customer's SMART-DS kW (the line's kW in the feeder's `Loads.dss` over the sum over the customer's lines) and as kvar its share of the customer's SMART-DS kvar (`heating_split.line_shares`). A customer on two 120 V legs draws its building once, half on each leg, and a one-line load takes its whole building curve. A customer whose kvar sum is 0 takes its kW shares as kvar shares; a customer whose kW sum is 0 stops Phase 7b with `[FAIL]`. Phase 7b prints the count of customers by number of lines per circuit.

Phase 7b classes each load as residential when every loadshape of the load starts `res_`, commercial when every one starts `com_`, and prints the counts per circuit. EV hosts are drawn among the residential loads only, so `ev_perc` of a mix is the share of homes with an EV.

## EV cars

The Phase 7 deploy builds one car per EV host, with its own uncontrolled row of kW over the 96 intervals of the day (`7_circuit_instantiation/deployer_modules/ev_cars.py`). `ev_cars` in `pipeline_config.yaml` sets where each car comes from. Main runs use the defaults, `ev_cars: evwatts_sessions` and `ev_home_window: true`.

- `evwatts_sessions`, the default: each car draws one measured weekday home Level 2 charging session of EV WATTS, from chargers in the donor state's census division. The car plugs in at the session's start, stays plugged in until its end and charges the session's energy.
- `nhts_days`: each car draws one 2017 NHTS weekday vehicle-day of the donor state, weighted by the household weight. A car that drove arrives home at its last arrival and leaves at its first departure; it charges the miles it drove times 33.7 / 99.9 kWh per mile. A car that did not drive does not charge. A vehicle-day with a driver trip faster than `nhts_max_trip_speed_mph` of `ev_inputs.yaml` (85 mph, the highest posted US speed limit) is class iv and is never drawn.
- `session_rows`: the repaired 2024 generator, kept as a check. Each charging car charges the daily energy of the Team-Nando weekday Level 2 median curve as one block, started where the fleet is furthest below that curve.

`ev_lvl2_perc` of the mix is the share of a group's cars with a Level 2 charger (7.2 kW); the rest charge at Level 1 (1 kW). Under `evwatts_sessions` a Level 2 car charges at its session's mean power. Under `evwatts_sessions` and `session_rows`, the share of cars that charge on the day is measured from the EV WATTS extract every run; the other cars do not charge. Every draw is seeded from the mix's `ev_seed`, the feeder and the draw's name, so the baseline, mixed and stress circuits of one feeder share their draws and a rerun repeats them.

`ev_work_share_case` picks the share of the charging cars that charge at a workplace instead of at home: `low` 0, `moderate` 0.10 (the default) and `high` 0.20, the `work_share` menu of `ev_inputs.yaml` (from EVI-Pro Lite and the INL charging study). Each car charges at one place on the simulated weekday. One car goes through these stages:

1. It charges today: it drew an EV WATTS session under `evwatts_sessions`, or an NHTS vehicle-day that drove under `nhts_days`.
2. It is one of the floor(share x charging cars + 0.5) cars of its group drawn for work, with the draw `work_<group>`.
3. It draws an office: one of the circuit's commercial loads, at random with replacement (`office_<group>`), so several cars can share one office.
4. Under `evwatts_sessions` it draws one Business Office Level 2 weekday session of the office extract, from chargers in the donor state's census division: it plugs in at the session's start for the session's duration and charges the session's energy at its mean power. Under `nhts_days` it draws one weekday vehicle-day with a stop at work: its window is the time parked at work, in pieces when it leaves and returns, and it charges the miles it drove times kWh per mile at 7.2 kW.
5. Its two EV loads sit on the office's buses (`EVu_w<i>_<office>_1` and `_2`, or `EVc_w<j>_`), and nothing is charged at its home.
6. A controlled work car keeps its charging inside its window at work, and under `valley_fill_transformer` it fills the service transformer of its office.
7. Its row in `<circuit>/EVControl/ev_places.csv` records its home host and its office, with the bus and coordinates of each.

Under `session_rows` every car charges at home: the work share is not applied. A circuit without a commercial load keeps every car at home. The deploy prints the case, the share, the commercial loads and the work cars per group.

`ev_home_window: true` keeps the charging of each controlled car inside the intervals it is plugged in at home or at work: its EV WATTS session, its NHTS vehicle-day, or under `session_rows` a drawn NHTS vehicle-day. Energy that does not fit is left over. With `false`, controlled cars may charge in any interval of the day.

`ev_day` picks the value set of every input in `ev_inputs.yaml`. Main runs use the default, `ev_day: typical`. `stress` changes behaviour, never hardware:

- every car charges under `evwatts_sessions` and `session_rows`, and the NHTS pool keeps only vehicle-days that drove from and to home (class i): the cars of `nhts_days` and the windows of the controlled cars of `session_rows`;
- the EV WATTS and NHTS pools keep only the months of the simulated season: June, July and August for summer, December, January and February for winter (the meteorological seasons);
- `session_rows` uses the 75th percentile check curve;
- the valley rules plan on the day-ahead forecast error;
- `offpeak_start` cars spread their starts with a standard deviation of 15 minutes instead of 60.

The seeds and draw names are the same under both values, so a stress run differs from a typical run only by the values. The deploy prints the size of each draw pool.

Over a window of more than one day (`horizon_days` above 1) the cars charge day after day. The cars of day X stay those of the one-day run. One car goes through these stages:

1. It keeps its charger and its drawn weekday session or vehicle-day for every weekday of the window. Under `evwatts_sessions` and `nhts_days` it also draws one weekend session or vehicle-day, from the weekend extracts (`build_evwatts_extract.py --day-type weekend`, `build_nhts_extract.py --day-type weekend`), and keeps it for every Saturday and Sunday. `session_rows` has one curve and uses it on every day.
2. On day X it charges or not as in the one-day run. On every other day, under `evwatts_sessions` and `session_rows`, a seeded draw with the measured share of that day's type decides whether it charges. The weekend share is measured on the weekend extract with the formula of the weekday share. Under `ev_day: stress` every car charges on every day. Under `nhts_days` a car charges on every day whose vehicle-day drove.
3. Its plug-in window runs on the window's own timeline: charging past midnight lands on the next day. The first day of the window receives the part after midnight of the session of the day before it, which is drawn as any other day. A window ends when the car plugs in again.
4. Energy that does not fit inside its plug-in window on a charging day is charged on the next evening without a drawn session, from its own plug-in time, at its own power, inside its own window. Energy still owed when the window ends is reported and not charged.
5. A work car charges at its office on weekdays and at home, with its weekend session, on weekend days. For this it has two more EV loads at home, `EVu_<host>_1` and `_2` (or `EVc_`), with the shape `EVu_<i>h`. Work cars are the work cars of day X, plus the work share of the cars that do not charge on day X, so the work share holds on every weekday.
6. `<circuit>/EVControl/ev_car_days.csv` records each car and day: whether it charges, the session, the place, and the energy needed, delivered, topped up and owed.

ASSUMPTION: over a horizon of more than one day each car keeps its one drawn session and charger, and on every day other than the simulated peak day it charges with probability equal to the measured share of days of that type with a session at home chargers of its census division (for example 0.403 South Atlantic and 0.454 West South Central on weekdays, 0.384 and 0.435 on Saturdays and Sundays), drawn independently each day. Real drivers keep habits such as fixed charging days, so drawn days spread more evenly than real ones, while the expected sessions per car and the fleet energy per day equal the measured values.

ASSUMPTION: energy a car cannot charge inside its plug-in window on a charging day is charged on the next evening the car has no drawn session, from its own plug-in time, at its own power, inside its own window; energy still owed when the horizon ends is reported and not charged. A Level 1 car at 1.0 kW needs 10 h for a 10 kWh session, so without this rule it would receive less energy over the horizon than its sessions record; when every car charges every day (stress) no top-up occurs.

ASSUMPTION: workplace charging happens on weekdays only. EV WATTS Business Office Level 2 chargers record a session on 11 to 14 percent of Saturdays and Sundays in service against 30 to 32 percent of weekdays, and a weekend charger-day takes about a third of a weekday's energy (`weekend_files` in `ev_inputs.yaml`, EV WATTS, https://doi.org/10.15483/1970735).

A worked example of the top-up, from the 2017 NHTS vehicle-day of household 30022175, vehicle 1, in NC: a Level 1 car at 1.0 kW is plugged in from 18:30 to 07:00, 50 intervals, and needs 15.25 kWh a day (45.2 miles at 33.7 / 99.9 kWh per mile). Each charging night 12.50 kWh fit and 2.75 kWh are left over. With charging days 1, 4, 5 and 6 of a 7-day window, the car tops up 2.75 kWh on day 2 and the 8.25 kWh of days 4, 5 and 6 on day 7. Its windows then hold 61.0 kWh, against 50.0 kWh if the leftovers were dropped. The day 7 top-up starts at 18:30, so the 2.75 kWh that fall after the window's last midnight are reported as owed. When every car charges every day (stress) the car has no free evening and nothing is topped up.

The inputs and their sources are in `7_circuit_instantiation/data_ev_cars/ev_inputs.yaml`. The deploy writes one row per car to `<circuit>/EVControl/ev_cars.csv` (see `docs/outputs.md`).

## EV control

`ev_control` in `pipeline_config.yaml` sets how the Phase 7 deploy shapes the charging of controlled EVs. Every circuit has uncontrolled and controlled cars, and each controlled car starts from its own uncontrolled row (see "EV cars"). Main runs use the defaults, `ev_control: valley_fill_feeder` and `ev_valley_base: buildings_only`.

- `uncontrolled`: controlled cars keep their session rows.
- `valley_fill_feeder`, the default: the deploy solves the circuit without EVs, adds every uncontrolled car's kW to the feeder-head load, and places each controlled car, in order of plug-in time, on the intervals where the forecast of that load is lowest. A car keeps its daily energy and its number of charging intervals.
- `valley_fill_transformer`: the same, on the load of each car's own service transformer, plus the uncontrolled cars on it. A car whose host has no single service transformer uses the feeder-head load.
- `water_fill_feeder`: the same base, order and forecast as `valley_fill_feeder`, but each car's power varies from 0 up to its power in each interval of its window, filling the lowest intervals toward one level, the valley-filling schedule of Gan, Topcu and Low (2013), https://doi.org/10.1109/TPWRS.2012.2210288.
- `offpeak_start`: each controlled car whose plug-in window holds an interval of the cheap period of the donor state's time-of-use rate has a schedule time: the start of the cheap period it meets, moved by a normal draw with a standard deviation of `start_spread_min` (60 minutes typical, 15 stress), rounded to whole intervals. The car starts at the later of its schedule time and its plug-in, capped at the end of its window, so a car plugged in after its schedule time starts at once. It charges at its own power until its daily energy is delivered or the window ends. A car whose window holds no cheap interval keeps its plug-in start. A car without a window takes its first charging interval as its plug-in and wraps over midnight. The rate is the weekday schedule of the simulated day's month, because the cars draw weekdays.

The valley rules (`valley_fill_feeder`, `valley_fill_transformer`, `water_fill_feeder`) place controlled cars in order of plug-in time, the day running from 04:00 as the NHTS travel day. Cars that do not charge, or drew a day without driving, come last; ties keep host order. The order holds under `ev_home_window: false` too.

The valley rules plan on a forecast of each curve they fill, not the curve itself, because an aggregator does not know the day's load in advance. For a curve with mean load W (kW), the relative error CV(W) comes from Sevlian and Rajagopal, https://arxiv.org/abs/1404.0058v3: the one-hour-ahead model on a typical day and the day-ahead model on a stress day. The error is normal, one draw per hour for each curve, seeded like the cars. Each placed car joins the forecast, because the aggregator knows its own cars. OpenDSS still solves the true loads. A curve with W <= 0 gets no error.

The valley rules and `offpeak_start` keep each car inside its window when `ev_home_window` is true. The service transformer map leaves out lines switched out with `enabled=n`, as OpenDSS does when it solves.

`ev_valley_base` sets what the no-EV solve of the valley rules holds: `buildings_only` (the default) or `after_pv` (also PV). It never holds storage, except under `storage_order: before_cars` (see "PV and storage"), when it holds PV and storage. The feeder and transformer rules compare a feeder view with a local view of where charging lands.

`ev_valley_day` sets the curve the controlled cars see on each day of a window of more than one day. Both values give the one-day run at `horizon_days: 1`.

- `own_day`, the default: the no-EV solve covers the whole window, and each day's charging and top-up cars are placed, in order of plug-in time on the window's timeline, on that day's own forecast. Each day has its own forecast error: day X keeps the draw of the one-day run and every other day has a draw of its own. `offpeak_start` reads the tariff row of each day's month and day type, the weekday schedule on weekdays and the weekend schedule on Saturdays and Sundays.
- `peak_day`: every day's cars are placed on day X's forecast, repeated on each day. `offpeak_start` reads the tariff row of day X's month and of each day's own day type.

The rates are dated copies of OpenEI U.S. Utility Rate Database records in `7_circuit_instantiation/data_tariffs/<ST>_urdb_rate.json`, with their source URL. `fetch_tou_rates.py` chooses them from the queries in `data_tariffs/rate_queries.yaml`. Each file records whether its rate was current when it was fetched.

## PV and storage

PV and storage go on two segments of loads: homes (every yearly loadshape of the load starts `res_`) and commercial loads (every one starts `com_`). Each segment has its own switches in `der_sizing` (`pv_residential`, `pv_commercial`, `storage_residential`, `storage_commercial`, all `true`) and its own shares in each mix (`pv_res_perc`, `pv_com_perc`, `storage_res_perc`, `storage_com_perc`). A mix without one of these keys, or without `ev_lvl2_perc`, stops Phase 7b. Phase 7b draws round(share x loads of the segment) hosts, at least one when the share is above 0 and the segment has loads, with the mix's `pv_seed` and `storage_seed`. `storage_hosts` sets where the batteries go: `with_pv` (the default) draws them among the segment's PV hosts first, `independent` among all its loads, `apart` among its loads without PV.

At a home with two legs (`<host>_1` and `<host>_2`), each PV array and battery is split into two equal halves, one on each leg's bus, where the EV legs go. A load without legs takes one unit on its own bus.

PV size (DC) under `pv_rule_<segment>: roof_and_use` (the default) is the lesser of roof coverage x roof area x module kW per m2 and the annual use share x the building's baseline annual electricity use / the annual yield of the donor's SMART-DS solar file. `roof_area_source: floor_stories` (the default) takes floor area over stories, tilted 20 degrees for homes as LBNL does for its coverage shares; `metadata` takes the building model's own roof column. The commercial `coverage_rule_commercial: comstock` uses the ComStock rule (40 % of the metadata roof at 0.21 kW per m2) instead of the LBNL coverage share. The inverter is Pmpp / inverter loading ratio. Storage kW is a ratio of the host's PV kW (1.0 for homes and commercial arrays up to 100 kW, 0.5 above), also at a storage host without PV, and kWh is a duration times kW. `sizing_case` (`low`, `moderate`, `high`) picks each parameter's entry; `low` gives the smaller systems. `pv_rule_<segment>: peak_ratio` keeps the earlier rule on the host's peak kW. The sources of every value are in the comments of `der_sizing`.

`storage_rule` sets how the batteries run. `schedule` (the default) writes no controller: each host's batteries follow a daily plan computed in Python on the forecast of their view's curve, in five stages.

1. The plan uses the forecast of the view's curve for the day, with the forecast error of the EV valley rules and its own draw `forecast_storage_<view>`.
2. For a starting energy s and a discharge budget x (kWh delivered to the grid), the battery discharges above the level that holds x within its kW (peak shaving) and charges below the level that refills x / (discharge efficiency x charge efficiency) within its kW (valley filling, Gan, Topcu and Low 2013, https://doi.org/10.1109/TPWRS.2012.2210288). Both levels are solved exactly on the piecewise-linear curve.
3. x is the largest budget, found by bisection, for which the stored energy stays between `storage_reserve_pct` and full at every step and ends the day at s.
4. Under `schedule_start: best` (the default), stages 2 and 3 run for every s from `storage_reserve_pct` to full in steps of `schedule_start_step_pct` (10 %), and the plan that leaves the lowest forecast maximum of the view is kept; a tie goes to the larger x, then to the lower s. Under `fixed`, s is `storage_start_pct`.
5. The host's plan joins the curve and the next host plans on it. OpenDSS follows each plan (`DispMode=FOLLOW`), each battery starting at s (`%stored`).

Over a window of more than one day each host's plan is one loadshape of 96 x `horizon_days` points, and each day is planned in turn:

1. The day is planned on its own forecast, with its own forecast error, from the energy the day before left. The first day starts at s.
2. The battery discharges above the level that holds the discharge budget x, and charges below a level that is never above the discharge level, with the grid energy that brings the stored energy back to s at the end of the day.
3. x is the largest budget for which the stored energy stays between `storage_reserve_pct` and full at every step of the day. A day whose valleys cannot hold the charge ends below s; the next day starts there and aims at s again.
4. s comes from `schedule_start`: `best` (the default) takes the s of the one-day rule on day X's forecast; `best_window` runs every s through the whole window and keeps the one that leaves the lowest forecast maximum of the window, with the ties of `best`; `fixed` is `storage_start_pct`. At `horizon_days: 1` `best` and `best_window` give the same plan.
5. `StorageControl/storage_midnights.csv` records, per battery and day, the planned and the monitored stored energy at midnight.

Under `simple` and `tuned` the controller keeps one pair of targets for the whole window, set on the window's forecast, and the batteries carry their energy through the continuous solve.

`simple` and `tuned` write one OpenDSS `StorageController` per view, discharging above `kWTarget` (PeakShave) and charging below `kWTargetLow` (PeakShaveLow). `simple` sets them from the view's daily peak and mean (`simple_peak_fraction`, `simple_mean_fraction`); `tuned` at the level above which the curve holds the batteries' usable energy and the level below which filling the curve recharges them. Under these rules every battery starts at `storage_start_pct`, and the targets use the same forecast of the measured curve.

- `storage_view`: `feeder` (the default, the feeder-head line), `transformer` (each host's service transformer) or `building` (the line that feeds the host's bus).
- `storage_order`: `after_cars` (the default; storage watches the curve with the cars placed), `before_cars` (storage watches the curve without cars, and the cars' base solve holds the storage) or `same_measurement` (each without the other).
- `storage_measure`: `all_placed` (the default; buildings, PV and, under `after_cars`, cars) or `buildings_only`.
- `storage_layer`: `add_kw` (the default; a buildings-only solve plus the kW of the layers on the view) or `solve` (an OpenDSS solve with the layers in).

Every battery draws standby power. Under `storage_standby_element: load` (the default), `Storage.dss` gives each Storage element `%IdlingkW=0` and writes after it a constant-power Load `standby_<battery>` on the battery's bus that draws the standby kW at every step (`status=fixed`). Under `idling`, the standby is the OpenDSS `%IdlingkW` of each Storage element. `storage_standby_case` (`low`, `moderate`, the default, or `high`) picks the entry. A home battery draws `storage_standby_w` (2, 12 or 71 W), the lowest, median and highest standby power measured with the battery discharged on 26 residential systems by Orth et al. (2023), https://doi.org/10.1016/j.est.2023.107299, as a percent of the host's storage kW. A commercial battery draws `storage_standby_pct_of_kw` of its kW (0.04, 0.24 or 1.42 %).

## Load growth over planning years

A run simulates the circuits as SMART-DS built them, with the building load of the data year. Load growth moves a run to one planning year, `growth_years` years after the data year. Existing customers use more or less electricity. New homes and businesses arrive as copies of the circuit's own customers, one at a time or as whole copied laterals. Named loads, such as a hospital, can be added. The run also reports the planning limits of the grown circuit. Nothing in the network is rebuilt.

Every setting sits in `configs/growth.yaml`. The tracked file has `growth_years: 0`, which is growth off: phase `growth` prints one line, no growth output is written, and every output equals a run without the file. A caller turns growth on with a `growth.yaml` in its `--settings` folder (see "Settings from a caller"). That file holds only the keys it changes. Every key path must exist in the tracked file, except under `infill_share_metro` and `block_attach_buses`, which take new keys. A list replaces the tracked list. `run_case.py` checks every key before any phase and stops with one `[FAIL]` line that names the key, the value and the accepted values.

```yaml
# my_settings/growth.yaml: year 10, new homes split between infill and blocks by the metro share
growth_years: 10
infill_share: metro
```

One run is one planning year in one workspace. A study of several years runs each year in its own workspace.

### Keys

| Key | Values | Meaning |
| --- | --- | --- |
| `growth_years` | whole number, 0 or above; default 0 | Years after the data year. 0 is growth off |
| `case` | `low`, `moderate`, `high`; default `moderate` | The AEO2026 case that gives all four rates: Low Economic Growth, Counterfactual Baseline, High Economic Growth |
| `rate_cases` | percent a year per rate and case | `households`, `use_per_household`, `floorspace`, `use_per_ft2` |
| `rates` | `null` or a number per rate | A number replaces that rate of the case |
| `infill_share` | `1.0`, `metro`, `national` or a number from 0 to 1; default `1.0` | Share of the new homes built as infill; the rest arrive as blocks |
| `infill_share_metro` | topology: number | The share of each topology's metropolitan region, used by `metro` |
| `infill_share_national` | number | The share used by `national` |
| `companions` | `feeder`, `national`, `aeo`; default `feeder` | How many new businesses come with the new homes |
| `companions_national` | two numbers | Commercial buildings and households, in millions, for `national` |
| `companion_excluded_types` | list of ComStock building types | Types never copied as a companion |
| `block_attach_buses` | feeder: list of buses | Where blocks attach, used in order before any drawn bearing |
| `named_loads` | list of `{feeder, type, count, year, bus}` | Loads added by name; `bus` is optional |
| `named_load_bus` | `seeded`, `strongest`, `weakest`; default `seeded` | The bus of a named load without `bus` |
| `load_factors` | list of `{feeder, load, factor, peak_factor}` | The factor of one named customer; `peak_factor` is optional |
| `planning_limits.voltage_band` | `repository`, `range_a`, `range_b` or `[low, high]`; default `repository` | The band of the voltage limit, per unit |
| `planning_limits.voltage_bands` | `range_a`, `range_b` | The two ANSI C84.1 bands |
| `planning_limits.line_limit_percent`, `head_limit_percent`, `transformer_limit_percent`, `substation_limit_percent` | percent; default 100 | The loading limits |
| `network_growth.mode` | `"off"` | Only `"off"` is accepted. Keep the quotes: `off` without quotes is a boolean in YAML |

### Rates and factors

The rates are the average annual changes from 2025 to 2050 of the U.S. EIA Annual Energy Outlook 2026, Table 4 (Residential Sector Key Indicators) and Table 5 (Commercial Sector Key Indicators), rounded to two decimals. The sources and the derivation of each rate are written beside the values in `configs/growth.yaml`. One `case` picks all four rates from the same AEO case.

- A home is a customer whose yearly loadshapes all start `res_`. A business is one whose loadshapes all start `com_`. One ResStock sample is one dwelling unit (ResStock documentation, "One Row of Data Is Not One Real House", https://nrel.github.io/ResStock.github.io/docs/resources/explanations/One_Row_Data_House.html), so a home customer is one household and the household rate applies to the count of home customers.
- The factor of every home is (1 + `use_per_household` / 100) ^ `growth_years`. The factor of every business is (1 + `use_per_ft2` / 100) ^ `growth_years`. A customer that is neither keeps factor 1 and is never copied. A new customer takes the factor of its segment.
- A factor multiplies the kW and kvar of each of the customer's Load lines. The loadshape CSVs stay unchanged, so energy and peak move together and the power factor is kept. Growth scales the building load only. EV, PV and storage inputs are never scaled.
- `load_factors` replaces the factor of a named customer. With `peak_factor` the customer's curve is stretched: new = a x old + b, with a = (`peak_factor` x peak - `factor` x mean) / (peak - mean) and b = mean x (`factor` - a), peak and mean being the annual peak and the annual mean of the customer's kW. Annual energy then grows by `factor` and annual peak by `peak_factor`. The customer gets its own loadshape CSVs. The run stops with `[FAIL]` when a point of the year falls below 0, when peak equals mean, or when the feeder or the load is not in the case. For a curve with peak 900 kW, mean 650 kW and minimum 500 kW, `factor: 1.10` and `peak_factor: 1.30` give a = 1.82 and b = -468, so the three values become 1,170, 715 and 442 kW.

The ASSUMPTION labels of the rates are in `configs/growth.yaml`: each growth year applies the 2025 to 2050 average on top of the data year; the national rates stand for one circuit; data centre servers and EV charging are left out of the use rates; the rates are rounded.

### How many new customers

Per circuit, with H its homes and N its businesses in the SMART-DS `Loads.dss`, g(r) = (1 + r / 100) ^ `growth_years`, and Python's `round`:

- New homes = round(H x (g(`households`) - 1)).
- Companion businesses: `feeder` = round(new homes x N / H); `national` = round(new homes / (`households_million` / `commercial_buildings_million`)); `aeo` = round(N x (g(`floorspace`) - 1)).
- Infill homes = round(new homes x share); block homes = new homes - infill homes. The companions split the same way. `metro` takes the share of the run's `topology_id` in `infill_share_metro` and stops with `[FAIL]` when it has none.

Worked example, a circuit of 494 homes and 272 businesses at 10 years with the `moderate` case. g(`households`) = 1.0079 ^ 10 = 1.0819, so new homes = round(494 x 0.0819) = 40. Companions: `feeder` gives round(40 x 272 / 494) = 22; `national` gives round(40 / (127.6 / 5.9)) = 2; `aeo` gives round(272 x (1.0102 ^ 10 - 1)) = 29. With `infill_share: metro` and a share of 0.25, 10 homes are infill and 30 arrive in blocks; of 22 companions, 6 are infill and 16 go with the blocks. The factors are 0.9972 ^ 10 = 0.9724 for homes and 0.9935 ^ 10 = 0.9369 for businesses.

Counts are computed, never drawn. The seeds only choose which customer or lateral is copied and where it attaches. Each circuit has one growth seed, `random_seed` of `pipeline_config.yaml` plus the sha256 offset of `<substation>|<feeder>`, and every draw has its own name on that seed, so adding a draw never moves another. All mixes of a run share the same new customers.

### Infill

- An infill home is a copy of one existing home of the same circuit. The infill homes are the first n of one seeded order of the circuit's homes, so a longer horizon holds every infill home of a shorter one.
- An infill companion is a copy of one business of the companion pool: the circuit's businesses, without the types of `companion_excluded_types` and without any whose floor area is above companions x the circuit's mean floor area per business.
- A copy copies its customer's connection. When the copied customer's service transformer serves more than one customer, the copy gets a new drop: a line from the bus where the copied customer's last line starts, with the same LineCode, phases and length, to a new load bus. When the copied customer is alone on its transformer, the copy gets its own copy of that transformer and of its secondary lines. A copy of a medium-voltage customer gets a copy of the line that feeds its bus, from the same upstream bus. A customer whose load bus is not the end of exactly one line is copied onto its own bus.
- A copy has the Load lines of its customer: legs, kV, phases, model, kW and kvar shares, and loadshape.

### Extension blocks

- A block is a copy of one of the circuit's own laterals. A lateral is rooted at a medium-voltage bus fed by a line of fewer than three phases whose upstream bus is fed by a three-phase line or is the source bus. It holds everything downstream: medium-voltage lines, transformers, secondaries and customers. Laterals with homes only and mixed laterals are templates. Laterals with businesses only are never templates.
- Blocks are placed one after another until no template fits. Each template is a seeded draw among the laterals that fit: no more homes than the block homes still to place and, for a mixed lateral, no more businesses than the block companions still due, each of them in the companion pool. Block homes that no template fits arrive as infill homes, marked `remainder` in the tables.
- Block companions still due after the blocks are dealt to the blocks in build order. Each is a copy of a business of the pool with its own copy of its transformer and secondary, or of its medium-voltage line, connected at the block's attach bus. When no block is built they arrive as infill companions.
- A block attaches at the next unused bus of `block_attach_buses` for its feeder. Otherwise it attaches at the outermost three-phase medium-voltage bus along a seeded bearing from the load centre that is at least r(new) + r(earlier) from every earlier attach bus. The load centre is the mean position of the circuit's customers. r of a lateral is the largest straight distance from its tap bus to any of its buses. Positions come from `Buscoords.dss`, projected to metres. When no bus qualifies the block is not built and its homes arrive as infill homes.

ASSUMPTION: a new customer or block has the line lengths, line codes and transformer ratings of the existing customer or lateral it copies, and its place is electrical: no street map is used. SMART-DS sized its lines and transformers with the Reference Network Model for peak planning loads (https://github.com/openEDI/documentation/tree/main/SMART-DS). A new district with longer runs has lower voltages than its copy shows.

### Named loads

- `named_loads` adds `count` loads of ComStock `type` on `feeder`, present when `year` is at or below `growth_years`. The building is a seeded draw among the buildings of that type in the state's Phase 4 commercial selection. When the selection has none, it is a seeded draw among the buildings of that type in the state's Phase 1 ComStock metadata whose climate zone is the most common zone among the circuit's own businesses. That building is added to the Phase 5a download with the same upgrades as every other. The run stops with `[FAIL]` when the state has no such building.
- The bus is the entry's `bus`, which must be a three-phase medium-voltage bus of the feeder. Without it, `named_load_bus` sets the bus: `seeded` is a seeded draw among the three-phase medium-voltage buses, `strongest` the one with the lowest positive-sequence impedance to the source bus along its path, `weakest` the highest.
- The connection copies the existing business of the feeder whose SMART-DS kW is closest to the new load's annual peak kW. A medium-voltage template gives the new load a copy of its line from the chosen bus. A template behind a service transformer gives it a transformer and a copy of the template's secondary: the transformer has the smallest rating among the feeder's transformers of the template's phases and voltages that is at or above the new load's peak kVA, or the largest when none is large enough, which the table records.
- A building that no load of the feeder uses has no SMART-DS load and so no reactive power series. It draws reactive power at the constant ratio of kvar to kW of its template's SMART-DS Load lines, at every step (an ASSUMPTION, labelled in `configs/growth.yaml`). Its loadshape is named `com_kw_g<bldg_id>_pu`.

### Day X and the mixes

- With growth on and `peak_day_rule: per_circuit`, day X of each circuit and season is the peak day of the grown curve: the sum of the grown curves of all its customers, existing and new. Every mix, the 100 % baseline mix included, is cut on day X by phase `mix_days`, and the baseline check does not run. `given` is unchanged. `per_group` keeps its group days.
- Existing customers keep exactly the heating labels and the EV, PV and storage hosts of a growth-off run of the same mix. New loads never enter an existing shuffle. They get the same mix percentages in separate draws over the new loads only, with no minimum of one. A copy runs in the heating group of its building. A building new to the feeder is labelled in a separate draw.
- PV and storage sizes use the grown annual use, annual use x the host's factor. The roof limit is unchanged.

### Planning limits

With growth on, the Phase 7 deploy reports the planning limits of the grown circuit. Nothing is built, replaced or moved.

- Loading. For every line, the peak current over all steps against the `normamps` of its LineCode. For every transformer, the peak kVA against its kVA. Lines of 1 m or less are switches, fuses and reclosers; they are listed with a flag and left out of the line limit.
- `voltage_band`: customers with any step below the low value or above the high value. EV legs are left out. `repository` is `voltage_band` of `pipeline_config.yaml`. `range_a` is 0.95 to 1.05 and `range_b` is 0.9167 to 1.0583, the ANSI C84.1 service voltages of 114 to 126 V and 110 to 127 V on a 120 V base (USDA Rural Utilities Service Bulletin 1724D-113, Table 1, https://rd.usda.gov/sites/default/files/UEP_Bulletin_1724D-113.pdf; Bulletin 1724D-114, Table 2, https://www.rd.usda.gov/files/UEP_Bulletin_1724D-114.pdf; Pacific Power, Power Quality Standards 1C.2.1, Table 1, https://www.pacificpower.net/content/dam/pcorp/documents/en/pp-rmp/power-quality-standards/1C_2_1_PF.pdf). The setting never changes the existing voltage summaries.
- `line_limit_percent` and `transformer_limit_percent`: 100 percent of the rating (Abraham and Ghosh, DISCO slides, NREL/PR-6A40-89565, slides 13 to 15, https://nrel.gov/docs/fy24osti/89565.pdf). A second sourced value for lines is 75 percent of the thermal rating as the planning rating of conductors (City of Riverside Public Utilities, Distribution Design Manual, DDM-1 Feeder Systems, section 1.2 J, https://www.tellusventure.com/downloads/riverside/DDM-1%20Feeder%20Systems%20.pdf).
- `head_limit_percent`: the peak kVA at the feeder head against `feeder_head_kva`, the value of Phase 8.
- `substation_limit_percent`: the head power of the case's circuits for one mix, summed step by step, against the substation rating. The rating is the sum of the kVA of the transformers in the topology's substation folder, the folder that holds the feeder folders. ASSUMPTION: the feeder head and the substation transformer take the same 100 percent of their rating as lines and service transformers; a utility that keeps a reserve for switching sets a lower value, and more circuits are then over their limit.
- Each block gets the line distance from the source bus to its attach bus, the lowest voltage at its customers, the highest loading on the lines from the source bus to its attach bus, and whether either is outside its limit.

### Phase and outputs

Phase `growth` sits between phases 4 and 5a (`growth_plan.py`). With growth on it writes, under `<ws>/growth/`, the plan `growth_plan.json` and the tables `growth_customers.csv`, `growth_blocks.csv`, `growth_named_loads.csv`, `growth_factors.csv` and `growth_summary.csv`. A building new to a feeder is added to the lists that Phases 5a onward read, with a load count of 0, so every curve that weights buildings by that count keeps its values.

Phase 7b appends the new customers and their lines and transformers to the copied feeder files of each circuit folder. The existing lines of those files stay as they are, apart from the kW and kvar of the Load lines. `scenario_assignments.json` lists the hosts among the new loads under the key `growth`, apart from the existing hosts. Phase 7c writes `loading_lines.csv`, `loading_transformers.csv`, `planning_limits.csv` and `growth_blocks.csv` into each `ModifiedCircuitData/`. Phase 8 adds `growth_years` and the planning-limit columns to `circuit_summary.csv` and to the summary rows, and writes `substation_limits.csv`. `docs/outputs.md` lists every file and column.

A caller that overrides `phase_order` in `defaults.yaml` adds `growth` after `4`. With growth on, a later phase stops with `[FAIL]` when the plan is missing or belongs to other growth settings.

## Known limitations

- The simulation horizon is `horizon_days` days of 96 fifteen-minute steps each, one day at `horizon_days: 1`. Day X is the peak day of the building curves; OpenDSS solves the window around it and no other day. The deploy script, `pfs_ev_base_profiles.py` and the max-day script keep their names.
- Homes use EULP ResStock profiles on TMY3 weather. Commercial buildings use EULP ComStock profiles on 2018 weather, and SMART-DS solar data is for 2018.
- PV and storage sizes follow sourced shares of roof area and annual use, applied to every host of a segment alike. Real systems vary around those shares, and the commercial median PV size of the default cases is below the LBNL median for non-residential systems. See `der_sizing` in `pipeline_config.yaml`.
- PV is sized on the baseline building's annual use, before any heat pump or EV, so a home in the dm or un group keeps the PV of its baseline building.
- Under `roof_area_source: floor_stories` the roof of an apartment is its floor area over the building's stories, so each unit of a multi-family building gets a roof share. Under `metadata` many apartment units have no roof.
- Storage watches the feeder head, a service transformer or a service line. A substation view of storage would need both feeders in one solve.
- ResStock assigns its own existing PV by market distributions, https://natlabrockies.github.io/ResStock.github.io/docs/resources/explanations/PV_System_Assignment_and_Distributions.html. Whether ResStock total electricity is net of that PV is not modelled here.
- A `StorageController` shares the kW it needs over every battery of its view and holds the watched power within a band around its target (`storage_kw_band_pct`, wider than the OpenDSS default) and asks for part of the kW it needs in each iteration (`storage_disp_factor`), so that fleets of many small batteries settle. A view where most batteries are full or empty approaches its target in many small steps; `storage_max_control_iter` sets how many a time step may take.
- Storage shaves the forecast peak of its view with a plan computed from the day's curve. Optimised or co-optimised dispatch of batteries is outside this tool.
- Batteries serve their view of the grid. Household self-consumption control, which most behind-the-meter batteries follow, is not modelled.
- Under `schedule_start: best` each battery starts with the energy that best serves day X and aims to return to it at every midnight. A one-day run (`horizon_days: 1`) returns to it exactly, as if every day had the same curve, and so assumes the day before left that energy. A longer window plans each day on its own curve from the energy the day before left, and assumes only that the day before the window left the starting energy.
- Each case takes its PV shape from one SMART-DS solar site of the donor's region, on the day the circuit runs on: the feeder's baseline peak day under `per_group`, the circuit's day under `per_circuit`. With `horizon_days` above 1 each day of the window takes the shape of its own month and day. See `pv_profile` in `configs/donor_registry.yaml`.
- The docs are Markdown read on GitHub. The Sphinx build needs `myst_parser`.
- `gather_m2_cases.py`, `validate_2x2.py` and `gen_results_table.py` read `configs/local.yaml` only and ignore `--settings` (`gen_results_table.py` takes `--runs-root`).
- Heating labels are dealt per building profile, and buildings serve different numbers of customers, so the realized customer shares can differ from the mix. Under `heating_label_unit: customer` both the building shares and the customer shares can differ, because a building shared by several customers takes the group of the last customer dealt.
- A loadshape whose monthly peaks match no building within the largest tolerance takes the buildings of the next 5 % step that matches, so its profile is further from its SMART-DS peaks. The `Tolerance` column of `df_com_matches_out_<ST>.csv` and `df_res_matches_out_<ST>.csv` records the step reached.
- The forecast error of the valley rules is hourly and independent from hour to hour, while real forecast errors are correlated over hours.
- Controlled cars are placed one at a time in order of plug-in time, so later cars get the valleys that earlier cars leave.
- The start spread of `offpeak_start` is an assumed normal spread, 60 minutes on a typical day and 15 on a stress day.
- Battery standby comes from lab tests of 26 German residential systems and is applied to every battery, commercial ones included. A commercial battery takes the home values per kW of a 5 kW system, as a percent of its kW. Each battery draws its discharged-state standby at every step of the day. Under `storage_standby_element: load` the grid supplies the standby also while a battery discharges, where OpenDSS `%IdlingkW` would take it from the battery.
- The stress day changes behaviour (the share of cars charging, the months drawn, the check curve, the forecast horizon, the start spread), never hardware.
- The tariff is one utility's rate per donor state: its weekday schedule, and with `horizon_days` above 1 its weekend schedule on Saturdays and Sundays. The saved file records whether the rate was current when it was fetched, and `offpeak_start` uses a rate that is no longer current as it is.
- Public EV charging is not modelled.
- Several work cars can share one office load, because the office is drawn with replacement among the circuit's commercial loads (the TX circuits hold 20 and 22 commercial loads).
- An EV WATTS office session is one plug-in at a shared charger, so it can cover less than a car's whole stay at work.
- Cars leaving the feeder for work are taken to balance cars arriving from other feeders: a work car charges at a commercial load of its own circuit.
- Homes heated by electricity run ResStock upgrade 1 in the dm group, the same profile as in the un group. The dm homes that still run baseline are homes the measure does not reach: fuel-heated homes that the ResStock 2024 Release 2 known issue on measure applicability leaves without the measure (https://natlabrockies.github.io/ResStock.github.io/docs/resources/explanations/Issue_2024_2_Measure_Applicability.html), homes with a shared HVAC system, and homes heated by a fuel other than natural gas, propane or fuel oil, which Measure Package 4 does not cover.
- NC cars draw EV WATTS sessions of chargers in the South Atlantic census division and TX cars of chargers in the West South Central division, because EV WATTS gives no state.
- EV WATTS sessions are from 2019 to 2022 and come from early adopters.
- NHTS drivers are from 2016 and 2017 and drove all vehicle types (car, van, SUV, pickup).
- kWh per mile is the average of the model year 2024 new battery EVs, one fleet average that does not vary with speed or season.
- Under `nhts_days` a car plugs in when it arrives home at its last arrival, with no delay.
- The share of cars charging counts one car per residential charger.
- EV WATTS timestamps are read as the charger's local clock time.
- NHTS vehicle-days that drive but neither end nor start at home are left out of the draw, and so are vehicle-days with a driver trip faster than 85 mph, taken as recording errors.
- At `horizon_days: 1` a plug-in window that runs past midnight wraps onto the first intervals of the same day. With `horizon_days` above 1 it runs on to the next day; only the part after the window's last midnight is left out, and its energy is reported as owed.
- The check curves in `7_circuit_instantiation/data_ev/`, used by `session_rows`, are UK home charging from the Electric Nation trial, processed by the University of Melbourne for an Australian project (Team-Nando EV-Demand-Profiles).
- An EV WATTS Level 2 car charges at its session's mean power, which can differ from 7.2 kW.
- Under `per_circuit`, a case-season takes about twice as long and needs more disk than under `per_group`.
- The source monitor m1 reads the source voltage setpoint. Load voltages come from the per-load record (`load_voltages.parquet`, see `docs/outputs.md`).

## Key Handoffs

| Artifact | Producer | Consumer |
| --- | --- | --- |
| `commercial_data_SELECT_STATES.csv`, `residential_data_SELECT_STATES.csv` | `1_data_provenance` cluster `pipeline_state` | `3_tolerance_matching/phase3_match.py` |
| `{STATE}_required_parquets_per_feeder_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5b_profile_generation/phase5b_variants_dm.py` |
| `{STATE}_parquet_and_bldgs_dm.csv` | `5d_scenario_controls/get_scenario_csv_controls.py` | `5c_csv_conversion/parquet_to_csv.py` |
| `profiles_use_bench/` | `7_circuit_instantiation/instantiate_circuits.py` | `7_circuit_instantiation/power_flow_sim_daily_EV_STO_DG_deploy.py` |
| `0_experimental_design/mixes_fixed.yaml` (three hand-set mixes, tracked) | Set by hand | `bridge_phase5c_to_phase7.py` (Phase 7a) copies it to `<ws>/7_circuit_instantiation/mixes.yaml`, keeping the extension of the mixes file, which `7_circuit_instantiation/instantiate_circuits.py` reads |

## License

[Apache-2.0](LICENSE)
