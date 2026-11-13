# 4. Outputs & Interpretation

## 4.1 Primary Files

### `aggregate_m2_combined.csv`
A feeder‑level **time series** of power flows plus a one‑line metadata “summary” row for each circuit/scenario/season/design.

- **Time‑series rows:** 96 x `horizon_days` per circuit, season, design and scenario (one per 15-minute timestep; 96 at `horizon_days: 1`)
- **Summary rows:** one per circuit, season, design and scenario

**Selected columns (typical):**

- Per-phase apparent/real/reactive: `S1-3 (kVA)`, `P1-3 (kW)`, `Q1-3 (kVAr)`, `Ang1-3 (deg)`  
- Three-phase totals: `P_3ph (kW)`, `Q_3ph (kVAr)`, `S_3ph (kVA)`, `S_sum_3ph (kVA)`  
- Keys to join with summary: `circuit_folder`, `season`, `design`, `scenario`

**Usage patterns:**

- **Peak demand:** `max(P_3ph)` across the timesteps
- **Energy:** trapezoidal integration over `P_3ph`  
- **Imbalance:** `S_sum_3ph - S_3ph` as a simple metric

### `circuit_summary_combined.csv`
One row per circuit/scenario/season/design—metadata to contextualize the time series.

- Fields: `n_loads` (without the battery standby Loads `standby_storage_<unit>` that `storage_standby_element: load` writes in `Storage.dss`), `n_evs`, `n_storage`, `n_pv`, `feeder_head_kva`, etc.
- Join keys: `circuit_folder + season + design (+ scenario)`

### Load voltages

The Phase 7 deploy places one mode=0 Monitor `vl_<load>` on every Load of the circuit (every phase leg, EV loads included) through `ModifiedCircuitData/Monitors_LoadVoltage.dss`. After the solve it reads them through the OpenDSS engine and writes three files to `ModifiedCircuitData/`. `v_pu` is the conductor voltage to ground divided by the line-to-neutral base voltage of the load's bus that OpenDSS reports. A bus with no base voltage takes the base from the load's `kV`: `kV` for a one-phase wye load, `kV / sqrt(3)` otherwise. Neutral and ground conductors (node 0) are left out. Steps run from 1 to the number of samples the monitors hold.

- `load_voltages.parquet`: one row per load, step and phase conductor. Columns `load`, `bus`, `step`, `conductor` (the node number), `v_volts`, `v_pu`, `ev_leg` (True for the EV loads the deploy adds, whose names start with `EVu_` or `EVc_`).
- `load_voltage_steps.csv`: one row per step, over customer loads only (`ev_leg` False). Columns `step`, `v_pu_min` and `v_pu_min_load` (lowest `v_pu` and its load), `v_pu_max` and `v_pu_max_load`, `n_below` and `n_above` (load conductors below `low_pu` and above `high_pu`).
- `load_voltage_loads.csv`: one row per load. Columns `load`, `bus`, `v_pu_min` and `v_pu_min_step`, `v_pu_max` and `v_pu_max_step`, `n_steps_outside` (steps at which any conductor of the load is outside the band), `ev_leg`.

Ties go to the first load by name or the first step. EV legs sit on their host's bus and repeat its voltage, so the step table and the summaries below count customer loads only.

### `load_voltage_summary.csv`

Phase 8 (`append_experiment_results.py`) writes it to `8_results_analysis/`, next to `aggregate_m2_combined.csv`. One row per circuit folder, from the customer loads (`ev_leg` False) of its `load_voltage_loads.csv`:

- `circuit_folder`
- `v_pu_min`, `v_pu_max`: the lowest and highest load `v_pu` of the day.
- `n_loads_below`: loads whose `v_pu_min` is below `low_pu`.
- `n_loads_above`: loads whose `v_pu_max` is above `high_pu`.
- `n_load_steps_outside`: the sum of `n_steps_outside` over the loads.

The band is `voltage_band` in `pipeline_config.yaml`: 0.95 to 1.05 per unit, ANSI C84.1 Range A at the service point, as described in NREL/TP-5D00-77156 (2021), section 2.2: https://www.nrel.gov/docs/fy21osti/77156.pdf. The source monitor m1 reads the source voltage setpoint, so it does not measure voltage along the feeder.

### EV car file

When a circuit has EV cars, the Phase 7 deploy writes `<circuit>/EVControl/ev_cars.csv`, beside `ModifiedCircuitData/`: one row per car, uncontrolled cars first. Phase 8 does not read it. Intervals are 1 to 96. With `horizon_days` above 1 the file holds each car's record on day X, as in the one-day run; `ev_car_days.csv` holds every day (see "The multi-day window" below).

- `car`: `EVu_<i>` or `EVc_<j>`, its shape in `LoadShapes_EV.dss`.
- `host`: the EV host load. `group`: `uncontrolled` or `controlled`.
- `ev_cars`: the `ev_cars` value. `level`: `L1` or `L2`.
- `power_kw`: the car's charging power: `level1_kw` or `level2_kw` of `ev_inputs.yaml`, or under `evwatts_sessions` a Level 2 car's session mean power (energy over charge duration).
- `charges_today`: whether the car charges on the simulated day.
- `source_id`: the EV WATTS `session_id`, or the NHTS `HOUSEID-VEHID`; empty for a car that does not charge under `evwatts_sessions` and for every car under `session_rows`.
- `day_class`: under `nhts_days`, the NHTS vehicle-day class: `i` (drove, with a home arrival and departure) or `ii` (did not drive).
- `window_source_id`: under `session_rows`, the NHTS `HOUSEID-VEHID` of a controlled car's window.
- `plug_in_interval`: the interval the car plugs in at home; empty without a window and for a whole-day window (NHTS class `ii`).
- `window_intervals`: the number of intervals of the plug-in window (96 for a whole day); empty without a window.
- `energy_kwh`: the energy the car needs: the session's energy, the miles driven times kWh per mile, or the check curve's daily energy.
- `first_interval`: the interval its uncontrolled charging starts (it can wrap past midnight); `n_intervals`: its non-zero intervals.
- `delivered_kwh`: the uncontrolled row's energy (sum / 4); `leftover_kwh`: `energy_kwh` minus `delivered_kwh`, the energy that does not fit in the window.
- `charging_share`: the share of cars charging under `evwatts_sessions` and `session_rows`, measured under `ev_day: typical` and 1 under `stress`; empty under `nhts_days`.
- `place`: `home` or `work`, where the car charges on the simulated day (README, "EV cars").
- `place_load`: the load whose bus carries the car's two EV loads: the host for a home car, the office (a commercial load of the circuit) for a work car.

When a circuit has EV cars, the deploy also writes `<circuit>/EVControl/ev_places.csv`: one row per car in the order of `ev_cars.csv`. It records where each car charges on the simulated day, not its commute. Columns `car`, `group`, `place` (`home` or `work`), `host` (the home host), `host_load` (the host's load whose bus carries EV loads: `<host>_1` when the host has two legs, else the host itself), `host_bus` (that load's bus, without phases), `host_lon` and `host_lat` (its coordinates from the feeder's `Buscoords.dss`), `place_load` (the host or the office), `place_leg`, `place_bus`, `place_lon` and `place_lat` (the same for the charging place), `energy_kwh`, `plug_in_interval` and `window_intervals` (as in `ev_cars.csv`). A bus missing from `Buscoords.dss` leaves its coordinate cells empty; the deploy prints how many.

The NHTS extracts `7_circuit_instantiation/data_ev_cars/<ST>_nhts2017_vehicle_days.csv` (tracked, written by `build_nhts_extract.py`) hold one row per weekday vehicle-day with the columns `HOUSEID`, `VEHID`, `TDAYDATE`, `TRAVDAY`, `WTHHFIN`, `day_class`, `arrival_min`, `departure_min`, `window_min`, `driver_miles`, `n_driver_trips`, `n_miles_missing`, `n_work_pieces`, `work_min` and `work_pieces`. The last three describe the vehicle's stays at work (trips ending at WHYTO 03): the number of pieces (0 when none), the minutes parked at work (empty when none) and the pieces in day order as `arrival:minutes` joined by `|` (for example `480:240|780:290`), which the work cars of `nhts_days` take as their window. `day_class` is `i` (drove, with a home arrival and departure), `ii` (did not drive), `iii` (drove, but none of its trips ends or none starts at home) or `iv` (a driver trip faster than `nhts_max_trip_speed_mph` of `ev_inputs.yaml`). The three window columns are filled for class `i` only. The deploy draws classes `i` and `ii`, or `i` only when every car charges; it never draws `iii` or `iv`. `nhts2017_extract.yaml` counts the rows per state and class.

### EV control files

When a circuit has controlled cars and `ev_control` is not `uncontrolled`, the Phase 7 deploy writes these files to `<circuit>/EVControl/`. Phase 8 does not read them.

- `ev_control_cars.csv`: one row per controlled car. Columns `car` (`EVc_<j>`, its shape in `LoadShapes_EV.dss`), `host`, `rule` (the `ev_control` value), `curve` (`feeder`, `feeder_fallback` for a car whose host has no single service transformer, or the transformer name; empty under `offpeak_start`), `energy_kw_intervals` (the sum of the car's session row, kW over 15-minute intervals), `n_intervals` (non-zero intervals of the controlled shape), `first_interval_uncontrolled` and `first_interval_controlled` (1 to 96; under `offpeak_start` the start interval, since charging can wrap past midnight), `max_kw_uncontrolled`, `max_kw_controlled`, `window_on` (whether the rule kept the car inside a plug-in window), `power_kw` (as in `ev_cars.csv`), `delivered_kwh_controlled` (the controlled shape's energy, sum / 4), `leftover_kwh_controlled` (the session row's energy minus the controlled shape's, in kWh), `placement_order` (1 to the number of controlled cars, the order the valley rules place the cars in, by plug-in time from 04:00; empty under `offpeak_start`), `start_offset_intervals` (under `offpeak_start`, the offset of the car's schedule time from the start of the cheap period, in 15-minute intervals; the car starts at the later of its schedule time and its plug-in, clamped into its window; empty for a car without an offset and under the valley rules), `place_load` (the load whose bus carries the car's EV loads: its host, or its office for a work car; `host` stays the home host, and under `valley_fill_transformer` `curve` is the service transformer of the place).
- `ev_control_curves.csv`, under the valley rules: one row per curve and step. Columns `curve` (`feeder` or a transformer name), `monitor` (`m2`, or `mt_<n>` in `base_solve/Monitors_Transformers.dss`), `step` (1 to 96 x `horizon_days`), `base_kw` (real power of the no-EV solve), `uncontrolled_ev_kw` (the uncontrolled cars on that curve), `controlled_ev_kw` (the controlled cars placed on it; every controlled car for `feeder`), `forecast_error_kw` (the aggregator's forecast error at that step: the forecast the cars were placed on is `base_kw + uncontrolled_ev_kw + forecast_error_kw`).
- `base_solve/`, under the valley rules: the `.dss` files and the monitor CSVs of the no-EV solve.

### PV and storage files

Phase 7b writes the PV and storage hosts into `<circuit>/scenario_assignments.json`: under `pv` and `storage`, the keys `seed`, `seed_offset` and `effective_seed`, `storage_hosts` (under `storage` only) and one entry per segment, `residential` and `commercial`, each with `perc` (the mix share), `enabled` (the `der_sizing` switch), `n_bases` (loads of the segment) and `hosts` (the host load names). `pv_targets` and `storage_targets` list every host, homes first.

The Phase 7 deploy writes `ModifiedCircuitData/der_hosts.csv`: one row per PV or storage host. Columns `base`, `segment`, `pv_host`, `storage_host`, `loadshape` (the host's first loadshape), `bldg_id`, `floor_area_ft2`, `stories`, `building_type`, `roof_floor_stories_m2` and `roof_metadata_m2` (the roof by both sources), `annual_use_kwh` (the baseline building's annual electricity), `annual_yield_kwh_per_kw` (the donor's solar file), `pv_rule`, `sizing_case`, `roof_area_source` and `coverage_rule` (as applied), `roof_used_m2`, `pv_cap_roof_kw` and `pv_cap_use_kw` (the two caps), `roof_binds`, `peak_kw` (under `peak_ratio`), `pv_kw` (Pmpp, DC), `pv_kva` (inverter), `storage_kw`, `storage_kwh`, `storage_kva` (sizes of the whole host, computed also where the host has only PV or only storage), `legs` (whether the units sit on the `_1` and `_2` legs) and `units` (objects per host). A host sized at 0 kW gets no object.

When a circuit has storage, the deploy writes `<circuit>/StorageControl/`. Phase 8 does not read it.

- `storage_curves.csv`: one row per view and step. Columns `view` (`feeder`, `transformer_<name>` or `building_<line>`, one view for the hosts a line feeds), `element` and `terminal` (what the view watches), `step` (1 to 96 x `horizon_days`), `measured_kw` (the measured curve), `forecast_error_kw` and `forecast_kw` (the curve the targets or schedules use).
- `storage_targets.csv`: one row per battery object. Columns `view`, `element`, `terminal`, `rule` (`storage_rule`), `view_kw` and `view_kwh` (the batteries of the view), `forecast_draw` (the random stream of the forecast), `kw_target` and `kw_target_low` (controller rules), `schedule_discharge_kwh` (under `schedule`, the battery's share of its host's scheduled discharge to the grid), `battery`, `host`, `segment`, `kw_rated`, `kwh_rated`, `start_pct` (the starting energy, percent of kWh: the start chosen under `schedule` with `schedule_start: best`, else `storage_start_pct`), and after the solve `charged_kwh` and `discharged_kwh` (from its state monitor), `stored_kwh_start` (`kwh_rated` x `start_pct` / 100), `stored_kwh_end` (the energy after step 96: the state monitor's last sample plus the last step's change), and `stored_kwh_min` and `stored_kwh_max` (over the monitor's samples and `stored_kwh_end`).
- `storage_schedule.csv`, under `schedule`: one row per host and step. Columns `view`, `host`, `loadshape` (`StoSched_<n>` in `Storage.dss`), `step`, `net_kw` (positive discharging, negative charging), `stored_kwh_start` and `stored_kwh_end` (the planned stored energy).
- `base_solve/` or `measure_solve/`: the `.dss` files and monitor CSVs of a solve run for the measured curves.

### The multi-day window

With `horizon_days` above 1 in `pipeline_config.yaml` every per-step output holds 96 x `horizon_days` steps, and these files and columns are added. With `horizon_days: 1` none of them is written and every file is as described above.

- `<circuit>/window_days.csv`: one row per day of the window. Columns `date` (YYYY-MM-DD on the 2018 calendar of the building curves), `weekday` (Monday to Sunday), `day_type` (`weekday` or `weekend`, from the date), `day_index` (1 for the first day), `day_x` (1 on the simulated peak day, else 0) and `holiday` (the name of a 2018 U.S. federal holiday, else empty; a holiday keeps the day type of its weekday).
- `date`, `day_index` and `day_type` follow the step column of `load_voltages.parquet`, `load_voltage_steps.csv`, `EVControl/ev_control_curves.csv`, `StorageControl/storage_curves.csv` and `StorageControl/storage_schedule.csv`, and follow `timestep` in the time-series rows of `aggregate_m1.csv`, `aggregate_m2.csv` and `aggregate_m2_combined.csv`.
- `day_x_first_step` and `day_x_last_step`: the steps of day X, in the summary rows of the aggregates and in `circuit_summary.csv` and `circuit_summary_combined.csv`.
- `EVControl/ev_control_curves.csv` also gets `forecast_kw`, the forecast the first placed car saw: the base and the uncontrolled cars plus the forecast error, each day with its own error under `ev_valley_day: own_day`, day X's forecast repeated under `peak_day`.
- `EVControl/ev_car_days.csv`: one row per car and day, the day before the window (`day_index` 0) and each day of the window. Columns `car`, `group`, `host`, `day_index`, `date`, `day_type` (the type of the sessions the car uses that day; day X is `weekday`), `day_x`, `charges` (whether the car has a drawn session that day), `event` (`session`, `top_up` or empty), `session_id` (the EV WATTS session or NHTS vehicle-day used), `place` (`home` or `work`) and `place_load`, `needed_kwh` (the session's energy on a charging day; for day 0 the part that lands in the window), `planned_kwh` (the car's charging on the run's steps before any control), `delivered_kwh` (the energy of its loadshape for that day's session or top-up; for a controlled car the controlled result), `topup_kwh` (`delivered_kwh` of a top-up), `tail_kwh` (energy that falls after the window's last step), `backlog_kwh` (energy that has not fitted in a window so far and waits for a top-up) and `owed_kwh` (`needed_kwh` less `delivered_kwh`, summed from day 0). Over a car, the sum of `needed_kwh` equals the sum of `delivered_kwh` plus the last day's `owed_kwh`.
- `LoadShapes_EV.dss` also holds `EVu_<i>h` and `EVc_<j>h`, the home rows of the work cars (their weekend days), on the loads `EVu_<host>_1` and `_2` (or `EVc_`). `ev_places.csv` keeps each car's place on day X.
- `StorageControl/storage_midnights.csv`: one row per battery object and day. Columns `battery`, `host`, `view`, `rule`, `day_index`, `date`, `day_type`, `kwh_rated`, `planned_kwh_end` (under `schedule`, the battery's share of its host's planned stored energy at the end of the day; empty under the other rules), `monitor_kwh_end` (the stored energy of the state monitor at the same step) and `drift_kwh` (monitor less planned).
- `storage_targets.csv` keeps one row per battery: `stored_kwh_start` and `stored_kwh_end` are those of the window, and `schedule_discharge_kwh` is the sum of the days' budgets.

The weekend NHTS extracts `7_circuit_instantiation/data_ev_cars/<ST>_nhts2017_vehicle_days_weekend.csv` (tracked, written by `build_nhts_extract.py --day-type weekend`) hold one row per Saturday or Sunday vehicle-day with the columns of the weekday extracts; `TRAVDAY` is `07` for a Saturday and `01` for a Sunday.

## 4.2 Visualization & Metrics

- **Peak demand tracking** (primary metric), with Tableau dashboards.  
- Power/Energy meters on the **main feeder meter** and **storage** units.  
- Voltage violations and other monitors may be exported separately depending on simulation options.

```{admonition} Example Joins (pandas)
:class: tip
Join `aggregate_m2_combined.csv` (summary rows) with `circuit_summary_combined.csv` on the composite key to add counts and device metadata to each scenario summary.
```
