#!/usr/bin/env python3
"""
run_case.py - Instantiation-management compatibility layer for the SMART-DS x EULP pipeline.

A "case" pins one TOPOLOGY (which SMART-DS circuit) x one DONOR (which EULP state).
Seasons (summer, winter) are preconfigured and run for every case. Scenario mixes / LHS
are intentionally OUT of scope here - they live downstream in 0_experimental_design (the
LHS) and Phase 7 (DER deployment).

This layer runs only the DETERMINISTIC instantiation chain (the proven fire-test sequence):
    pre -> 1 -> 2 -> 3 -> 4 -> 5a -> 5b -> 5d -> 5b_variants -> 5c
It sets the PIPELINE_* environment variables the existing scripts already read
(see pipeline_utils.py) and shells out to them. No core pipeline code is modified.

Usage:
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --all
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --phase pre
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --phase 5c --season summer
    python run_case.py --case configs/cases/NC_GSO_rural__TX.yaml --all --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = REPO_ROOT / "configs"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _git_info() -> dict:
    def _run(args):
        try:
            return subprocess.check_output(
                ["git", *args], cwd=REPO_ROOT, stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            return "unknown"

    return {"branch": _run(["rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": _run(["rev-parse", "HEAD"])}


def _subst(value: str, ctx: dict) -> str:
    for key, val in ctx.items():
        value = value.replace("{" + key + "}", str(val))
    return value


def resolve_case(case_path: Path) -> dict:
    """Merge case + registries + defaults + local into one resolved dict."""
    case = _load_yaml(case_path)
    topo_reg = _load_yaml(CONFIG_DIR / "topology_registry.yaml")["topologies"]
    donor_reg = _load_yaml(CONFIG_DIR / "donor_registry.yaml")["donors"]
    defaults = _load_yaml(CONFIG_DIR / "defaults.yaml")

    local_path = CONFIG_DIR / "local.yaml"
    if not local_path.exists():
        sys.exit(f"Missing {local_path}.\n"
                 f"  -> copy configs/local.yaml.example to configs/local.yaml and edit it.")
    local = _load_yaml(local_path)

    topo_id, donor_id = case["topology_id"], case["donor_id"]
    if topo_id not in topo_reg:
        sys.exit(f"Unknown topology_id '{topo_id}' (not in topology_registry.yaml).")
    if donor_id not in donor_reg:
        sys.exit(f"Unknown donor_id '{donor_id}' (not in donor_registry.yaml).")
    topo, donor = topo_reg[topo_id], donor_reg[donor_id]

    if topo.get("status") != "ready":
        sys.exit(f"Topology '{topo_id}' is status='{topo.get('status')}', not ready.\n"
                 f"  -> extract a real SMART-DS circuit, fill its paths, set status: ready.")
    if donor.get("status") != "ready":
        sys.exit(f"Donor '{donor_id}' is status='{donor.get('status')}', not ready.")

    smart_ds_base = local.get("smart_ds_base")
    if not smart_ds_base:
        sys.exit("local.yaml must define smart_ds_base.")
    smart_ds_root = (Path(smart_ds_base) / topo["smart_ds_relpath"]).as_posix()

    return {
        "case_id": case.get("case_id", case_path.stem),
        "topology_id": topo_id,
        "donor_id": donor_id,
        "smart_ds_root": smart_ds_root,
        "circuit_folder": topo.get("circuit_folder"),
        "donor_state": donor["donor_state"],
        "max_feeders": case.get("execution", {}).get("max_feeders", "null"),
        "eulp_download_date": donor.get("eulp_download_date"),
        "seasons": defaults.get("seasons", ["summer", "winter"]),
        "phase_order": defaults.get("phase_order", []),
        "base_env": defaults.get("base_env", {}),
        "local": local,
    }


def build_env(resolved: dict, season: str) -> dict:
    """Compose the PIPELINE_* contract the existing scripts read (pipeline_utils.py)."""
    env = dict(os.environ)
    env.update({k: str(v) for k, v in resolved["base_env"].items()})
    env["PIPELINE_STATE"] = resolved["donor_state"]            # donor side
    env["PIPELINE_SEASON"] = season
    env["PIPELINE_SMART_DS_ROOT"] = resolved["smart_ds_root"]  # topology side
    env["PIPELINE_MAX_FEEDERS"] = str(resolved["max_feeders"])
    local = resolved["local"]
    if local.get("smart_ds_parquet_root"):                     # optional override
        env["PIPELINE_SMART_DS_PARQUET_ROOT"] = str(local["smart_ds_parquet_root"])
    if local.get("parquet_data_root"):                         # optional override
        env["PIPELINE_PARQUET_ROOT"] = str(local["parquet_data_root"])
    return env


def run_phase(phase_id, phase_def, resolved, season, env, log, dry_run) -> bool:
    ctx = {"smart_ds_root": resolved["smart_ds_root"],
           "max_feeders": resolved["max_feeders"],
           "state": resolved["donor_state"]}
    phase_env = dict(env)
    for k, v in (phase_def.get("env") or {}).items():
        phase_env[k] = _subst(str(v), ctx)

    def emit(msg):
        print(msg)
        log.write(msg + "\n")
        log.flush()

    emit(f"\n=== [{season}] PHASE {phase_id} ===")
    for step in phase_def.get("steps", []):
        if "copy" in step:
            src = _subst(step["copy"][0], ctx)
            dst = _subst(step["copy"][1], ctx)
            src_p, dst_p = REPO_ROOT / src, REPO_ROOT / dst
            if dst.endswith("/"):
                dst_p = dst_p / src_p.name
            emit(f"  copy {src} -> {dst}")
            if not dry_run:
                dst_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_p, dst_p)
        elif "cmd" in step:
            cmd = _subst(step["cmd"], ctx)
            rel_cwd = step.get("cwd", ".")
            emit(f"  run ({rel_cwd}): {cmd}")
            if not dry_run:
                rc = subprocess.run(cmd, cwd=REPO_ROOT / rel_cwd,
                                    env=phase_env, shell=True).returncode
                if rc != 0:
                    emit(f"  !! command failed (exit {rc})")
                    return False

    verify = phase_def.get("verify")
    if verify and not dry_run:
        emit(f"  verify --phase {verify}")
        rc = subprocess.run(f"python verify_fire_test.py --phase {verify}",
                            cwd=REPO_ROOT, env=env, shell=True).returncode
        if rc != 0:
            emit(f"  !! verify failed (exit {rc})")
            return False
    return True


def write_manifest(run_dir: Path, resolved: dict, season: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "case_id": resolved["case_id"],
        "topology": {"topology_id": resolved["topology_id"],
                     "smart_ds_root": resolved["smart_ds_root"],
                     "circuit_folder": resolved["circuit_folder"]},
        "donor": {"donor_state": resolved["donor_state"],
                  "eulp_download_date": resolved["eulp_download_date"],
                  "season": season},
        "git": _git_info(),
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    with open(run_dir / "resolved_case.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(manifest, fh, sort_keys=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a topology x donor instantiation case.")
    ap.add_argument("--case", required=True, type=Path)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--phase", help="single phase id (e.g. pre, 1, 5c)")
    grp.add_argument("--all", action="store_true", help="run the full deterministic phase order")
    ap.add_argument("--season", choices=["summer", "winter"], help="run one season only")
    ap.add_argument("--dry-run", action="store_true", help="print commands without executing")
    args = ap.parse_args()

    resolved = resolve_case(args.case)
    phases = _load_yaml(CONFIG_DIR / "phases.yaml")
    seasons = [args.season] if args.season else resolved["seasons"]
    phase_ids = [args.phase] if args.phase else resolved["phase_order"]

    runs_root = Path(resolved["local"].get("runs_root", "runs"))
    if not runs_root.is_absolute():
        runs_root = REPO_ROOT / runs_root

    print(f"Case {resolved['case_id']}: topology={resolved['topology_id']} "
          f"donor={resolved['donor_state']} seasons={seasons}")
    print(f"  PIPELINE_SMART_DS_ROOT={resolved['smart_ds_root']}")

    overall_ok = True
    for season in seasons:
        run_dir = runs_root / resolved["case_id"] / season
        write_manifest(run_dir, resolved, season)
        status = {}
        with open(run_dir / "run_log.txt", "a", encoding="utf-8") as log:
            log.write(f"\n##### run {_dt.datetime.now().isoformat(timespec='seconds')} "
                      f"season={season} phases={phase_ids} dry_run={args.dry_run}\n")
            env = build_env(resolved, season)
            for pid in phase_ids:
                if pid not in phases:
                    log.write(f"  (no definition for phase {pid}, skipping)\n")
                    status[pid] = "undefined"
                    continue
                ok = run_phase(pid, phases[pid], resolved, season, env, log, args.dry_run)
                status[pid] = "ok" if ok else "failed"
                if not ok:
                    overall_ok = False
                    break
        with open(run_dir / "phase_status.json", "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=2)
        print(f"[{season}] status: {status}  ->  {run_dir}")

    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
