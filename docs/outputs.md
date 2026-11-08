# 4. Outputs & Interpretation

## 4.1 Primary Files

### `aggregate_m2_combined.csv`
A feeder‑level **time series** of power flows plus a one‑line metadata “summary” row for each circuit/scenario/season/design.

- **Total rows:** ~143,366  
- **Time‑series rows:** 141,888 (96 timesteps per circuit/season/design/scenario)

**Selected columns (typical):**

- Per-phase apparent/real/reactive: `S1-3 (kVA)`, `P1-3 (kW)`, `Q1-3 (kVAr)`, `Ang1-3 (deg)`  
- Three-phase totals: `P_3ph (kW)`, `Q_3ph (kVAr)`, `S_3ph (kVA)`, `S_sum_3ph (kVA)`  
- Keys to join with summary: `circuit_folder`, `season`, `design`, `scenario`

**Usage patterns:**

- **Peak demand:** `max(P_3ph)` across 96 timesteps  
- **Energy:** trapezoidal integration over `P_3ph`  
- **Imbalance:** `S_sum_3ph - S_3ph` as a simple metric

### `circuit_summary_combined.csv`
One row per circuit/scenario/season/design—metadata to contextualize the time series.

- Fields: `n_loads`, `n_evs`, `n_storage`, `n_pv`, `feeder_head_kva`, etc.  
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

### EV control files

When a circuit has controlled cars and `ev_control` is not `uncontrolled`, the Phase 7 deploy writes `<circuit>/EVControl/`, beside `ModifiedCircuitData/`. Phase 8 does not read it.

- `ev_control_cars.csv`: one row per controlled car. Columns `car` (`EVc_<j>`, its shape in `LoadShapes_EV.dss`), `host`, `rule` (the `ev_control` value), `curve` (`feeder`, `feeder_fallback` for a car whose host has no single service transformer, or the transformer name; empty under `offpeak_start`), `energy_kw_intervals` (the sum of the car's session row, kW over 15-minute intervals), `n_intervals` (non-zero intervals of the controlled shape), `first_interval_uncontrolled` and `first_interval_controlled` (1 to 96; under `offpeak_start` the start interval, since charging can wrap past midnight), `max_kw_uncontrolled`, `max_kw_controlled`.
- `ev_control_curves.csv`, under the two valley rules: one row per curve and step. Columns `curve` (`feeder` or a transformer name), `monitor` (`m2`, or `mt_<n>` in `base_solve/Monitors_Transformers.dss`), `step` (1 to 96), `base_kw` (real power of the no-EV solve), `uncontrolled_ev_kw` (the uncontrolled cars on that curve), `controlled_ev_kw` (the controlled cars placed on it; every controlled car for `feeder`).
- `base_solve/`, under the two valley rules: the `.dss` files and the monitor CSVs of the no-EV solve.

## 4.2 Visualization & Metrics

- **Peak demand tracking** (primary metric), with Tableau dashboards.  
- Power/Energy meters on the **main feeder meter** and **storage** units.  
- Voltage violations and other monitors may be exported separately depending on simulation options.

```{admonition} Example Joins (pandas)
:class: tip
Join `aggregate_m2_combined.csv` (summary rows) with `circuit_summary_combined.csv` on the composite key to add counts and device metadata to each scenario summary.
```
