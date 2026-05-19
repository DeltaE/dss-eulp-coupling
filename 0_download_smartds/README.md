# SMART-DS Download Stage

This stage captures the legacy `D:\lvg` SMART-DS download workflow in a
repo-local, command-line form. The original local scripts used the OpenEI S3
viewer with Selenium; these scripts use the public OEDI S3 object listing
directly so runs can be scripted and resumed more easily.

The source dataset is SMART-DS v1.0 on the OEDI data lake:

```text
s3://oedi-data-lake/SMART-DS/v1.0/
```

## Download SMART-DS Data

Dry-run one small slice first:

```powershell
python .\0_download_smartds\download_smartds.py `
  --regions GSO `
  --subregions rural `
  --scenarios base_timeseries `
  --output-dir .\0_download_smartds\data_raw\smartds `
  --dry-run
```

Download the default legacy subset for all three regions:

```powershell
python .\0_download_smartds\download_smartds.py `
  --regions SFO AUS GSO `
  --output-dir .\0_download_smartds\data_raw\smartds
```

The default scenario subset matches the `D:\lvg` workflow:

- `base_timeseries`
- `solar_high_batteries_high_timeseries`

By default the script downloads:

- OpenDSS `.dss` files under each scenario's `opendss/`
- SMART-DS analysis `.csv` files under `opendss/**/analysis/`
- `profiles/` CSVs as `profiles_data/`
- `solar_data/` CSVs as `solar_data/`
- `load_data/` parquets as `parquet_data/`

Use `--only-opendss` when you only need circuit definitions.

## Stage Plain Circuits

To copy discovered OpenDSS feeder folders into the legacy-style plain circuit
folder:

```powershell
python .\0_download_smartds\stage_circuits_plain.py `
  --smartds-root .\0_download_smartds\data_raw\smartds `
  --target .\ab_3b\circuits_plain_format `
  --registry .\ab_3b\feeder_registry.json
```

The staging script discovers feeder folders by looking for both `Loads.dss` and
`LoadShapes.dss`, then copies each feeder into a flat folder. Name collisions are
resolved with suffixes like `__2`.

## Data Hygiene

The downloaded and staged circuit data can be hundreds of gigabytes. The repo
ignores the default data folders:

- `0_download_smartds/data_raw/`
- `ab_3b/circuits_plain_format/`
