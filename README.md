# DSS-EULP Coupling Pipeline

> **Open-data coupling of SMART-DS synthetic distribution feeders with NREL End-Use Load Profiles (EULP) for distribution system planning under uncertainty.**

[![Documentation Status](https://readthedocs.org/projects/dss-dmdu/badge/?version=latest)](https://dss-dmdu.readthedocs.io/en/latest/?badge=latest)

## Overview

This repository contains the reproducible pipeline for coupling [SMART-DS](https://data.openei.org/submissions/2981) synthetic distribution feeders with [End-Use Load Profiles (EULP)](https://data.openei.org/submissions/4520) from NREL's Open Energy Data Initiative.

**Companion paper:** Víctor-Gallardo, L., et al. "Open-Data Coupling of Synthetic Distribution Feeders with End-Use Load Profiles for Distribution System Planning Under Uncertainty." *MethodsX* (submitted).

## Pipeline Phases

| Phase | Folder | Description |
|-------|--------|-------------|
| 1 | `1_experimental_design/` | LHS/Sobol scenario generation |
| 2 | `2_circuit_matching/` | Feeder flattening + load shape extraction |
| 3 | `3_tolerance_matching/` | Building-to-circuit peak demand matching |
| 4 | `4_quota_assignment/` | Income-stratified building assignment |
| 5a | `5a_eulp_downloads/` | EULP parquet acquisition from OEDI S3 |
| 5b | `5b_profile_generation/` | Peak day identification + daily slicing |
| 5c | `5c_csv_conversion/` | Parquet → CSV for OpenDSS loadshapes |
| 6 | `6_kvar_preparation/` | Reactive power ratio extraction |
| 7 | `7_circuit_instantiation/` | DER deployment + OpenDSS simulation |

## Quick Start

```bash
# 1. Clone this repo
git clone https://github.com/DeltaE/dss-eulp-coupling.git
cd dss-eulp-coupling

# 2. Create environment (conda recommended)
conda create -n dss_eulp python=3.9 -y
conda activate dss_eulp
pip install pandas numpy pyarrow matplotlib

# 3. Follow phase-by-phase instructions in each folder's README
```

## Data Requirements

- **SMART-DS feeders**: Download from [OEDI](https://data.openei.org/submissions/2981) (NC, TX, CA, or SFO regions)
- **EULP profiles**: Downloaded automatically by scripts in `5a_eulp_downloads/`
- **EULP metadata**: `residential_data_SELECT_STATES.csv` and `commercial_data_SELECT_STATES.csv` from OEDI

## Companion Repositories

- **Analysis repo** (DMDU/PRIM): [j-uncertainty-grid-modernisation](https://github.com/DeltaE/j-uncertainty-grid-modernisation)
- **Documentation**: [dss-dmdu.readthedocs.io](https://dss-dmdu.readthedocs.io)

## Citation

If you use this pipeline, please cite:

```bibtex
@article{victorgallardo2026coupling,
  title={Open-Data Coupling of Synthetic Distribution Feeders with End-Use Load Profiles 
         for Distribution System Planning Under Uncertainty},
  author={V{\'i}ctor-Gallardo, Luis and [co-authors] and Niet, Taco},
  journal={MethodsX},
  year={2026},
  note={Submitted}
}
```

## License

[To be determined — suggest MIT or CC-BY-4.0]

## Developed by

**Luis Víctor-Gallardo** — [Delta-E+](https://delta-e.sfu.ca/) / School of Sustainable Energy Engineering, Simon Fraser University
