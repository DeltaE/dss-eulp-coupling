# DSS-EULP Coupling Pipeline

Open-data coupling of SMART-DS synthetic distribution feeders with NREL End-Use
Load Profiles (EULP) for distribution system planning under uncertainty.

## Configuration

Each value has one owner:

- `configs/local.yaml` holds the machine paths: `smart_ds_base`, `eulp_metadata_root`, `runs_root` and `evwatts_extract_dir` (see "EV cars"), `openei_api_key_file` for the tariff fetch only (see "EV control"), and `nhts2017_csv_dir` and `evwatts_raw_dir` for the two extract scripts only. Copy it from `configs/local.yaml.example`.
- A case file in `configs/cases/` names a topology, a donor and `execution.max_feeders`. `configs/topology_registry.yaml` and `configs/donor_registry.yaml` hold the values of each topology and donor, such as the feeder folder, the donor state and `eulp_download_date`.
- `configs/defaults.yaml` holds the seasons, the phase order and `mixes_file`.
- `pipeline_config.yaml` holds the method parameters: `random_seed`, `skip_circuits`, `quota`, `eulp_release`, `der_sizing`, `peak_day_rule` (default `per_circuit`; `per_group` remains available, see "Peak-day rules"), `heating_label_unit` (default `building`; `customer` remains available, see "Heating labels and EV hosts"), `voltage_band` (the band for the load voltage summaries), `ev_cars`, `ev_home_window` and `ev_day` (defaults `evwatts_sessions`, `true` and `typical`, see "EV cars"), and `ev_control` and `ev_valley_base` (defaults `valley_fill_feeder` and `buildings_only`, see "EV control").

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

The EV cars of the default `ev_cars: evwatts_sessions`, and of `session_rows`, need the EV WATTS public database (https://doi.org/10.15483/1970735). Create a free account at https://livewire.energy.gov/ds/evwatts/evwatts.public and download its session and evse tables (`evwatts.public.session.csv`, `evwatts.public.evse.csv`). Set `evwatts_raw_dir` to their folder and `evwatts_extract_dir` to a folder outside the repository, then run `python 7_circuit_instantiation/build_evwatts_extract.py` once from the repository root. The EV WATTS data stays outside the repository. The 2017 NHTS extract in `7_circuit_instantiation/data_ev_cars/` is tracked; `python 7_circuit_instantiation/build_nhts_extract.py` rebuilds it from https://nhts.ornl.gov/assets/2016/download/Csv.zip, unpacked into the folder that `nhts2017_csv_dir` names.

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

## Peak-day rules

`peak_day_rule` in `pipeline_config.yaml` sets the calendar day that each mixed or stress circuit is simulated on. Baseline circuits run on each feeder's baseline seasonal peak day under both values.

- `per_circuit`, the default: all heating groups of a circuit run on one day, the seasonal peak day of the circuit's building load under its mix. Phase `mix_days` finds that day and writes `<ws>/mix_days/<ST>_circuit_days.csv`, `<ST>_circuit_labels.csv` and `<ST>_circuit_weights.csv`. For each mix that is not 100 % baseline, it also writes the subtree `<ws>/mix_days/<mix>/` with the 5b, 5c, 6 and 7a outputs for that day.
- `per_group`: each heating group (baseline, dm, uncontrolled) runs on its own seasonal peak day. Phase `mix_days` writes nothing.

To switch, set `peak_day_rule` to `per_circuit` or `per_group` before the run. `run_case.py` stops on any other value. PV follows the day the circuit runs on.

## Heating labels and EV hosts

Phase 7b and phase `mix_days` deal the heating groups (baseline, dm, uncontrolled) of each feeder and mix with `7_circuit_instantiation/heating_split.py`. `heating_label_unit` in `pipeline_config.yaml` sets what is counted:

- `building`, the default: each building profile (yearly loadshape) of the feeder gets one group, the group counts are exact over buildings by largest remainder, and every customer of a building runs in its group.
- `customer`: the counts are over customers (load names), and a building shared by several customers takes the group of the last one dealt.

Phase 7b and phase `mix_days` stop on any other value. Every load runs on a building profile: Phase 7b stops with `[FAIL]` and the loadshape name when a loadshape has no kW or kvar CSV, and `missing_files_report.json` stays empty.

Phase 7b classes each load as residential when every loadshape of the load starts `res_`, commercial when every one starts `com_`, and prints the counts per circuit. EV hosts are drawn among the residential loads only, so `ev_perc` of a mix is the share of homes with an EV.

## EV cars

The Phase 7 deploy builds one car per EV host, with its own uncontrolled row of kW over the 96 intervals of the day (`7_circuit_instantiation/deployer_modules/ev_cars.py`). `ev_cars` in `pipeline_config.yaml` sets where each car comes from. Main runs use the defaults, `ev_cars: evwatts_sessions` and `ev_home_window: true`.

- `evwatts_sessions`, the default: each car draws one measured weekday home Level 2 charging session of EV WATTS, from chargers in the donor state's census division. The car plugs in at the session's start, stays plugged in until its end and charges the session's energy.
- `nhts_days`: each car draws one 2017 NHTS weekday vehicle-day of the donor state, weighted by the household weight. A car that drove arrives home at its last arrival and leaves at its first departure; it charges the miles it drove times 33.7 / 99.9 kWh per mile. A car that did not drive does not charge. A vehicle-day with a driver trip faster than `nhts_max_trip_speed_mph` of `ev_inputs.yaml` (85 mph, the highest posted US speed limit) is class iv and is never drawn.
- `session_rows`: the repaired 2024 generator, kept as a check. Each charging car charges the daily energy of the Team-Nando weekday Level 2 median curve as one block, started where the fleet is furthest below that curve.

`ev_lvl2_perc` of the mix is the share of a group's cars with a Level 2 charger (7.2 kW); the rest charge at Level 1 (1 kW). Under `evwatts_sessions` a Level 2 car charges at its session's mean power. Under `evwatts_sessions` and `session_rows`, the share of cars that charge on the day is measured from the EV WATTS extract every run; the other cars do not charge. Every draw is seeded from the mix's `ev_seed`, the feeder and the draw's name, so the baseline, mixed and stress circuits of one feeder share their draws and a rerun repeats them.

`ev_home_window: true` keeps the charging of each controlled car inside the intervals it is plugged in at home: its EV WATTS session, its NHTS vehicle-day, or under `session_rows` a drawn NHTS vehicle-day. Energy that does not fit is left over. With `false`, controlled cars may charge in any interval of the day.

`ev_day` picks the value set of every input in `ev_inputs.yaml`. Main runs use the default, `ev_day: typical`. `stress` changes behaviour, never hardware:

- every car charges under `evwatts_sessions` and `session_rows`, and the NHTS pool keeps only vehicle-days that drove from and to home (class i): the cars of `nhts_days` and the windows of the controlled cars of `session_rows`;
- the EV WATTS and NHTS pools keep only the months of the simulated season: June, July and August for summer, December, January and February for winter (the meteorological seasons);
- `session_rows` uses the 75th percentile check curve;
- the valley rules plan on the day-ahead forecast error;
- `offpeak_start` cars spread their starts with a standard deviation of 15 minutes instead of 60.

The seeds and draw names are the same under both values, so a stress run differs from a typical run only by the values. The deploy prints the size of each draw pool.

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

`ev_valley_base` sets what the no-EV solve of the valley rules holds: `buildings_only` (the default) or `after_pv_storage` (also PV and storage). The feeder and transformer rules compare a feeder view with a local view of where charging lands.

The rates are dated copies of OpenEI U.S. Utility Rate Database records in `7_circuit_instantiation/data_tariffs/<ST>_urdb_rate.json`, with their source URL. `fetch_tou_rates.py` chooses them from the queries in `data_tariffs/rate_queries.yaml`. Each file records whether its rate was current when it was fetched.

## Known limitations

- The simulation horizon is one day of 96 fifteen-minute steps. The deploy script, `pfs_ev_base_profiles.py` and the max-day script keep their names until the horizon becomes configurable.
- Homes use EULP ResStock profiles on TMY3 weather. Commercial buildings use EULP ComStock profiles on 2018 weather, and SMART-DS solar data is for 2018.
- Storage and PV sizes follow assumed ratios and minimums. See `der_sizing` in `pipeline_config.yaml`.
- Each case takes its PV daily shape from one SMART-DS solar site of the donor's region, on the day the circuit runs on: the feeder's baseline peak day under `per_group`, the circuit's day under `per_circuit`. See `pv_profile` in `configs/donor_registry.yaml`.
- The docs are Markdown read on GitHub. The Sphinx build needs `myst_parser`.
- Heating labels are dealt per building profile, and buildings serve different numbers of customers, so the realized customer shares can differ from the mix. Under `heating_label_unit: customer` both the building shares and the customer shares can differ, because a building shared by several customers takes the group of the last customer dealt.
- A loadshape whose monthly peaks match no building within the largest tolerance takes the buildings of the next 5 % step that matches, so its profile is further from its SMART-DS peaks. The `Tolerance` column of `df_com_matches_out_<ST>.csv` and `df_res_matches_out_<ST>.csv` records the step reached.
- The forecast error of the valley rules is hourly and independent from hour to hour, while real forecast errors are correlated over hours.
- Controlled cars are placed one at a time in order of plug-in time, so later cars get the valleys that earlier cars leave.
- The start spread of `offpeak_start` is an assumed normal spread, 60 minutes on a typical day and 15 on a stress day.
- The stress day changes behaviour (the share of cars charging, the months drawn, the check curve, the forecast horizon, the start spread), never hardware.
- The tariff is the weekday schedule of one utility per donor state. The saved file records whether the rate was current when it was fetched, and `offpeak_start` uses a rate that is no longer current as it is.
- Workplace and public EV charging are not modelled.
- Homes heated by electricity run ResStock upgrade 1 in the dm group, the same profile as in the un group. The dm homes that still run baseline are homes the measure does not reach: fuel-heated homes that the ResStock 2024 Release 2 known issue on measure applicability leaves without the measure (https://natlabrockies.github.io/ResStock.github.io/docs/resources/explanations/Issue_2024_2_Measure_Applicability.html), homes with a shared HVAC system, and homes heated by a fuel other than natural gas, propane or fuel oil, which Measure Package 4 does not cover.
- NC cars draw EV WATTS sessions of chargers in the South Atlantic census division and TX cars of chargers in the West South Central division, because EV WATTS gives no state.
- EV WATTS sessions are from 2019 to 2022 and come from early adopters.
- NHTS drivers are from 2016 and 2017 and drove all vehicle types (car, van, SUV, pickup).
- kWh per mile is the average of the model year 2024 new battery EVs, one fleet average that does not vary with speed or season.
- Under `nhts_days` a car plugs in when it arrives home at its last arrival, with no delay.
- The share of cars charging counts one car per residential charger.
- EV WATTS timestamps are read as the charger's local clock time.
- NHTS vehicle-days that drive but neither end nor start at home are left out of the draw, and so are vehicle-days with a driver trip faster than 85 mph, taken as recording errors.
- A plug-in window that runs past midnight wraps onto the first intervals of the same day.
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
