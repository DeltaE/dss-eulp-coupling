# Phase 5 Technical Correctness Audit

Audit target: `feature/feeder-discovery` at `e0d4609`.

Scope note: this was a read-only technical audit of pipeline behavior. No source code was changed; this file records findings only.

## Summary

| Area | Rating | Result |
| --- | --- | --- |
| Task A: `scan_feeders.py` | WARNING | Current behavior matches the intended legacy parsing for actual NC data, but malformed `yearly` values with fewer than three underscore-separated parts would crash. |
| Task B: `generate_loads_pivot.py` | OK | Formula and Excel parity verified: 12,472 matching rows, 0 mismatches against the available matching workbook/source pair. |
| Task C: `scale_feeder_curves.py` | WARNING | Merge/groupby behavior is preserved. Missing registry feeders are silently omitted, so preflight validation is needed before the fire test. |
| Task D: hardcoded sweep | OK | No active fire-test feeder hardcodes found. Only safe examples/default downloader region strings were found. |
| Task E: Phase 6 hardcoded path | CRITICAL | Exact Phase 6 reactive-power behavior depends on a hardcoded, CWD-sensitive legacy parquet path. Do not skip Phase 6 for an exact correctness fire test. |

## Task A: `scan_feeders.py`

### A1. Load parsing fidelity

Rating: WARNING

Relevant code:

- `0_download_smartds/scan_feeders.py:53`: `parts = line.split()`
- `0_download_smartds/scan_feeders.py:61-79`: token-based extraction of `Load.load_`, `Phases=`, `kW=`, `kvar=`, `yearly=`
- `0_download_smartds/scan_feeders.py:62`: `part.split(".")[-1].replace('_1', '')`
- `0_download_smartds/scan_feeders.py:83-85`: `yearly.split("_")[0]` and `yearly.split("_")[2]`
- `0_download_smartds/scan_feeders.py:92-96`: `seen_loads` guard and append

Findings:

- `line.split()` parsing extracts the expected fields from actual NC `Loads.dss` lines. Example rural line:

```text
New Load.load_p1rlv1359_1 ... kW=3.9060227283575606 kvar=0.8578020352767629 Phases=1 yearly=res_kw_278_pu
```

- The aggressive `.replace('_1', '')` behavior is preserved. It removes all `_1` substrings, not just a trailing `_1`.
- Actual NC data did not expose a case where that aggressiveness changes a middle-of-name `_1`.

Validation counts:

```text
rural:          files=8,  load lines=12,042, aggressive mismatches=0
urban-suburban: files=61, load lines=118,142, aggressive mismatches=0
```

Here, "aggressive mismatch" means legacy `.replace('_1', '')` produced a different name than suffix-only removal of `_1$`.

- `seen_loads` prevents duplicate counting of exact post-replace load names within each feeder. No duplicate post-replace names were found:

```text
rural:          raw_load_lines=12,042, duplicate_post_replace_within_feeder=0
urban-suburban: raw_load_lines=118,142, duplicate_post_replace_within_feeder=0
```

- Important nuance: the code removes `_1` but not `_2`, so `load_p1ulv37_1` becomes `load_p1ulv37` while `load_p1ulv37_2` remains `load_p1ulv37_2`. That behavior matches the available parsed NC CSV and is consistent with the later single-phase `count / 2` correction.

Yearly edge cases:

- Actual NC `yearly` values are four-part strings such as `res_kw_278_pu` and `com_kw_12824_pu`. The code intentionally extracts part `0` as `res`/`com` and part `2` as the numeric ID, so this works for actual data.
- More than three parts works only if part `2` remains the numeric ID.
- Fewer than three parts would raise `IndexError` at `yearly.split("_")[2]`.
- Missing `yearly` is handled without crashing: `Yearly_Type` and `Yearly_Number` become `None`.

Correctness issue:

- WARNING: malformed `yearly` values with fewer than three underscore-separated parts would crash. Actual NC rural and urban-suburban data did not contain such rows.

### A2. Discovery order

Rating: OK

The generalized discovery logic:

```python
candidates = [p for p in root.rglob("Loads.dss")]
feeder_dirs = sorted(set(p.parent for p in candidates), key=lambda p: p.as_posix().lower())
```

was compared against the legacy pattern of sorted substations, then sorted feeders. For the NC layouts audited, the order is identical.

Rural run:

```text
Command used: scan_feeders.py with --smartds-root D:\lvg\GSO\rural\base_timeseries\opendss
Output written to temp: C:\Users\lfv1\AppData\Local\Temp\parsed_loads_NEW.csv
Scanned 8 feeders, found 12,042 unique loads
Order identical to sorted substation/feeders: True
```

Rural feeder order:

```text
rhs0_1247/rhs0_1247--rdt1527
rhs0_1247/rhs0_1247--rdt1534
rhs0_1247/rhs0_1247--rdt1948
rhs1_1247/rhs1_1247--rdt137
rhs2_1247/rhs2_1247--rdt1262
rhs2_1247/rhs2_1247--rdt1264
rhs3_1247/rhs3_1247--rdt2705
rhs3_1247/rhs3_1247--rdt2999
```

Urban-suburban check:

- The requested legacy file `D:\lvg\GSO\urban-suburban\base_timeseries\parsed_loads.csv` was not present.
- The repo-local `0_download_smartds/parsed_loads.csv` contains 61 urban-suburban feeders and follows the same sorted pattern:

```text
uhs0_1247/uhs0_1247--udt12274
uhs0_1247/uhs0_1247--udt14717
uhs0_1247/uhs0_1247--udt16115
uhs10_1247/uhs10_1247--udt11713
uhs10_1247/uhs10_1247--udt12084
uhs10_1247/uhs10_1247--udt13528
...
```

## Task B: `generate_loads_pivot.py`

### B1. `REAL_LOAD_COUNT` formula

Rating: OK

Verified in `0_download_smartds/generate_loads_pivot.py`:

- Groupby columns are exactly:

```python
["Feeder", "Phases", "Yearly_Type", "Yearly_Number"]
```

- Count target is exactly:

```python
["Load_Name"].count()
```

- Single-phase correction is:

```python
Count_of_Load_Name / 2 if Phases == 1 else Count_of_Load_Name
```

- Final cast is:

```python
.astype(int)
```

- Python truncation matches the intended Excel behavior:

```text
int(3/2) = 1
```

The available urban-suburban source had no odd single-phase count groups:

```text
one_phase_odd_count_groups = 0
```

### B2. Validation against Excel

Rating: OK

The specifically requested workbook path `5b_profile_generation/parsed_loads_PIVOT.xlsx` was not present. A matching workbook/source pair was available at:

- `0_download_smartds/parsed_loads.csv`
- `0_download_smartds/parsed_loads_PIVOT.xlsx`

Because these share the same urban-suburban source data, the comparison was valid.

Comparison result:

```text
xlsx_rows     = 12,472
new_rows      = 12,472
matching_rows = 12,472
mismatches    = 0
merge both    = 12,472
left_only     = 0
right_only    = 0
```

No `REAL_LOAD_COUNT` or `Count_of_Load_Name` mismatches were found.

## Task C: `scale_feeder_curves.py`

### C1. Merge logic preservation

Rating: OK

`5b_profile_generation/scale_feeder_curves.py` is a wrapper:

```python
runpy.run_path(str(Path(__file__).with_name("scale_feeder_curves_NC.py")), run_name="__main__")
```

The active implementation is `5b_profile_generation/scale_feeder_curves_NC.py`.

The merge and aggregation logic is preserved from the pre-registry version:

- Commercial merge:

```python
df_feeder.merge(df_commercial, left_on=["Parquet_Name"], right_on=["Chosen_Parquet"], how="left")
```

- Residential merge:

```python
df_feeder.merge(df_residential, left_on=["Parquet_Name"], right_on=["Chosen_Parquet"], how="left")
```

- Critical drop:

```python
dropna(subset=["bldg_id"])
```

- `Parquet_File` calculation:

```python
f"{int(bldg_id)}-0.parquet"
```

- Final groupby:

```python
["Feeder", "Parquet_Folder", "Parquet_File"]['REAL_LOAD_COUNT'].sum().reset_index()
```

The relevant diffs only changed:

- pivot input source from xlsx-only to CSV-first with xlsx fallback
- hardcoded feeder list to `load_feeder_registry()`
- `Parquet_Name` creation moved so it is skipped when already present in the generated CSV

No accidental merge key, join type, drop, `Parquet_File`, or groupby change was found.

### C2. State prefix propagation

Rating: OK

When `state = "TX"`, `STR_STATE = STATE`, so the script consistently uses:

```text
TX_final_commercial.csv
TX_final_residential.csv
TX_parquet_and_bldgs.csv
TX_required_parquets_per_feeder.csv
parquet_commercial_<date>_comm_TX
parquet_residential_short_<date>_TX
```

No mixed bare/`TX_` output naming was found in this script.

### C3. Feeder filtering

Rating: WARNING

Verified behavior:

- `relevant_feeders` comes from `registry["feeders"][*]["feeder_name"]`.
- `df_summary` is filtered before any merge:

```python
df_filtered = df_summary[df_summary["Feeder"].isin(relevant_feeders)].copy()
```

- The loop then processes feeders in registry order:

```python
for feeder in relevant_feeders:
    df_feeder = df_filtered[df_filtered["Feeder"] == feeder].copy()
```

Missing registry feeder behavior:

- If one registry feeder is absent from `df_summary`, that feeder gets an empty `df_feeder`.
- The downstream merges produce empty frames and the script continues.
- This is graceful in the "no exception" sense, but it is silent and can omit a feeder from the output without failing the fire test.

Additional readiness note:

- No root `feeder_registry.json` is currently present in the working tree. `scale_feeder_curves_NC.py` will require Phase 0/2 staging to create or supply it before execution.

Correctness issue:

- WARNING: before the fire test, validate that every registry feeder appears in `parsed_loads_SUMMARY.csv`. Silent omission would be hard to detect downstream.

## Task D: Hardcoded value sweep

Rating: OK

Commands requested were run with `rg` equivalents across all `*.py`.

### Pattern: `uhs`

```text
No hits.
```

### Pattern: `1247`

```text
No hits.
```

### Pattern: `startswith.*uhs`

```text
No hits.
```

### Pattern: `GSO|Greensboro|AUS|Austin`

Hits:

```text
5c_csv_conversion\parquet_to_csv.py-132-    for n in range(len(df_filtered.index.tolist())):
5c_csv_conversion\parquet_to_csv.py-133-        '''
5c_csv_conversion\parquet_to_csv.py:134:        THIS IS COMMENTED BECAUSE THERE WAS AN ERROR WHEN THIS FOR LOOP HAD
5c_csv_conversion\parquet_to_csv.py-135-        THE FOLLOWING: *for parquet_file in parquet_files* DEFINITION.
5c_csv_conversion\parquet_to_csv.py-136-
```

Classification: SAFE. False-positive substring match: `AUS` inside `BECAUSE`, in a comment block.

```text
0_download_smartds\download_smartds.py-28-DEFAULT_YEAR = 2018
0_download_smartds\download_smartds.py-29-DEFAULT_SCENARIOS = ("base_timeseries", "solar_high_batteries_high_timeseries")
0_download_smartds\download_smartds.py:30:DEFAULT_REGIONS = ("SFO", "AUS", "GSO")
0_download_smartds\download_smartds.py-31-DEFAULT_OUTPUT_DIR = REPO_ROOT / "0_download_smartds" / "data_raw" / "smartds"
0_download_smartds\download_smartds.py-32-DEFAULT_SUFFIXES = {
```

Classification: SAFE. Active downloader default, but not a hardcoded feeder/circuit selection and not part of the Phase 5 fire-test path unless the optional downloader is run without explicit regions.

```text
0_download_smartds\download_smartds.py-345-    parser = argparse.ArgumentParser(description=__doc__)
0_download_smartds\download_smartds.py-346-    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
0_download_smartds\download_smartds.py:347:    parser.add_argument("--regions", nargs="+", default=list(DEFAULT_REGIONS), help="SMART-DS regions such as SFO AUS GSO.")
0_download_smartds\download_smartds.py-348-    parser.add_argument("--subregions", nargs="+", help="Optional subregion filter, e.g. P21U rural urban-suburban.")
0_download_smartds\download_smartds.py-349-    parser.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
```

Classification: SAFE. CLI help/example text.

### Pattern: `circuit_61`

```text
No hits.
```

### Pattern: `urban.suburban`

Hit:

```text
0_download_smartds\download_smartds.py-346-    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
0_download_smartds\download_smartds.py-347-    parser.add_argument("--regions", nargs="+", default=list(DEFAULT_REGIONS), help="SMART-DS regions such as SFO AUS GSO.")
0_download_smartds\download_smartds.py:348:    parser.add_argument("--subregions", nargs="+", help="Optional subregion filter, e.g. P21U rural urban-suburban.")
0_download_smartds\download_smartds.py-349-    parser.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
0_download_smartds\download_smartds.py-350-    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
```

Classification: SAFE. CLI help/example text.

No LEGACY or RISK hardcoded-value hits were found in active fire-test code paths.

## Task E: Phase 6 hardcoded path

Rating: CRITICAL

File: `6_kvar_preparation/rev_spec_kvar_kw_ratio.py`

Hardcoded path:

```python
EXTERNAL_FOLDER_STR = '3b_smartds_eulp_match'
original_parquet_dir = Path('..') / EXTERNAL_FOLDER_STR / "parquet_data"
```

What it points to:

- A legacy folder named `3b_smartds_eulp_match/parquet_data`.
- The script expects original source parquets there with these columns:

```text
Time
total_site_electricity_kw
total_site_electricity_kvar
```

- Those parquets are used to compute `kvar_ratios.pkl`, which `generate_kvar_csvs.py` later applies to create `_kvar_` CSV loadshapes from `_kw_` CSV loadshapes.

Important path behavior:

- The path is relative to the current working directory, not to the script file.
- Under the documented `pushd 6_kvar_preparation` workflow, it resolves to:

```text
D:\github\dss-eulp-coupling\3b_smartds_eulp_match\parquet_data
```

Fire-test impact:

- Phase 7 has a flat-ones fallback if kW/kvar CSVs are missing, so a minimal smoke test may proceed without Phase 6.
- That fallback is not exact reactive-power behavior. For this audit's stated goal of preserving exact computational behavior, Phase 6 should not be skipped.
- If the exact fire test includes Phase 6, this hardcoded path is a blocker unless the expected directory is staged/symlinked with the correct parquets.

Correctness issue:

- CRITICAL: exact fire-test behavior depends on satisfying or replacing this hardcoded Phase 6 source-parquet path.

## Issues To Address Before Fire Test

1. CRITICAL: Provide the expected Phase 6 source parquet directory at `6_kvar_preparation\..\3b_smartds_eulp_match\parquet_data` or parameterize `rev_spec_kvar_kw_ratio.py` before an exact reactive-power fire test.
2. WARNING: Add or run a preflight check that every `feeder_registry.json` feeder appears in `parsed_loads_SUMMARY.csv`; the current scale step silently omits missing feeders.
3. WARNING: `scan_feeders.py` will crash on malformed `yearly` strings with fewer than three underscore-separated parts. Actual NC data audited here is clean, so this is not blocking for the current NC fire test.

