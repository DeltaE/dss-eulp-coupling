# 3. Workflow Guide

This section describes the end-to-end workflow and provides runnable commands you can adapt.

```{admonition} Quick Start
:class: important
Adjust paths, states, and design variants as needed. Example commands assume your repo layout matches the folders below.
```

## 3.1 Repository Layout

```
dss_xlrm/
├── 0_code_xlrm/           # Experimental design generation
├── 1b_smartds_eulp_match/ # Circuit-building matching
├── 1c_eulp_downloads/     # EULP data acquisition
├── 2_profiles_heat_pumps/ # Profile generation (baseline)
├── 3_kvar_kw_prep/        # Reactive power ratios
├── 4_profiles_heat_pumps_dm/  # Demand management profiles
├── 5_profiles_heat_pumps_un/  # Uncontrolled profiles
├── 6_instantiate_circuits_*/  # Instantiation & simulation
└── 7_results_analysis/    # Aggregation & analysis
```

## 3.2 Phase-by-Phase

### Phase 1 — Experimental Design (0_code_xlrm)
- Generate scenario dictionaries using DOE (LHS/Sobol). `N_CASES` controls scenario count.
- **Key script:** `run_mix_generator.py`
- **Outputs:** `mixes_lhs.json`, `mixes_sobol.json`

```bash
cd 0_code_xlrm
python run_mix_generator.py
```

### Phase 2 — Circuit ↔ Building Matching (1b_smartds_eulp_match)

**Sequential scripts:**
1. `copy_circuits.py` — Copy Smart-DS circuits to working dir  
2. `circuit_make_daily_list_sets.py` — Extract daily load patterns  
3. `review_parquet_matches.py` — Review available parquet files  
4. `match_smartds_parquets_NC.py` — Match circuits to EULP profiles  
5. `clean_up_bldgs_NC.py` — Filter/organize building data  
6. `select_rep_family_NC.py` — Select representative buildings

```bash
cd ../1b_smartds_eulp_match
python copy_circuits.py
python circuit_make_daily_list_sets.py
python review_parquet_matches.py
python match_smartds_parquets_NC.py
python clean_up_bldgs_NC.py
python select_rep_family_NC.py
```

### Phase 3 — Data Acquisition (1c_eulp_downloads)
Download EULP parquet files from OEDI (open access).

```bash
cd ../1c_eulp_downloads
python download_parquets_homes_NC.py
python download_parquets_commercial_NC.py
```

### Phase 4 — Profile Generation (2/4/5 profiles)
Variants: **baseline** (`2_profiles_heat_pumps`), **demand management** (`4_profiles_heat_pumps_dm`), **uncontrolled** (`5_profiles_heat_pumps_un`).

**Typical workflow:**
```bash
cd ../2_profiles_heat_pumps
python scale_feeder_curves_NC.py
python find_max_day_curve_NC.py
python plot_parquet_differences.py
python get_scenario_csv_controls.py
```

### Phase 5 — Reactive Power Preparation (3_kvar_kw_prep)
Run the longer job to build reactive power ratios (kVAr/kW).

```bash
cd ../3_kvar_kw_prep
python rev_spec_kvar_kw_ratio.py   # ~579 minutes for full dataset
```

### Phase 6 — Circuit Instantiation & Simulation (6_instantiate_circuits_*)
Create circuit instances, assign DERs, and run power flow simulations.

- **Main script:** `instantiate_circuits_and_runs_APPLYFILTER.py`
- **Runner:** `power_flow_sim_daily_EV_STO_DG_deploy.py`
- **Features:** EV assignments (controlled/uncontrolled), PV/storage placement, heat pump profiles (baseline/DM/uncontrolled)

```bash
cd ../6_instantiate_circuits_summer_lhs   # example path; adjust for season/design
python instantiate_circuits_and_runs_APPLYFILTER.py
python power_flow_sim_daily_EV_STO_DG_deploy.py
```

### Phase 7 — Results Analysis (7_results_analysis)
Aggregate across scenarios, seasons, and DOE designs.

```bash
cd ../7_results_analysis
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
