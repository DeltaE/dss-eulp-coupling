#!/usr/bin/env python3
"""
run_case.py - Instantiation-management compatibility layer for the SMART-DS x EULP pipeline.

A "case" pins one TOPOLOGY (which SMART-DS circuit) x one DONOR (which EULP state).
Seasons (summer, winter) are preconfigured and run for every case. Scenario mixes / LHS
are intentionally OUT of scope here - they live downstream in 0_experimental_design (the
LHS) and Phase 7 (DER deployment).

This layer runs only the DETERMINISTIC instantiation chain (the proven fire-test sequence):
    pre -> 1 -> 2 -> 3 -> 4 -> 5a -> 5b -> 5d -> 5b_variants -> 5c -> 5c_variants -> 6 -> 6_variants -> 7a -> 7b -> 7c -> 8
It sets the PIPELINE_* environment variables the existing scripts already read
(see pipeline_utils.py) and shells out to them. No core pipeline code is modified.

Usage:
    python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all
    python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --phase pre
    python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --phase 5c --season summer
    python run_case.py --case configs/cases/NC_GSO_urban__NC.yaml --all --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
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
    eulp_metadata_root = local.get("eulp_metadata_root")
    if not eulp_metadata_root:
        sys.exit("local.yaml must define eulp_metadata_root.")
    if not Path(eulp_metadata_root).is_dir():
        sys.exit(f"eulp_metadata_root folder does not exist: {eulp_metadata_root}")
    eulp_metadata_root = Path(eulp_metadata_root).as_posix()
    topo_relpath = Path(topo["smart_ds_relpath"])
    smart_ds_root = Path(smart_ds_base) / topo_relpath
    if topo.get("circuit_folder"):
        smart_ds_root = smart_ds_root / topo["circuit_folder"]
    smart_ds_root = smart_ds_root.as_posix()
    mixes_file = defaults.get("mixes_file")
    if not mixes_file:
        sys.exit("defaults.yaml must define mixes_file.")
    mixes_file = Path(mixes_file)
    if not mixes_file.is_absolute():
        mixes_file = REPO_ROOT / mixes_file

    # Donor parquet pool is the deterministic sibling of the opendss tree:
    #   <dataset>/<morphology>/base_timeseries/opendss  ->  <dataset>/<morphology>/parquet_data
    # Co-located across GSO/AUS (confirmed: loose com_*/res_* at the parquet_data root).
    # The same physical folder feeds BOTH PIPELINE_PARQUET_ROOT (donor pool, Phase 2)
    # and PIPELINE_SMART_DS_PARQUET_ROOT (SMART-DS load parquets, Phase 6 kVAr).
    # Optional escape hatch: a topology entry may set parquet_relpath to override the
    # derived path for datasets that stage the pool elsewhere (e.g. a future SFO layout).
    parquet_relpath = topo.get("parquet_relpath")
    if parquet_relpath:
        parquet_root = (Path(smart_ds_base) / parquet_relpath).as_posix()
    else:
        parquet_root = (Path(smart_ds_base) / topo_relpath.parent.parent / "parquet_data").as_posix()

    return {
        "case_id": case.get("case_id", case_path.stem),
        "topology_id": topo_id,
        "donor_id": donor_id,
        "smart_ds_root": smart_ds_root,
        "parquet_root": parquet_root,
        "eulp_metadata_root": eulp_metadata_root,
        "mixes_file": mixes_file.resolve().as_posix(),
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
    work_root = resolved["work_root"]
    env["PIPELINE_STATE"] = resolved["donor_state"]            # donor side
    env["PIPELINE_SEASON"] = season
    env["PIPELINE_WORK_ROOT"] = work_root
    env["PIPELINE_RUNS_ROOT"] = resolved["runs_root"]
    env["PIPELINE_SMART_DS_ROOT"] = resolved["smart_ds_root"]  # topology side (opendss)
    env["PIPELINE_MAX_FEEDERS"] = str(resolved["max_feeders"])
    env["PIPELINE_FEEDER_REGISTRY_PATH"] = os.path.join(work_root, "feeder_registry.json")
    # Per-topology donor pool (derived in resolve_case). Both roots coincide for
    # co-located datasets; threaded explicitly so the architectural split is preserved.
    env["PIPELINE_PARQUET_ROOT"] = resolved["parquet_root"]            # donor pool, Phase 2
    env["PIPELINE_SMART_DS_PARQUET_ROOT"] = resolved["parquet_root"]   # SMART-DS load parquets, Phase 6
    env["PIPELINE_EULP_METADATA_ROOT"] = resolved["eulp_metadata_root"]  # EULP metadata CSVs, Phase 1
    env["PIPELINE_EULP_DOWNLOAD_DATE"] = str(resolved["eulp_download_date"])  # donor registry
    env["PIPELINE_MIXES_FILE"] = resolved["mixes_file"]  # mixes_file in defaults.yaml, Phase 7a
    return env


def run_phase(phase_id, phase_def, resolved, season, env, log, dry_run) -> bool:
    ctx = {"python": f'"{sys.executable}"',
           "smart_ds_root": resolved["smart_ds_root"],
           "max_feeders": resolved["max_feeders"],
           "work_root": resolved["work_root"],
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
            src_p, dst_p = Path(src), Path(dst)
            if not src_p.is_absolute():
                src_p = REPO_ROOT / src_p
            if not dst_p.is_absolute():
                dst_p = REPO_ROOT / dst_p
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
    if verify:
        emit(f"  verify --phase {verify}")
    if verify and not dry_run:
        rc = subprocess.run(f"{ctx['python']} verify_phase.py --phase {verify}",
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


def prepare_work_root(work_root: str) -> None:
    for rel_path in [
        "1_data_provenance/outputs/pipeline_state",
        "2_circuit_matching/circuits_plain_format",
        "3_tolerance_matching",
        "4_quota_assignment",
        "5b_profile_generation/daily_parquets",
        "5c_csv_conversion",
        "5d_scenario_controls/combine_scenarios",
        "5d_scenario_controls/get_scenario_csv_controls",
        "6_kvar_preparation",
        "7_circuit_instantiation",
        "7_circuit_instantiation/profiles_use_bench",
        "8_results_analysis",
    ]:
        os.makedirs(os.path.join(work_root, rel_path), exist_ok=True)


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
    runs_root = runs_root.resolve()
    resolved["runs_root"] = runs_root.as_posix()
    print(f"Case {resolved['case_id']}: topology={resolved['topology_id']} "
          f"donor={resolved['donor_state']} seasons={seasons}")
    print(f"  PIPELINE_SMART_DS_ROOT={resolved['smart_ds_root']}")
    print(f"  PIPELINE_PARQUET_ROOT={resolved['parquet_root']}")
    print(f"  PIPELINE_EULP_METADATA_ROOT={resolved['eulp_metadata_root']}")

    workspaces = {season: (runs_root / resolved["case_id"] / season / "workspace").resolve()
                  for season in seasons}
    # --all checks every requested season before anything runs or is created.
    existing = [ws for ws in workspaces.values() if ws.exists()] if args.all else []
    if existing and args.dry_run:
        for ws in existing:
            print(f"  note: {ws.as_posix()} already exists; a run without --dry-run refuses it.")
    elif existing:
        sys.exit("These workspaces already exist:\n"
                 + "".join(f"  {ws.as_posix()}\n" for ws in existing)
                 + "A run always starts from an empty workspace.\n"
                 "Delete those folders to rerun these case-seasons, or run a different case.")

    overall_ok = True
    for season in seasons:
        work_root = workspaces[season]
        resolved["work_root"] = str(work_root)
        print(f"  PIPELINE_WORK_ROOT={resolved['work_root']}")
        run_dir = runs_root / resolved["case_id"] / season
        env = build_env(resolved, season)
        if args.dry_run:
            # A dry run writes nothing: no records, no workspace, no log.
            for key in sorted(k for k in env if k.startswith("PIPELINE_")):
                print(f"  {key}={env[key]}")
            log_file = io.StringIO()
        else:
            write_manifest(run_dir, resolved, season)
            prepare_work_root(resolved["work_root"])
            log_file = open(run_dir / "run_log.txt", "a", encoding="utf-8")
        status = {}
        with log_file as log:
            log.write(f"\n##### run {_dt.datetime.now().isoformat(timespec='seconds')} "
                      f"season={season} phases={phase_ids} dry_run={args.dry_run}\n")
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
        if args.dry_run:
            print(f"[{season}] dry run: nothing written")
            continue
        with open(run_dir / "phase_status.json", "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=2)
        print(f"[{season}] status: {status}  ->  {run_dir}")

    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
