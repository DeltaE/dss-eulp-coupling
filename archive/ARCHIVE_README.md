# Archive: Multi-State EULP x SMART-DS Coupling Results

Pipeline output artifacts for multiple US states, demonstrating that the
SMART-DS x EULP coupling pipeline generalises beyond the primary North
Carolina validation site.

## Province to State Mapping

| Province | State | Abbr |
|----------|-------|------|
| British Columbia | Washington | WA |
| Ontario | Michigan | MI |
| Quebec | Vermont | VT |
| Alberta | Montana | MT |

## States Archived

- **MI**: stages 3b, 3c_downloads, 4_profhp, 5_kvar, 6_profhp_dm, 7_profhp_un, 8_summer, 8_winter
- **MT**: stages 3b, 3c_downloads, 4_profhp, 5_kvar, 6_profhp_dm, 7_profhp_un, 8_summer, 8_winter
- **VT**: stages 3b, 3c_downloads, 4_profhp, 5_kvar, 6_profhp_dm, 7_profhp_un, 8_summer, 8_winter
- **WA**: stages 3b, 3c_downloads, 4_profhp, 5_kvar, 6_profhp_dm, 7_profhp_un, 8_summer, 8_winter

## Pipeline Stages

| Stage | Description |
|-------|-------------|
| `3b` | Building-type matching (residential + commercial CSVs) |
| `3c_downloads` | EULP download manifests and scripts |
| `4_profhp` | Baseline load profile assignment |
| `5_kvar` | Reactive power (kVAr) preparation |
| `6_profhp_dm` | Demand-managed profile variant |
| `7_profhp_un` | Uncontrolled profile variant |
| `8_summer` | OpenDSS summer simulation results |
| `8_winter` | OpenDSS winter simulation results |

## What Is Included

- **CSV manifests**: matching tables, parquet inventories, circuit summaries
- **Python scripts**: pipeline stage scripts for each state
- **Run logs**: `run_log.txt` with ok/fail counts per simulation batch
- **Convergence reports**: `circuit_check_report.csv` with per-feeder status
- **Small utility folders**: scenario controls, deployer modules, etc.
- **Sample circuits**: a few per-feeder result directories per state
- **SMART-DS structure**: feeder directory hierarchy (`.dss` files excluded)

## What Is Excluded

Large data directories are stubbed with `.gitkeep` placeholders:

- `*.dss` : OpenDSS circuit models (regenerate via stage 7)
- `*.parquet` / `*.pq` : EULP load profile data (download via NREL OEDI)
- `*.pkl` : intermediate pickle files
- Per-feeder bulk directories (>30 files) : stubbed with `.gitkeep`
- Per-circuit directories beyond the sample cap : stubbed with `.gitkeep`
- `parquet_data/`, `daily_parquets/`, `daily_csvs/` : bulk data dirs

## Reproduction

1. Clone this repository and follow the root `README.md`
2. Run pipeline stages 1-7 with the desired state configuration
3. Simulation outputs appear in `8_summer/` and `8_winter/`

## Data Provenance

Processed during the EMH 2025 multi-state simulation campaign
(174 circuit-season configurations, 116 successful runs across four US
states).  See `emh_2025_variant_and_matching_inventory.md` for inventory.
