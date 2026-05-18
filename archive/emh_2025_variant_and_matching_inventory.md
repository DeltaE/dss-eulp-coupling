# EMH 2025 Ottawa - Variant Meaning & Building-Matching Inventory

**Generated:** 2026-04-14  
**Directory:** `dist/`

---

## QUESTION 1: VARIANT MEANING

### Method

Compared `scenario_assignments.json` across variants 0, 1, and 2 for circuits 52 and 53 (both `uhs17_1247`) in `on_8_winter/` (MI).

### Summary

The three variants represent **three distinct DER penetration scenarios**:

| Variant | Label | EV % | Storage % | PV % | EV Control Split | Seed |
|---------|-------|------|-----------|------|------------------|------|
| **0** | High-EV stress test | 99% | 1% | 1% | 99% uncontrolled | 555 |
| **1** | Randomized LHS draw | ~99% | ~49% | ~24% | ~80% controlled | 777 |
| **2** | Low/baseline | 1% | 1% | 1% | 99% uncontrolled | 555 |

**What changes between variants:**

1. **DER penetration percentages** -- primary differentiator. Variant 0 = high EV only; variant 1 = mixed high DERs from an LHS sample; variant 2 = near-zero baseline.
2. **Controlled/uncontrolled EV split** -- variant 0 is 99% uncontrolled (worst-case grid stress); variant 1 flips to ~80% controlled (demand-managed); variant 2 is 99% uncontrolled but with negligible EV count.
3. **Random seed** -- variant 1 uses seed 777 (different load assignments); variants 0 and 2 share seed 555.
4. **Resulting load counts** change as a consequence of the above parameters.

> **Interpretation:** Variant 0 tests worst-case uncontrolled EV saturation. Variant 1 tests a realistic mixed-DER future with demand management. Variant 2 provides a near-zero baseline for delta calculations. MI and VT include all 3 variants; MT and WA include only variants 0 and 1.

### Side-by-Side: Circuit 52 (`uhs17_1247_circuit_52`)

| Parameter | Variant 0 | Variant 1 | Variant 2 |
|-----------|-----------|-----------|-----------|
| `ev.perc` | 0.99 | 0.9898 | 0.01 |
| `ev.lvl2_perc` | 0.99 | 0.9898 | 0.01 |
| `ev_split.controlled` | 0.01 | 0.7972 | 0.01 |
| `ev_split.uncontrolled` | 0.99 | 0.2028 | 0.99 |
| `storage.perc_3ph` | 0.01 | 0.4919 | 0.01 |
| `pv.perc_3ph` | 0.01 | 0.2408 | 0.01 |
| `disjoint_sets` | false | false | false |
| Seeds (ev, storage, pv) | 555 | 777 | 555 |
| EV loads (uncontrolled) | 2,170 | 444 | 21 |
| EV loads (controlled) | 22 | 1,747 | 1 |
| **EV loads (total)** | **2,192** | **2,191** | **22** |
| Storage targets | 1 | 35 | 1 |
| PV targets | 1 | 17 | 1 |

### Side-by-Side: Circuit 53 (`uhs17_1247_circuit_53`)

| Parameter | Variant 0 | Variant 1 | Variant 2 |
|-----------|-----------|-----------|-----------|
| `ev.perc` | 0.99 | 0.9898 | 0.01 |
| `ev.lvl2_perc` | 0.99 | 0.9898 | 0.01 |
| `ev_split.controlled` | 0.01 | 0.7972 | 0.01 |
| `ev_split.uncontrolled` | 0.99 | 0.2028 | 0.99 |
| `storage.perc_3ph` | 0.01 | 0.4919 | 0.01 |
| `pv.perc_3ph` | 0.01 | 0.2408 | 0.01 |
| `disjoint_sets` | false | false | false |
| Seeds (ev, storage, pv) | 555 | 777 | 555 |
| EV loads (uncontrolled) | 818 | 167 | 7 |
| EV loads (controlled) | 8 | 659 | 1 |
| **EV loads (total)** | **826** | **826** | **8** |
| Storage targets | 1 | 45 | 1 |
| PV targets | 1 | 22 | 1 |

> **Note:** Variants 0 and 1 have nearly identical total EV counts (both ~99% ev.perc) but distribute them very differently between controlled and uncontrolled. Variant 2 has far fewer total EVs (1% ev.perc).

---

## QUESTION 2: BUILDING-MATCHING RATES

### Method

Analyzed `*_3b/` directories for all 4 states. The matching pipeline has 3 stages:

1. **`match_smartds_parquets_XX.py`** -- Matches SMART-DS loads to EULP buildings via monthly-peak tolerance escalation
2. **`clean_up_bldgs_XX.py`** -- Filters EULP data to matched building IDs
3. **`select_rep_family_XX.py`** -- Selects one representative building per load (stratified by type)

### Input: SMART-DS Loads (identical across all 4 states)

- **883 commercial** load profiles (parquets like `com_12774.parquet`)
- **519 residential** load profiles (parquets like `res_100.parquet`)
- **1,402 total SMART-DS loads** to match
- Source file: `review_parquet_matches.csv` (identical in all 4 `*_3b/` dirs)

### EULP Building Pool Per State

| State | Commercial | Residential | Res-High | Res-Mid | Res-Low | Res-N/A |
|-------|-----------|-------------|----------|---------|---------|---------|
| MT (AB) | 499 | 1,238 | 418 | 254 | 538 | 28 |
| WA (BC) | 1,537 | 7,550 | 3,066 | 1,676 | 2,720 | 88 |
| MI (ON) | 2,654 | 8,502 | 3,243 | 1,745 | 3,403 | 111 |
| VT (QC) | 282 | 813 | 314 | 163 | 318 | 18 |

### Match Results (Stage 1)

| State | COM Loads | COM Matched | COM Rate | RES Loads | RES Matched | RES Rate | Overall Rate |
|-------|-----------|-------------|----------|-----------|-------------|----------|-------------|
| **MT** | 883 | 861 | **97.5%** | 519 | 519 | **100%** | 98.4% |
| **WA** | 883 | 883 | **100%** | 519 | 519 | **100%** | 100% |
| **MI** | 883 | 881 | **99.8%** | 519 | 519 | **100%** | 99.9% |
| **VT** | 883 | 862 | **97.6%** | 519 | 519 | **100%** | 98.5% |

### Tolerance Escalation -- Commercial

Matching algorithm compares all 12 monthly peaks. Tolerance escalates from 5% to 50% in 5% steps (stops at first success).

| Tolerance | MT (AB) | WA (BC) | MI (ON) | VT (QC) |
|-----------|---------|---------|---------|---------|
| 5% | 0 | 3 | 0 | 7 |
| 10% | 35 | 60 | 336 | 75 |
| 15% | 163 | 202 | 182 | 216 |
| 20% | 232 | 293 | 122 | 218 |
| 25% | 155 | 164 | 95 | 93 |
| 30% | 87 | 85 | 60 | 101 |
| 35% | 69 | 42 | 38 | 66 |
| 40% | 59 | 26 | 22 | 44 |
| 45% | 37 | 7 | 13 | 30 |
| 50% | 24 | 1 | 3 | 12 |
| **No match** | **22** | **0** | **2** | **21** |

> MI has the best commercial match quality (336 matches at 10% tolerance) -- correlates with largest EULP pool (2,654 buildings). VT and MT have the most unmatched loads (21-22) -- smallest pools (282 and 499).

### Tolerance Escalation -- Residential

Compares winter peaks (Dec, Jan, Feb) and summer peaks (Jun, Jul, Aug). Tolerance escalates from 5% to 95%.

| Tolerance | MT (AB) | WA (BC) | MI (ON) | VT (QC) |
|-----------|---------|---------|---------|---------|
| 5% | 64 | 89 | 98 | 51 |
| 10% | 162 | 170 | 171 | 129 |
| 15% | 109 | 104 | 98 | 114 |
| 20% | 74 | 66 | 65 | 66 |
| 25% | 42 | 39 | 33 | 52 |
| 30% | 28 | 22 | 21 | 36 |
| 35-50% | 26 | 20 | 23 | 43 |
| 55-95% | 14 | 9 | 10 | 28 |

All 4 states achieve 100% residential match. VT requires the most tolerance escalation (28 matches at 55-95%), consistent with its smallest building pool.

### Final Output (Stage 3: Representative Selection)

| State | Final COM | Final RES | Total Assigned | Unassigned Loads |
|-------|-----------|-----------|----------------|------------------|
| MT (AB) | 861 | 444 | 1,305 | 97 |
| WA (BC) | 883 | 486 | 1,369 | 33 |
| MI (ON) | 881 | 501 | 1,382 | 20 |
| VT (QC) | 862 | 447 | 1,309 | 93 |

> **Note:** The residential final counts (444-501) are less than the 519 matched loads. The `select_rep_family` script uses stratified sampling by building type with capacity limits per type, so not all matched loads receive a final representative building.

### Matching Pipeline Files Per State

| File | Purpose |
|------|---------|
| `review_parquet_matches.csv` | Input: 1,402 SMART-DS loads with monthly stats |
| `df_commercial_matches_out.csv` | Stage 1: commercial match results with tolerance |
| `df_residential_matches_out.csv` | Stage 1: residential match results with tolerance |
| `XX_final_commercial.csv` | Stage 3: final 1:1 commercial assignments |
| `XX_final_residential.csv` | Stage 3: final 1:1 residential assignments |
| `circuits_plain_format/` | 61 circuit subdirectories with OpenDSS files |

No separate log files or `circuit_check_report.csv` found in `*_3b/` directories. The matching scripts use print statements for runtime summaries.

---

## COMBINED SUMMARY

| State | Season(s) | Variants | Circuits | COM Match % | RES Match % | Final Loads | Sim Converged | Sim Failed |
|-------|-----------|----------|----------|-------------|-------------|-------------|--------------|------------|
| MT | summer, winter | 0, 1 | 58 | 97.5% | 100% | 1,305 | 232 | 0 |
| WA | summer, winter | 0, 1 | 58 | 100% | 100% | 1,369 | 232 | 0 |
| MI | summer, winter | 0, 1, 2 | 58 | 99.8% | 100% | 1,382 | 232 | 0 |
| VT | summer, winter | 0, 1, 2 | 58 | 97.6% | 100% | 1,309 | 232 | 0 |
