# scan_paths.py  --  run from the repo root:   python scan_paths.py
#
# Dumps the path-handling lines from every pipeline script so we can see, per script,
# whether it resolves its I/O via __file__ / SCRIPT_DIR (which IGNORES cwd) or via
# plain relative paths (which follow cwd). That distinction is the whole question for
# per-case isolation:
#   * cwd-relative  -> isolated for free when run_case.py points cwd at the case workspace
#   * __file__-based -> ignores cwd, needs a small redirect to a shared work_root
# This produces the exact minimal edit list -- no guessing about unseen scripts.

import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

PHASE_DIRS = [
    "0_download_smartds", "1_data_provenance", "2_circuit_matching",
    "3_tolerance_matching", "4_quota_assignment", "5a_eulp_downloads",
    "5b_profile_generation", "5c_csv_conversion", "5d_scenario_controls",
    "src",
]

# Tokens that reveal how a script anchors paths and where it reads/writes.
TOKENS = [
    "__file__", "getcwd", "SCRIPT_DIR", "BASE_DIR", "REPO_ROOT", "WORK_ROOT",
    "load_config", "load_feeder_registry", "feeder_registry", "parquet_data_root",
    "to_csv(", "to_parquet(", "savetxt", "read_csv(", "read_parquet(", "read_table(",
    "os.makedirs", ".mkdir(", "os.listdir", "glob(", "pickle.dump", "pickle.load",
    "open(", "runpy",
]
pat = re.compile("|".join(re.escape(t) for t in TOKENS))

SKIP = {"scan_paths.py", "CHECK_PATHS.py"}


def scan(full, rel):
    out = []
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                s = line.strip()
                if s and not s.startswith("#") and pat.search(s):
                    out.append(f"{i:4} | {s[:150]}")
    except Exception as e:  # noqa: BLE001
        out.append(f"   ! could not read: {e}")
    if out:
        print(f"\n### {rel}")
        print("\n".join(out))


# repo-root scripts (run_case.py, pipeline_utils.py, verify_fire_test.py, ...)
for fn in sorted(os.listdir(ROOT)):
    full = os.path.join(ROOT, fn)
    if fn.endswith(".py") and fn not in SKIP and os.path.isfile(full):
        scan(full, fn)

# phase dirs, recursive (catches src/eulp_metadata, etc.)
for d in PHASE_DIRS:
    base = os.path.join(ROOT, d)
    if not os.path.isdir(base):
        continue
    for dp, dn, fns in os.walk(base):
        dn[:] = [x for x in dn if x not in (".git", "__pycache__", "runs", "daily_parquets")]
        for fn in sorted(fns):
            if fn.endswith(".py"):
                full = os.path.join(dp, fn)
                scan(full, os.path.relpath(full, ROOT).replace("\\", "/"))

print("\n--- done ---")
