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

- Fields: `n_loads`, `n_evs`, `n_storage`, `n_pv`, `substation_xfmr_kva`, etc.  
- Join keys: `circuit_folder + season + design (+ scenario)`

## 4.2 Visualization & Metrics

- **Peak demand tracking** (primary metric), with Tableau dashboards.  
- Power/Energy meters on the **main feeder meter** and **storage** units.  
- Voltage violations and other monitors may be exported separately depending on simulation options.

```{admonition} Example Joins (pandas)
:class: tip
Join `aggregate_m2_combined.csv` (summary rows) with `circuit_summary_combined.csv` on the composite key to add counts and device metadata to each scenario summary.
```
