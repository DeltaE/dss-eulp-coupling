# 1. Introduction

## 1.1 Project Overview

**DSS XLRM** is a Distribution System Simulation (DSS) framework that applies the **DMDU** (Decision Making Under Deep Uncertainty) paradigm to distribution system planning.

- **X (Uncertainties):** Load characteristics, EV adoption, heat pump deployment, DER penetration (PV/storage).
- **L (Levers):** Storage control (e.g., peak shaving), demand management programs.
- **R (Relationships):** OpenDSS-based network models, EULP building profiles, Smart-DS feeders.
- **M (Metrics):** Peak demand, voltage, power/energy flows and derived reliability/quality indicators.

### Research Context

- Audience: **Researchers**, planners, and utilities (PhD research).
- Objective: **Distribution system planning** under deep uncertainty using ensembles on realistic feeders.
- Datasets: **SMART-DS** (North Carolina, Texas, California), with circuits with connection issues filtered out.
- Profiles/Data: **NREL EULP** (via OEDI, open access).

### Capabilities

- Experimental designs via **Latin Hypercube Sampling (LHS)** and **Sobol sequences**.
- Seasonal analysis (**summer/winter**) and multiple profile variants (baseline, demand management, uncontrolled).
- EV/PV/Storage placement & control, per-feeder time-series simulation (96×15-min timesteps).

## 1.2 System Architecture

```{mermaid}
flowchart TD
    A[DOE: LHS/Sobol] --> B[Scenario Dictionaries<br/>mixes_lhs.json / mixes_sobol.json]
    B --> C[Smart-DS ↔ EULP Matching]
    C --> D[Profile Generation<br/>baseline / DM / uncontrolled]
    D --> E[Reactive Power Prep<br/>kvar ratios]
    E --> F[Circuit Instantiation & Simulation]
    F --> G[Results Aggregation]
    G --> H[Visualization & Analysis<br/>Tableau / notebooks]
```
