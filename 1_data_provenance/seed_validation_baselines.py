"""Seed state-specific validation baselines for eulp_metadata.

Run from 1_data_provenance/:
    python seed_validation_baselines.py

For each state (NC, TX):
  1. Builds the pipeline_state cluster (no validation)
  2. Copies generated outputs to data_derived/historical/ with state suffix
  3. Runs validate-only IMMEDIATELY to confirm the baseline passes
     (must happen before the next state's build overwrites the output)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATES = ["NC", "TX"]

OUTPUTS_DIR = SCRIPT_DIR / "outputs" / "pipeline_state"
HISTORICAL_DIR = SCRIPT_DIR / "data_derived" / "historical"

DATASETS = {
    "residential": "residential_data_SELECT_STATES.csv",
    "commercial": "commercial_data_SELECT_STATES.csv",
}


def run_build(state: str, extra_args: list[str] | None = None) -> int:
    env = os.environ.copy()
    env["PIPELINE_STATE"] = state
    env["PIPELINE_SEASON"] = "summer"  # season doesn't affect Phase 1 output
    # eulp_metadata lives under src/ — matches phases.yaml Phase 1 env: {PYTHONPATH: src}
    src_dir = str(SCRIPT_DIR / "src")
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, "-m", "eulp_metadata.build", "--cluster", "pipeline_state"]
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n{'='*60}")
    print(f"  {' '.join(cmd)}  [PIPELINE_STATE={state}]")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR), env=env)
    return result.returncode


def main() -> int:
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

    for state in STATES:
        # --- Build ---
        print(f"\n>>> Building baseline for {state} ...")
        rc = run_build(state)
        if rc != 0:
            print(f"  !! Build failed for {state} (exit {rc})")
            return 1

        # --- Copy to historical ---
        for dataset, filename in DATASETS.items():
            src = OUTPUTS_DIR / filename
            dst = HISTORICAL_DIR / f"{Path(filename).stem}_{state}.csv"
            if not src.exists():
                print(f"  !! Expected output not found: {src}")
                return 1
            shutil.copy2(src, dst)
            print(f"  Copied {src.name}  ->  {dst.name}")

        # --- Validate immediately (output still matches this state) ---
        rc = run_build(state, ["--validate-only"])
        if rc != 0:
            print(f"  !! Validation FAILED for {state}")
            return 1
        print(f"  OK: {state} baseline seeded and validated")

    print(f"\nAll {len(STATES)} baselines seeded and validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
