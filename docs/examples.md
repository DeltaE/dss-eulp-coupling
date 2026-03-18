# 5. Examples

## 5.1 Peak Reduction from Storage

```python
import pandas as pd

ts = pd.read_csv("aggregate_m2_combined.csv")
ts_data = ts[ts["row_type"] == "data"]

# Quick split (example logic)
with_storage = ts_data[ts_data["n_storage"] > 0]
baseline     = ts_data[ts_data["n_storage"] == 0]

peak_baseline = baseline.groupby("circuit_folder")["P_3ph (kW)"].max()
peak_storage  = with_storage.groupby("circuit_folder")["P_3ph (kW)"].max()

peak_reduction = (peak_baseline - peak_storage).dropna()
print(peak_reduction.describe())
```

## 5.2 LHS vs Sobol Coverage (by circuit)

```python
df = pd.read_csv("aggregate_m2_combined.csv")
c52 = df[df["circuit_folder"] == "uhs17_1247_circuit_52"]

lhs = c52[c52["design"].str.contains("lhs", case=False, na=False)]
sob = c52[c52["design"].str.contains("sobol", case=False, na=False)]

lhs_peak = lhs.groupby("scenario")["P_3ph (kW)"].max()
sob_peak = sob.groupby("scenario")["P_3ph (kW)"].max()

print(lhs_peak.describe())
print(sob_peak.describe())
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
