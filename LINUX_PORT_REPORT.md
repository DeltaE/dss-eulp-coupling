# Linux Port Report

Branch `feature/linux-port`, 10 commits, one blocker per commit (not squashed —
each is independently revertible). Scope: `PROMPT_Linux_Port_v2.md`'s six
blockers + minor items + tests + docs. Terse, answer-first, per the reporting
style requested.

## Numerical impact: nothing new, one residual unknown inherent to the task

**Expected answer is "nothing," and that's the answer for every fix in this
port considered individually.** Two things are worth reading carefully before
trusting that at face value:

1. **The OpenDSS engine itself is a different implementation on Linux.**
   Windows keeps the exact COM `OpenDSSEngine.DSS` object untouched — zero
   change there, by construction of the shim (see BLOCKER 1 below). Linux
   necessarily runs `opendssdirect.py` / DSS C-API instead, since COM doesn't
   exist here. This is inherent to the porting task, not a side effect of any
   specific fix, and the prompt's own SS0 already treats it as
   independently-verified for basic convergence. I re-verified that
   independently on this machine (3-bus circuit, daily mode, 15-minute
   stepsize, 96 steps, `Converged is True`, `Mode/Number/StepSize` all
   correct). What I **cannot** verify without the real data is bit-for-bit
   equivalence across a full real fire-test scenario (real SMART-DS circuit
   topology, real EV/PV/Storage DER, real EULP load profiles) — two
   independent power-flow solver codebases implementing the same algorithm
   can in principle differ at floating-point margins or in iteration/tie-
   breaking behavior on harder cases than a 1-load synthetic circuit. This is
   the single biggest open item; see the checklist at the end.

2. **Two of the case-sensitivity fixes (BLOCKER 2) specifically *prevent* a
   new Linux-only numerical divergence, they don't introduce one.** Windows
   NTFS is case-*insensitive*, so `Loads.dss` vs `loads.dss` vs
   `Loads_original.dss` vs `loads_original.dss` were always the same file
   there regardless of what case a hardcoded string used — the bug was
   latent but never manifested. On ext4 (this machine), those are genuinely
   different paths. Without the fix, Linux would have silently produced
   **wrong, non-matching-Windows results** (DER never compiled into the
   circuit; per-load charging means silently replaced by a flat 1.0 kW /
   0.0 kvar fallback) with no error at all. With the fix, Linux resolves the
   same file Windows always effectively used, so results should match, not
   diverge. Framed the other way: skipping BLOCKER 2 is what would have
   changed numbers, not applying it.

Every other change below (interpreter resolution, `shell=True`→`shlex`,
Windows-path gating, dependency pins, encoding, monitor-export assertions) is
either purely about *how* a command/file is invoked — not what it computes —
or, for the `encoding="utf-8"` additions, provably a no-op for the ASCII-only
content every touched file actually handles (numeric DSS/CSV data, English
metadata). See the per-item notes in the table for the one case
(`encoding=`) that's flagged out of rigor rather than genuine suspicion.

## Blocker table

| # | Blocker | Files touched | Change | Verified by |
|---|---|---|---|---|
| 1 | OpenDSS COM → cross-platform engine | `7_circuit_instantiation/deployer_modules/dss_engine.py` (new), `power_flow_sim_daily_EV_STO_DG_deploy.py`, `verify_phase7_readiness.py`, `deployer_modules/pfs_{ev_modeling,parsing_misc,file_processing}.py` (dead import removal) | `create_dss_engine()` factory: real COM on win32, `opendssdirect` adapter elsewhere, selected by `sys.platform` / `DSS_BACKEND` override. `AllowForms`/`Command`/`Result`/`Converged`/`Mode`/`Number`/`StepSize` are Python properties so `.Converged` (no parens) returns a real bool on both backends — the parens-mistake the audit warned about is structurally impossible through this shim, not just avoided by convention. | Real 3-bus daily-mode (15m, 96-step) solve through the shim on this machine; `tests/test_dss_engine_linux.py` (4 tests, incl. an explicit `isinstance(converged, bool)` regression test) |
| 2 | Filename case sensitivity | `power_flow_sim_daily_EV_STO_DG_deploy.py`, `pipeline_utils.py` (shared `resolve_dss_file`), `0_download_smartds/scan_feeders.py`, `7_circuit_instantiation/instantiate_circuits_and_runs_APPLYFILTER.py` | Case-insensitive `resolve_dss_file()` routes Loads.dss reads/writes and the copy-loop's Master.dss/LoadShapes.dss dispatch. `Redirect ...` line matches made case-insensitive on read while preserving write-back casing. `assert_expected_redirects()` fails loudly if a DER redirect didn't make it in. `scan_feeders.py`'s `rglob("Loads.dss")` (case-sensitive on POSIX regardless of filesystem) switched to a case-insensitive filter. Fixed the same bug class in `instantiate_...APPLYFILTER.py` (found during this pass, not in the original audit list — see below). | `tests/test_case_sensitivity.py` (7 tests) against a fixture pair (`tests/fixtures/{normal_case_feeder,lower_case_feeder}/`) with identical content, one lowercased end-to-end including Redirect lines |
| 3 | Hardcoded `python` interpreter | `run_case.py`, `configs/phases.yaml`, `instantiate_circuits_and_runs_APPLYFILTER.py`, `pipeline_utils.py` | `{python}` ctx placeholder resolved from `sys.executable`; phases.yaml's `python <script>` → `{python} <script>` (33 sites — audit estimated ~15, actual is higher, noted as drift). `subprocess.run(['python', ...])` → `sys.executable`. Startup version guard warns if not 3.11, in both `pipeline_utils.load_config()` and `run_case.py main()` (duplicated deliberately — `run_case.py` doesn't import `pipeline_utils` by design). | `run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --dry-run`: every emitted command resolves to this machine's micromamba interpreter path; `tests/test_orchestrator_dry_run.py` |
| 4 | `shell=True` string commands | `run_case.py` | Both `subprocess.run()` call sites in `run_phase()` use `shlex.split()` + `shell=False` on `os.name == "posix"`; Windows keeps its existing `shell=True` path unchanged. `_check_no_spaces_in_posix_paths()` refuses to run (clear message) if `PIPELINE_WORK_ROOT`/`PIPELINE_SMART_DS_ROOT`/`PIPELINE_PARQUET_ROOT`/the interpreter path contain a space, since a template-substituted value with a space can't be safely `shlex.split()` after the fact. | Real (non-dry-run) subprocess execution via the new code path; verified the space-guard fires against a synthetic space-containing `smart_ds_base` |
| 5 | Hardcoded Windows absolute paths | `verify_fire_test.py`, `prepare_phase7_fire_test.py`; (`verify_phase7_readiness.py`'s SMART-DS-candidate path was fixed as part of the BLOCKER 1 commit, same file/section) | `PARQUET_ROOT`'s `D:\lvg\parquet_data` last-resort default is now win32-only (empty on other platforms rather than pointing at a path that can never exist and would read as a real, wrong "found" result). `prepare_phase7_fire_test.py`'s `D:\github` / `C:\Users\lfv1\Dropbox` / `D:\Dropbox` data_ev search gated behind `sys.platform == "win32"`. | Ran `prepare_phase7_fire_test.py` with `data_ev/` present and (temporarily) absent — confirmed the Linux branch prints a docs pointer instead of a "not found under D:\github" message |
| 6 | `requirements.txt` platform deps + pins | `requirements.txt` | Added `opendssdirect.py; sys_platform != "win32"` alongside the existing `comtypes; sys_platform == "win32"`. Pinned numpy/pandas/scipy/pyarrow/matplotlib/PyYAML/requests/urllib3 to the exact SS0 versions. Added `scipy` (see below — it was missing entirely). `selenium` commented as optional but not removed. | `pip install --dry-run -r requirements.txt`: all 8 pins match this machine's `dsseulp` env exactly |
| — | Minor: encoding | ~16 text-mode `open()`/`.open()` call sites across the live pipeline + legacy scripts | Explicit `encoding="utf-8"` (binary-mode calls untouched — `encoding=` there is meaningless/an error) | `python -m py_compile` on every touched file; behavior is a provable no-op for the ASCII-only content each file actually handles |
| — | Minor: monitor export assertion | `power_flow_sim_daily_EV_STO_DG_deploy.py` | `assert_monitor_exports()` after Compile: confirms each expected `<CircuitName>_Mon_<monitorname>_1.csv` actually landed | Empirically determined the exact filename convention (including the non-obvious `_1` suffix) against a real solve on this machine rather than assumed from docs, then unit-tested `get_circuit_name()`/`assert_monitor_exports()` directly |
| — | Minor: emoji / `PYTHONIOENCODING` | `docs/LINUX_SETUP.md` | Documented; emoji left in place per the audit (`❌ ✅ ⚠️ →` in ~24 files, untouched) | `configs/defaults.yaml` already sets `PYTHONIOENCODING: utf-8` as `base_env` for every `run_case.py`-driven phase; documented the direct-invocation case too |
| — | Bonus: `test_tolerance_match.py` path | `3_tolerance_matching/test_tolerance_match.py` | Hardcoded `spec_from_file_location("opt", "/home/claude/match_smartds_parquets_NC.py")` → resolved relative to the test file's own location | 60 random trials + edge cases now pass on this machine (previously couldn't even import) |

## Found but not fixed, and why

- **`instantiate_circuits_and_runs_APPLYFILTER.py:386`'s `Loads_original.dss`
  hardcoded-case rebuild** — not in the original audit's file list. Found
  during this pass: same root cause and blast radius as the audited BLOCKER 2
  findings (silently falls back to `parse_means_for_daily`'s empty-file
  default instead of real per-load means on a case mismatch), so fixed
  alongside them rather than left for a separate pass. See the BLOCKER 2 row.
- **`archive_multistate.py:36,41`, `add_shared_placeholders.py:5-9`,
  `1_data_provenance/copy_legacy_project.py:13-14`** — all audited as
  hardcoded Windows paths (BLOCKER 5). Left untouched. These are one-off,
  already-executed personal migration/archival scripts (not referenced by
  `phases.yaml` or `run_case.py` anywhere), hardcoded to one user's specific,
  completed Windows migration events (a conference archive build, a EULP
  metadata workspace copy). Converting them to env-var-with-default has no
  functional benefit for the pipeline and risks touching working
  one-time-use tooling outside platform-port scope — matches the audit's own
  "triage accordingly" hedge for this category.
- **`scan_topology_universe.py`'s case-sensitivity (audit line ~35)** —
  already handled: `has_required_dss()` lowercases before comparing, and
  `count_loads()` has its own working case-insensitive fallback scan. No live
  bug; left as is rather than routed through the new shared
  `resolve_dss_file()`, since it already works and touching it would be
  cosmetic-only churn.
- **The commented-out `"? mode"`/`"? number"`/`"? stepsize"` diagnostic block**
  in `power_flow_sim_daily_EV_STO_DG_deploy.py` (inside a `'''...'''` string,
  lines ~739–754) — audit described this as live code needing a fix
  (`dss.Solution.Mode()` etc. instead of text queries). In the current
  revision it's inert (a bare string literal, never executed) — see "Audit
  drift" below. Left untouched rather than edited dead code; noted here in
  case it's ever reactivated: on Linux, `"? mode"` etc. return `Property
  Unknown` (OpenDSS's `?` resolves element properties only), so use
  `dss.Solution.Mode`/`.Number`/`.StepSize` (already exposed by the shim)
  instead.
- **`selenium` as a real packaging "extra"** — audit said "consider," not
  "must." The repo has no `setup.py`/`pyproject.toml` to hook a real extras
  mechanism into; inventing that packaging layer for one optional dependency
  is out of scope for a platform port. Left installed by default (per "do not
  remove it"), commented as optional in `requirements.txt`.

## Audit drift (code vs. document)

Per the reporting instructions, the code wins wherever it disagreed with the
prompt:

- **`phases.yaml`'s `python <script>` count**: audited as "~15"; actual count
  is 33. Fixed all of them either way.
- **The compile/solve block in `power_flow_sim_daily_EV_STO_DG_deploy.py`**:
  the audit describes lines "646–672 (all engine calls)" as live, including
  the daily-mode `set mode=daily` / `"? mode"` diagnostic block. In the
  current revision, only the engine construction (`create_dss_engine()`,
  `AllowForms`, `Start`), the `Compile` command, and the final
  `print(f"Converged? ...")` are live; the `Solve()` call and the `set
  mode=...`/`"? ..."` diagnostics are inside a `'''...'''` string (inert).
  The script currently relies on Master.dss's *own* embedded `Solve
  mode=daily ...` line (written by `retarget_master_to_daily()`) to actually
  run the solve during `Compile` — the Python-side `Solve()` call being
  commented out doesn't skip solving, it's redundant with what the DSS
  script itself already does. Ported exactly what's live; noted the
  discrepancy here rather than silently "fixing" dead code to match the
  document's assumption about what's live.
- **`scan_topology_universe.py:35`** — audited as a hardcoded-case bug; the
  file already has a working case-insensitive fallback (see "Found but not
  fixed" above).

## What cannot be verified without the real data

The SMART-DS circuits and EULP parquets are not on this machine (still on the
Windows box at `D:\lvg` per SS0). Checklist for the first real run once data
is transferred to `/local-scratch` (see `docs/LINUX_SETUP.md`):

- [ ] Run `run_case.py --case <a real case> --all` end-to-end (not dry-run)
      and diff Phase 5c/6 CSV outputs byte-for-byte against the Windows
      baseline for the same case/season.
- [ ] Run Phase 7 (`prepare_phase7_fire_test.py` → `7a`/`7b`/`7c`) against a
      real feeder with real EV/PV/Storage targets and confirm
      `assert_expected_redirects()` / `assert_monitor_exports()` both pass
      silently (i.e., don't need to fire) on a real scenario, not just the
      synthetic ones in `tests/`.
- [ ] Diff the resulting monitor CSVs (`<Circuit>_Mon_<name>_1.csv`) and any
      other Phase 7/8 numeric outputs against the Windows baseline for the
      same case — this is the actual test of the engine-equivalence question
      raised above; nothing in this repo can substitute for it.
- [ ] Confirm the real SMART-DS export's actual file casing — everything is
      now case-insensitive-tolerant, but if the real data uses a casing
      pattern not represented in `tests/fixtures/`, run
      `scan_topology_universe.py --root <path>` and `tests/test_case_sensitivity.py`
      again for confidence before a full run.
- [ ] Confirm `configs/local.yaml`'s `smart_ds_base` and
      `PIPELINE_PARQUET_ROOT` point at real, space-free `/local-scratch`
      paths (the POSIX `shlex.split()` path depends on this — BLOCKER 4).
- [ ] If regenerating `0_experimental_design`'s LHS/Sobol mixes is ever
      needed on this machine: confirm `scipy==1.11.4` (now pinned; was
      previously entirely absent from `requirements.txt` despite being a real
      import — `run_mix_generator.py: from scipy.stats import qmc`) actually
      reproduces the same sampling sequence as whatever scipy version
      originally produced the existing `mixes_lhs.json`/`mixes_sobol.json`.
      This stage is outside `run_case.py`'s deterministic-chain scope, so it
      wasn't otherwise exercised here.

## Windows-regression risk

Judged low across the board; the specific reasoning per change:

- **BLOCKER 1 (engine shim)**: zero risk. The win32 branch of
  `create_dss_engine()` returns the exact same `comtypes.client.CreateObject(...)`
  object as before; nothing about the Windows call path changed.
- **BLOCKER 2 (case resolution)**: zero risk. `resolve_dss_file()` checks the
  exact-case path first and only falls back to a case-insensitive scan if
  that misses — on NTFS the exact-case path always hits, so the fallback
  branch is simply never reached on Windows.
- **BLOCKER 3 (`{python}`/`sys.executable`)**: zero risk. `sys.executable` on
  Windows resolves to the same interpreter a user would have had on `PATH` as
  `python` in the working setup (Anaconda Prompt with the env activated);
  behavior is equivalent by construction.
- **BLOCKER 4 (`shlex`/`shell=False`)**: zero risk. Explicitly gated on
  `os.name == "posix"`; the Windows branch is the original `shell=True`
  string path, untouched.
- **BLOCKER 5 (path gating)**: zero risk. Every change preserves the exact
  Windows-branch value/behavior; only the non-Windows branch's value changed
  (from a nonsensical Windows path to empty/skipped).
- **BLOCKER 6 (requirements pins)**: zero risk *if* the Windows machine is
  already running these exact versions (which SS0 states as measured fact).
  If it somehow isn't, pinning would force an upgrade/downgrade there too —
  worth a one-time `pip list` diff-check on the Windows machine before
  merging, since this repo has no way to verify that from here.
- **Minor: encoding**: low-but-nonzero. Explicit `utf-8` on both read and
  write **replaces** an implicit `locale.getpreferredencoding()` default that
  was `cp1252` on Windows. Every file touched handles ASCII-only content in
  practice (numeric DSS definitions, English metadata/JSON), so this should
  be a no-op — but it's the one change in this port that could theoretically
  alter Windows-side output if a file the audit or I missed ever carries
  genuine non-ASCII bytes. Flagged per the report's own instruction to surface
  anything that conceivably could, rather than silently asserting "safe."
- **Minor: monitor export assertion / redirect assertion**: zero risk on a
  correct run (both are pure post-hoc checks that raise on failure, not
  before). They *could* newly surface a pre-existing bug on Windows if one
  exists there today (e.g. a redirect silently missing for some other
  reason) — that would be a correctness improvement being surfaced, not a
  regression, but worth knowing before assuming a Windows run that used to
  "work" will still exit 0.
