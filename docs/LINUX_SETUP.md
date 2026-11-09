# Linux Setup

Machine-specific setup for running this pipeline natively on Linux, without OpenDSS
COM or Windows. [instantiation_management.md](instantiation_management.md) covers
the general topology, donor and case model. This page covers the platform-specific
parts: interpreter, dependencies, environment variables, and where the SMART-DS
and EULP data go.

Verified against `srye-deltae-08` (Ubuntu 20.04, glibc 2.31). The version numbers
below are hard constraints. The acceptance bar for this port is zero numerical
change against the Windows baseline. That bar is only checkable if numpy, pandas
and pyarrow are byte-identical.

## 1. Create the Python 3.11 environment

The system Python on most distros (3.8 on Ubuntu 20.04) is too old for the pinned
dependency set. A run under it can be invalid with no other symptom.
`tests/test_environment_pins.py` (below) checks the interpreter and the pins.

```bash
# micromamba, conda or mamba: any environment manager that gives a real,
# isolated Python 3.11 works. This page was verified with micromamba.
micromamba create -n dsseulp python=3.11 -y
micromamba activate dsseulp

pip install -r requirements.txt
```

`requirements.txt` pins every package to the exact version verified on the
Windows machine that produced all existing results (numpy 1.26.4, pandas
2.1.4, pyarrow 14.0.2, matplotlib 3.8.0, PyYAML 6.0.1, requests
2.31.0, urllib3 2.0.7). It declares the platform split for the OpenDSS engine:
`comtypes` on win32, `opendssdirect.py` everywhere else. **Do not** upgrade or
downgrade any of these without re-validating outputs against the Windows
baseline first.

Confirm the pins landed:

```bash
python tests/test_environment_pins.py
```

## 2. Verify the OpenDSS engine reaches Linux correctly

Phase 7 reaches OpenDSS through
`7_circuit_instantiation/deployer_modules/dss_engine.py`, which selects a
backend by `sys.platform` (override with `DSS_BACKEND=com|direct` for
cross-platform testing). On Linux this is a thin adapter over
`opendssdirect.py` and DSS C-API. That engine is a separate implementation from
the Windows COM `OpenDSSEngine.DSS`. It was verified independently for a
daily-mode, 15-minute-stepsize, 96-step solve.

```bash
python tests/test_dss_engine_linux.py
```

## 3. Environment variables

`run_case.py` sets every `PIPELINE_*` variable from `configs/local.yaml` and
`configs/cases/*.yaml`. The table in [workflow.md](workflow.md) lists them. A
phase script exits 1 when a run value it reads is unset, so run the phases
through `run_case.py`.

### `configs/local.yaml`

Per-machine, gitignored. Copy the example and set the three machine paths.
`smart_ds_base` is the SMART-DS data root. `eulp_metadata_root` is the folder
that holds `Metadata_<ST>_Residential/` and `Metadata_<ST>_Commercial/`. Both
must exist. `runs_root` is where each case-season writes its workspace.

```bash
cp configs/local.yaml.example configs/local.yaml
```

```yaml
smart_ds_base: "/local-scratch/<you>/smartds"
eulp_metadata_root: "/local-scratch/<you>/eulp_metadata"
runs_root: "/local-scratch/<you>/runs"
```

## 4. Getting the data onto this machine

Put the SMART-DS tree, the EULP parquet pool and the EULP metadata under
`/local-scratch` (node-local ext4). `/cvmfs/rcg.sfu.ca` is read-only software
distribution. `README.md`, section "Prerequisites for a cold clone", lists the
data each case needs.

`/cvmfs` is read-only. Write pipeline outputs elsewhere.

### Case sensitivity

This box is ext4, which is case-sensitive. The Windows machine the data was
produced on is case-insensitive. File access goes through a case-insensitive
resolver: `resolve_dss_file()` in `pipeline_utils.py`, and a local copy in
`power_flow_sim_daily_EV_STO_DG_deploy.py`, since that script is copied into
each circuit folder. If the SMART-DS export you copy over uses a casing that has
not been tested, run `tests/test_case_sensitivity.py` before trusting a full
pipeline run.

## 5. Encoding

`PYTHONIOENCODING=utf-8` is set as `base_env` for every phase in
`configs/defaults.yaml`, so `run_case.py`-driven runs need nothing extra. A phase
script run directly, outside `run_case.py`, can fail on the `✅`/`❌`/`⚠️` status
glyphs in its own output under `LANG=C` or similar. Set the variable yourself in
that case:

```bash
export PYTHONIOENCODING=utf-8
```

File I/O passes `encoding="utf-8"` explicitly wherever the pipeline reads or
writes text. The platform default is cp1252 on Windows and utf-8 here, so the
setting above only affects the output stream. File contents are the same on both.

## 6. Path constraints

On POSIX, phase commands run through `shlex.split()` with `shell=False`. A
space anywhere in `PIPELINE_WORK_ROOT`, `PIPELINE_SMART_DS_ROOT`,
`PIPELINE_PARQUET_ROOT`, or the Python interpreter path breaks command parsing.
`run_case.py` checks for this at startup and refuses to run with a clear
message. Keep all of these paths free of spaces.

## 7. Running the deterministic chain

```bash
python run_case.py --case configs/cases/<your-case>.yaml --all --dry-run   # sanity check first
python run_case.py --case configs/cases/<your-case>.yaml --all
```

See [instantiation_management.md](instantiation_management.md) for what a
"case" is and how to add a new topology or donor.

## 8. Full test sweep

None of these need real SMART-DS or EULP data:

```bash
for f in tests/test_*.py; do python "$f" || echo "FAILED: $f"; done
```

`pytest tests/` runs the same files, since every file is pytest-discoverable.
