# 5. Examples

## 5.1 Peak and Storage by Circuit

Every scenario of `0_experimental_design/mixes_fixed.yaml` places batteries, `baseline` included, so the outputs of the README cases hold no run without storage. `n_storage` sits on the summary rows only.

```python
import pandas as pd

ts = pd.read_csv("aggregate_m2_combined.csv")
ts_data = ts[ts["row_type"] == "data"]
summary = ts[ts["row_type"] == "summary"]

n_storage = summary.set_index("circuit_folder")["n_storage"]
peak = ts_data.groupby("circuit_folder")["P_3ph (kW)"].max()

print(pd.concat([n_storage, peak], axis=1))
```

## 5.2 NC vs TX Donor (by circuit)

`design` holds the donor state. `m2_all_cases_all_seasons.csv` holds both donors of each feeder.

```python
df = pd.read_csv("m2_all_cases_all_seasons.csv")
c1 = df[(df["circuit_folder"] == "uhs13_1247_circuit_1_mixed") & (df["row_type"] == "data")]

nc = c1[c1["design"] == "NC"]
tx = c1[c1["design"] == "TX"]

nc_peak = nc.groupby("season")["P_3ph (kW)"].max()
tx_peak = tx.groupby("season")["P_3ph (kW)"].max()

print(nc_peak)
print(tx_peak)
```

## 5.3 Joining Time Series and Metadata

```python
import pandas as pd

agg = pd.read_csv("aggregate_m2_combined.csv")
meta = pd.read_csv("circuit_summary_combined.csv")

# Example: select summary rows from agg (if present) and join
is_summary = agg["row_type"] == "summary"
summary = agg[is_summary].copy()

key_cols = ["circuit_folder", "season", "design", "scenario"]
joined = summary.merge(meta, on=key_cols, how="left", suffixes=("", "_meta"))
print(joined.head())
```
