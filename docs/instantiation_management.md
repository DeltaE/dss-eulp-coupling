# Instantiation Management

This layer turns the SMART-DS x EULP pipeline into explicit, reproducible **cases**. A case
pins one **topology** (which SMART-DS circuit) and one **donor** (which EULP state), runs the
deterministic instantiation chain, and writes a provenance manifest. It does **not** touch
scenario mixes or the LHS - those are downstream (see *Out of scope*).

## The two dimensions

- **Topology** - which SMART-DS / OpenDSS circuit is instantiated. A finite menu of *downloaded*
  circuits in `configs/topology_registry.yaml`. Sets `PIPELINE_SMART_DS_ROOT`.
- **Donor** - which state's EULP profiles are assigned to that topology. Listed in
  `configs/donor_registry.yaml`. Sets `PIPELINE_STATE`.

A case is therefore `topology x donor`, e.g. `NC_GSO_rural__TX` = NC circuit, TX load profiles.

## Seasons

Summer and winter run for **every** case (`configs/defaults.yaml: seasons`), matching the tested
setup. Shoulder seasons (spring/fall) are **To Be Tested** and left unwired - the slot is
documented but inert.

## Where .dss inputs come from

`.dss` feeder files are **external inputs** and are not versioned. They live under the SMART-DS
root on each machine. `configs/local.yaml` (gitignored) sets `smart_ds_base`; each topology's
`smart_ds_relpath` is appended to it. The registry documents *where* files are expected, not the
files themselves.

## Per-machine config

Copy `configs/local.yaml.example` -> `configs/local.yaml` (gitignored) and set the absolute roots
for that machine. The same case YAML then runs unchanged on every machine.

## Running a case

    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --all
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --phase pre
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --all --dry-run   # preview only
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --all --season summer

`--all` runs the deterministic phase order from `defaults.yaml`. `--dry-run` prints every
command/copy without executing. Provenance is written to `runs/<case_id>/<season>/`.

## Adding a new topology

1. Place/confirm the SMART-DS circuit under your `smart_ds_base`.
2. Add an entry to `configs/topology_registry.yaml` with `smart_ds_relpath`, `circuit_folder`,
   `feeder_id`, and `status: ready`.
3. No core script changes needed.

## Adding a new donor

Add an entry to `configs/donor_registry.yaml` with `donor_state`, `eulp_download_date`, and the
metadata filenames. Set `status: ready`.

## Phase boundary (why these phases)

The layer runs the deterministic chain only:
`pre -> 1 -> 2 -> 3 -> 4 -> 5a -> 5b -> 5d -> 5b_variants -> 5c` (the proven sequence in
`FIRE_TEST_CHEATSHEET.md`). Note "pre" here is `0_download_smartds` (circuit staging), NOT
`0_experimental_design`. Phases 2-6 were verified to have **zero** dependency on
`0_experimental_design` (the LHS); that stage and Phase 7 (DER deployment) consume the mixes and
are deliberately downstream.

## Out of scope (downstream RDM)

- `0_experimental_design` - LHS / `mixes_lhs.json` generation.
- Phase 7 - DER deployment (EV/PV/storage), which consumes the mixes.
- Phase 8 - results analysis.
- Scenario mixes are **not** a dimension of this layer.

## Provenance

Each run writes `runs/<case_id>/<season>/`:
- `resolved_case.yaml` - topology, donor, season, `eulp_download_date`, git branch+commit, timestamp.
- `run_log.txt` - every command/copy executed.
- `phase_status.json` - per-phase ok/failed.

## Pending

- **TX topology** - `TX_pending` is a placeholder. Extract a real TX SMART-DS circuit, fill its
  paths, set `status: ready`. `TX__TX` and `TX__NC` launch only then.
- **Phase 6 (kvar)** - `6_kvar_preparation` (`generate_kvar_csvs.py`, `rev_spec_kvar_kw_ratio.py`,
  `save_needed_sd_parquets.py`) was not in the documented fire-test sequence and is not yet wired
  into `phases.yaml`. Add it once the command order is confirmed.
- **Season re-runs** - `--all` re-runs season-independent phases (pre-5a) once per season, and
  re-running Phase 2 may duplicate ModifiedCircuitData EV loads until a cleanup guard exists. Use
  `--season` to run one at a time meanwhile.
