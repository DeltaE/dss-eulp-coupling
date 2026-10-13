# AGENTS.md

Instructions for coding agents working in this repository. Human readers
start with `README.md`.

## Project

SMART-DS distribution feeders coupled with NREL End-Use Load Profiles and
simulated in OpenDSS. The case matrix is 2×2: two feeder topologies (GSO
in North Carolina, AUS in Texas) against two building-stock states (NC,
TX), each run for summer and winter. Eight case-seasons in total.

## Setup

- Python 3.11. Dependencies in `requirements.txt`.
- Copy `configs/local.yaml.example` to `configs/local.yaml` and set the
  machine paths. `configs/local.yaml` is never committed.
- Data prerequisites are in `README.md`, section "Prerequisites for a
  cold clone".
- Phase 7 on Windows uses the OpenDSS COM interface.

## Run

From the repository root:

```
python run_case.py --case configs/cases/<case>.yaml --all --season <summer|winter>
```

Cases: `NC_GSO_urban__NC`, `NC_GSO_urban__TX`, `TX_AUS_urban__NC`,
`TX_AUS_urban__TX`. Outputs go to `runs/<case>/<season>/workspace/`.
`runs/` is generated and untracked.

## Layout

Phase folders `0_` to `8_` run in numeric order. `configs/phases.yaml`
and `run_case.py` define what `--all` executes; they are the authority on
which scripts are live. Thin `phaseN_*.py` wrappers invoke the
implementation scripts.

## Acceptance

A change to pipeline code is accepted when a fresh clone, given only
`configs/local.yaml` and the documented inputs, reproduces the baseline
outputs byte for byte. Maintainers run that comparison with tooling kept
outside the repository.

## Rules

- Minimal diffs. Change only what the task names. No reformatting and no
  unrequested refactoring.
- No hash or checksum verification in pipeline code.
- No new tracked files unless the task asks for them.
- Never delete. Move to an archive outside the repository and record the
  move.
- Never push. Never rewrite history on `main`: commit SHAs are cited in
  `README.md` and in the manuscript.
- Pipeline outputs belong under the case-season workspace. Nothing is
  written to the repository root.
- Do not commit generated data: Parquet, spreadsheets, Tableau workbooks,
  large CSVs.
- Before removing a file, confirm nothing reads it: check
  `configs/phases.yaml`, `run_case.py`, and grep the tracked `.py` files.
- When a step is ambiguous or a required file is missing, stop and
  report.
- Every claim in a summary cites a file and line, or a command and its
  output.

## Commits

One concern per commit. Prefixes: `feat:`, `fix:`, `docs:`, `chore:`.
Commit only when the task's gate passes.

## Documentation style

Short declarative sentences in the active voice. No em-dashes. Canadian
spelling.

## Local state

If `_plan/STATE.md` exists (untracked), read it before starting. It holds
the machine paths and the current task state. At the end of a job,
replace its contents with the new state.
