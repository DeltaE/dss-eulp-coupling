# -*- coding: utf-8 -*-
"""
mix_days.py
-----------
Phase mix_days, between 6_variants and 7a in configs/phases.yaml. run_case.py runs it
from the repository root with the PIPELINE_* variables set.

With peak_day_rule: per_group in pipeline_config.yaml it prints one line, writes
nothing and exits 0. With per_circuit, for every mix in the mixes file
(PIPELINE_MIXES_FILE), in file order:
1. Runs 5b_profile_generation/find_max_day_curve_impl.py --mix <mix>: the mix's peak
   day per feeder and season (day X) in <work_root>/mix_days/<STATE>_circuit_days.csv.
   A mix that is 100 % baseline is checked against <STATE>_peak_days.csv and stops
   there. Any other mix has every profile of its three heating groups cut on day X
   under <work_root>/mix_days/<mix>/5b_profile_generation/daily_parquets/.
2. For a mix that is not 100 % baseline, runs with PIPELINE_MIX=<mix> the 5c,
   5c_variants, 6 and 6_variants steps of configs/phases.yaml, then 7a, in that order.
   Their day-dependent reads and all their writes go to <work_root>/mix_days/<mix>/
   (pipeline_utils.resolve_day_path), so that folder ends with the three profhp roots
   of Phase 7 for day X. save_needed_sd_parquets.py does not depend on the day and is
   not rerun: compute_kvar_kw_ratios.py reads its needed_parquets.pkl from the
   workspace.
A step that exits non-zero stops the phase with that exit code.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
from pipeline_utils import load_config, load_mixes, peak_day_rule, resolve_work_path

sys.path.insert(0, str(REPO_ROOT / "7_circuit_instantiation"))
from heating_split import is_baseline_only

# (cwd, arguments): the day-dependent steps of 5c, 5c_variants, 6, 6_variants and 7a
LATER_STEPS = [
    ("5c_csv_conversion", ["parquet_to_csv.py"]),
    ("5c_csv_conversion", ["parquet_to_csv.py", "--scenario", "dm"]),
    ("5c_csv_conversion", ["parquet_to_csv.py", "--scenario", "uncontrolled"]),
    ("6_kvar_preparation", ["compute_kvar_kw_ratios.py"]),
    ("6_kvar_preparation", ["generate_kvar_csvs.py"]),
    ("6_kvar_preparation", ["compute_kvar_kw_ratios.py", "--scenario", "dm"]),
    ("6_kvar_preparation", ["generate_kvar_csvs.py", "--scenario", "dm"]),
    ("6_kvar_preparation", ["compute_kvar_kw_ratios.py", "--scenario", "uncontrolled"]),
    ("6_kvar_preparation", ["generate_kvar_csvs.py", "--scenario", "uncontrolled"]),
    (".", ["bridge_phase5c_to_phase7.py"]),
]


def run(cwd, args, env):
    print(f"[mix_days] run ({cwd}): {' '.join(args)}  PIPELINE_MIX={env.get('PIPELINE_MIX', '')}",
          flush=True)
    rc = subprocess.run([sys.executable, *args], cwd=REPO_ROOT / cwd, env=env).returncode
    if rc != 0:
        print(f"[FAIL] mix_days step {' '.join(args)} exited {rc}.")
        sys.exit(rc)


def main():
    cfg = load_config()
    rule = peak_day_rule(cfg)
    if rule != "per_circuit":
        print(f"[mix_days] peak_day_rule is {rule}: phase mix_days skipped, nothing written.")
        return
    mixes = load_mixes(cfg["mixes_file"])

    for mix_name, mix_cfg in mixes.items():
        env = dict(os.environ)
        env.pop("PIPELINE_MIX", None)
        run("5b_profile_generation", ["find_max_day_curve_impl.py", "--mix", mix_name], env)
        if is_baseline_only(mix_cfg["shares"]):
            continue
        for sub in ("5c_csv_conversion", "6_kvar_preparation", "7_circuit_instantiation"):
            os.makedirs(resolve_work_path("mix_days", mix_name, sub), exist_ok=True)
        env["PIPELINE_MIX"] = mix_name
        for cwd, args in LATER_STEPS:
            run(cwd, args, env)
    print(f"[mix_days] done: {', '.join(mixes)}")


if __name__ == "__main__":
    main()
