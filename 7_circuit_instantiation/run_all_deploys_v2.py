# -*- coding: utf-8 -*-
"""
run_prepared_circuits.py  —  simple, procedural batch runner
- Finds prepared circuit folders (name contains "_circuit_") that contain the deploy script
- Skips the repo root (".") even if it has the deploy script
- Runs sequentially and streams output into this console
- Also tees the same output to a UTF-8 log file if LOG_FILE is set
"""

import os, sys, subprocess, time, fnmatch

# ---- user knobs ----
ROOT_DIR    = "."   # where to search
RUNNER      = "power_flow_sim_daily_EV_STO_DG_deploy.py"
GLOB_NAME   = "*_circuit_*"  # only run folders whose name matches this
MAX_RUN     = None  # e.g., 3 for a quick test; None = all
STOP_ON_ERR = False  # True → stop at first nonzero exit code

# --- simple logging to a text file (UTF-8) ---
LOG_FILE = "run_log.txt"   # set to None to disable file logging
APPEND   = True            # False = overwrite, True = append

# ---- tiny helpers (keep it minimal) ----
def safe_print(s, end=""):
    try:
        print(s, end=end)
    except UnicodeEncodeError:
        # strip non-ascii so Windows cp1252 consoles don't crash on emoji, etc.
        sys.stdout.write(s.encode("ascii", "ignore").decode("ascii"))
        if end:
            sys.stdout.write(end)
        sys.stdout.flush()

# ---- discover circuit folders ----
root_abs = os.path.abspath(ROOT_DIR)
candidates = []

for dirpath, dirnames, filenames in os.walk(root_abs):
    # skip the root itself
    if os.path.abspath(dirpath) == root_abs:
        continue
    base = os.path.basename(dirpath)
    if "_circuit_" not in base:
        continue
    if RUNNER not in filenames:
        continue
    if not fnmatch.fnmatch(base, GLOB_NAME):
        continue
    candidates.append(dirpath)

candidates.sort()
if MAX_RUN:
    candidates = candidates[:MAX_RUN]

if not candidates:
    print(f"No circuit folders found under {ROOT_DIR} with runner '{RUNNER}'.")
    sys.exit(1)

# open log (if enabled)
logf = None
if LOG_FILE:
    try:
        mode = "a" if APPEND else "w"
        logf = open(LOG_FILE, mode, encoding="utf-8", buffering=1)  # line-buffered
        print(f"[log] Writing live output to {LOG_FILE}")
    except Exception as e:
        print(f"[log] Could not open {LOG_FILE}: {e}")
        logf = None

header = f"Found {len(candidates)} circuit folders with {RUNNER}:"
print(header)
if logf: logf.write(header + "\n")

for p in candidates:
    # try to show a relative path; fall back to absolute if needed
    try:
        rel = os.path.relpath(p, root_abs)
    except Exception:
        rel = p
    line = "  " + rel
    print(line)
    if logf: logf.write(line + "\n")

# ---- run sequentially ----
ok = 0; fail = 0; failures = []
t0 = time.time()

for cdir in candidates:
    sep = "\n" + "="*80 + "\n"
    try:
        rel = os.path.relpath(cdir, root_abs)
    except Exception:
        rel = cdir
    run_hdr = f"RUN: {rel}\n" + "="*80

    # console + log headers
    safe_print(sep)
    safe_print(run_hdr + "\n")
    if logf:
        logf.write(sep)
        logf.write(run_hdr + "\n")

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"                 # live output from child
    env.setdefault("PYTHONIOENCODING", "utf-8")   # child prints utf-8 safely
    env.setdefault("DSS_NO_FORMS", "1")           # hint for headless DSS

    cmd = [sys.executable, "-u", RUNNER]
    proc = subprocess.Popen(
        cmd, cwd=cdir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, bufsize=1
    )

    for line in proc.stdout:
        msg = f"[{os.path.basename(cdir)}] {line}"
        safe_print(msg)                 # to console (strip non-ASCII if needed)
        if logf:
            try:
                logf.write(msg)         # to log (UTF-8)
            except Exception:
                pass

    rc = proc.wait()
    exit_line = f"\nEXIT CODE: {rc}"
    print(exit_line)
    if logf: logf.write(exit_line + "\n")

    if rc == 0:
        ok += 1
    else:
        fail += 1
        failures.append((cdir, rc))
        if STOP_ON_ERR:
            break

    # small pause helps OpenDSS COM release resources on Windows
    time.sleep(0.5)

dt = time.time() - t0
summary = "\n" + "-"*60 + f"\nDone in {dt:.1f}s  |  ok={ok}  fail={fail}"
print(summary)
if logf: logf.write(summary + "\n")

if failures:
    print("\nFailures:")
    if logf: logf.write("\nFailures:\n")
    for p, rc in failures:
        try:
            rel = os.path.relpath(p, root_abs)
        except Exception:
            rel = p
        fl = f"  {rel}  (exit {rc})"
        print(fl)
        if logf: logf.write(fl + "\n")

if logf:
    try:
        logf.close()
    except Exception:
        pass

sys.exit(0 if fail == 0 else 2)
