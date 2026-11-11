# -*- coding: utf-8 -*-
"""
test_caller_settings.py
-----------------------
Settings from a caller (run_case.py --settings): the merge of a settings file over the
repository's file with its strict keys, the check of the settings folder, load_config
under PIPELINE_SETTINGS_DIR, and run_case.py --dry-run with and without --settings.
The EULP release in data folder names: the parquet folder names and the Phase 1
metadata folder of a release other than the current one. Needs no SMART-DS/EULP data.

Run directly (no pytest needed): python tests/test_caller_settings.py
Or under pytest: pytest tests/test_caller_settings.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from pipeline_utils import (SETTINGS_ENV, check_settings_dir, load_config, merge_settings,  # noqa: E402
                            read_settings_file, settings_key_paths)
from pipeline_utils import (EULP_CURRENT_RELEASE, eulp_parquet_folder, eulp_release,  # noqa: E402
                            eulp_release_suffix)


def _stops(fn, *args):
    try:
        fn(*args)
    except SystemExit as e:
        return e.code == 1
    return False


def _ensure_local_yaml():
    """As in test_orchestrator_dry_run.py: a throwaway configs/local.yaml from the
    example when none exists, with eulp_metadata_root at an empty temporary folder."""
    local_path = os.path.join(REPO_ROOT, "configs", "local.yaml")
    example_path = os.path.join(REPO_ROOT, "configs", "local.yaml.example")
    if os.path.exists(local_path):
        return local_path, None
    with open(example_path, encoding="utf-8") as f:
        content = f.read()
    metadata_dir = tempfile.mkdtemp()
    content = re.sub(r"(?m)^eulp_metadata_root:.*$",
                     f'eulp_metadata_root: "{Path(metadata_dir).as_posix()}"', content)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    return local_path, metadata_dir


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def test_merge_nested_list_scalar():
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 3, "e": "x"}
    merged = merge_settings(base, {"a": {"c": [9]}, "d": None}, "pipeline_config.yaml")
    assert merged == {"a": {"b": 1, "c": [9]}, "d": None, "e": "x"}
    assert base == {"a": {"b": 1, "c": [1, 2]}, "d": 3, "e": "x"}
    assert settings_key_paths({"a": {"c": [9]}, "d": None}) == ["a.c", "d"]


def test_merge_mapping_against_scalar_stops():
    assert _stops(merge_settings, {"a": {"b": 1}}, {"a": 2}, "local.yaml")
    assert _stops(merge_settings, {"a": 2}, {"a": {"b": 1}}, "topology_registry.yaml")


def test_merge_strict_keys():
    cfg = load_config(os.path.join(REPO_ROOT, "pipeline_config.yaml"))
    assert _stops(merge_settings, dict(cfg), {"ev_work_shar_case": "low"}, "pipeline_config.yaml")
    assert _stops(merge_settings, dict(cfg), {"der_sizing": {"storage_rul": "simple"}}, "pipeline_config.yaml")
    with open(os.path.join(REPO_ROOT, "configs", "defaults.yaml"), encoding="utf-8") as f:
        defaults = yaml.safe_load(f)
    assert _stops(merge_settings, defaults, {"phase_ordr": []}, "defaults.yaml")
    merged = merge_settings(defaults, {"base_env": {"NEW_VAR": "1"}}, "defaults.yaml")
    assert merged["base_env"]["NEW_VAR"] == "1"
    assert merged["base_env"]["PYTHONHASHSEED"] == "0"
    with open(os.path.join(REPO_ROOT, "configs", "topology_registry.yaml"), encoding="utf-8") as f:
        topo = yaml.safe_load(f)
    new = dict(topo["topologies"]["NC_GSO_urban_uhs13_1247"])
    merged = merge_settings(topo, {"topologies": {"NC_GSO_copy": new}}, "topology_registry.yaml")
    assert merged["topologies"]["NC_GSO_copy"] == new
    assert set(merged["topologies"]) == set(topo["topologies"]) | {"NC_GSO_copy"}


def test_empty_file_changes_nothing():
    folder = tempfile.mkdtemp()
    try:
        _write(folder, "defaults.yaml", "")
        override = read_settings_file(folder, "defaults.yaml")
        assert override == {}
        assert read_settings_file(folder, "local.yaml") is None
        base = {"a": {"b": 1}}
        assert merge_settings(base, override, "defaults.yaml") == base
        _write(folder, "local.yaml", "- a\n- b\n")
        assert _stops(read_settings_file, folder, "local.yaml")
    finally:
        shutil.rmtree(folder)


def test_check_settings_dir():
    folder = tempfile.mkdtemp()
    try:
        assert _stops(check_settings_dir, os.path.join(folder, "missing"))
        _write(folder, "README.txt", "notes")
        _write(folder, "local.yaml", "runs_root: runs\n")
        _write(folder, "defaults.yaml", "")
        assert check_settings_dir(folder) == ["defaults.yaml", "local.yaml"]
        _write(folder, "pipeline_config.yml", "random_seed: 1\n")
        assert _stops(check_settings_dir, folder)
    finally:
        shutil.rmtree(folder)


def test_load_config_with_settings_dir():
    folder = tempfile.mkdtemp()
    saved = os.environ.pop(SETTINGS_ENV, None)
    try:
        plain = load_config()
        _write(folder, "pipeline_config.yaml",
               "ev_work_share_case: low\nder_sizing: {storage_rule: simple}\n")
        os.environ[SETTINGS_ENV] = folder
        cfg = load_config()
        assert cfg["ev_work_share_case"] == "low"
        assert cfg["der_sizing"]["storage_rule"] == "simple"
        for key in plain:
            if key == "ev_work_share_case":
                continue
            if key == "der_sizing":
                assert {k: v for k, v in cfg[key].items() if k != "storage_rule"} == \
                    {k: v for k, v in plain[key].items() if k != "storage_rule"}
                continue
            assert cfg[key] == plain[key], key
        assert set(cfg) == set(plain)
        del os.environ[SETTINGS_ENV]
        assert load_config() == plain
    finally:
        if saved is None:
            os.environ.pop(SETTINGS_ENV, None)
        else:
            os.environ[SETTINGS_ENV] = saved
        shutil.rmtree(folder)


def test_dry_run_with_and_without_settings():
    local_path, metadata_dir = _ensure_local_yaml()
    folder = tempfile.mkdtemp()
    env = {k: v for k, v in os.environ.items() if k != SETTINGS_ENV}
    case_path = os.path.join(REPO_ROOT, "configs", "cases", "NC_GSO_urban__NC.yaml")
    try:
        _write(folder, "donor_registry.yaml", 'donors: {NC: {eulp_download_date: "20991231"}}\n')
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "run_case.py"), "--case", case_path,
             "--all", "--season", "summer", "--dry-run", "--settings", folder],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        lines = [ln.strip() for ln in proc.stdout.splitlines()]
        assert f"{SETTINGS_ENV}={Path(folder).resolve().as_posix()}" in lines, proc.stdout
        assert "PIPELINE_EULP_DOWNLOAD_DATE=20991231" in lines, proc.stdout
        assert "settings donor_registry.yaml: donors.NC.eulp_download_date" in lines, proc.stdout
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "run_case.py"), "--case", case_path,
             "--all", "--season", "summer", "--dry-run"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert SETTINGS_ENV not in proc.stdout
        assert "PIPELINE_EULP_DOWNLOAD_DATE=20250330" in proc.stdout
    finally:
        shutil.rmtree(folder)
        if metadata_dir:
            os.remove(local_path)
            os.rmdir(metadata_dir)


def test_eulp_parquet_folder():
    current = {"eulp_download_date": "20250330", "state": "NC",
               "eulp_release": {"residential": "resstock_tmy3_release_2",
                                "commercial": "comstock_amy2018_release_1",
                                "residential_year": 2024, "commercial_year": 2024}}
    assert eulp_parquet_folder(current, "residential") == "parquet_residential_short_20250330_NC"
    assert eulp_parquet_folder(current, "commercial") == "parquet_commercial_20250330_comm_NC"
    amy = dict(current, eulp_release=dict(current["eulp_release"], residential="resstock_amy2018_release_2"))
    assert eulp_parquet_folder(amy, "residential").endswith("_2024_resstock_amy2018_release_2")
    assert eulp_parquet_folder(amy, "commercial") == "parquet_commercial_20250330_comm_NC"
    later = dict(current, eulp_release=dict(current["eulp_release"], residential_year=2025))
    assert eulp_release_suffix(later, "residential") == "_2025_resstock_tmy3_release_2"
    no_year = dict(current, eulp_release={"residential": "resstock_tmy3_release_2"})
    assert eulp_release(no_year, "residential") == (2024, "resstock_tmy3_release_2")
    assert eulp_release_suffix(no_year, "residential") == ""
    assert eulp_release(load_config(os.path.join(REPO_ROOT, "pipeline_config.yaml")), "residential") == \
        EULP_CURRENT_RELEASE["residential"]


def test_planned_files_for_release_folder():
    sys.path.insert(0, os.path.join(REPO_ROOT, "1_data_provenance", "src"))
    from eulp_metadata.build import DEFAULT_CONFIG, load_workflow, planned_files_for_dataset
    config = load_workflow(DEFAULT_CONFIG)
    cluster = {"states": ["NC"], "residential_folder_groups": ["residential_tmy3"],
               "residential_upgrades": ["baseline"]}
    root = tempfile.mkdtemp()
    settings = tempfile.mkdtemp()
    saved = {k: os.environ.get(k) for k in (SETTINGS_ENV, "PIPELINE_EULP_METADATA_ROOT")}
    try:
        _write(settings, "pipeline_config.yaml", "eulp_release: {residential: resstock_amy2018_release_2}\n")
        os.environ[SETTINGS_ENV] = settings
        os.environ["PIPELINE_EULP_METADATA_ROOT"] = root
        assert _stops(planned_files_for_dataset, config, cluster, "residential")
        folder = os.path.join(root, "Metadata_NC_Residential_2024_resstock_amy2018_release_2")
        os.makedirs(folder)
        _write(folder, "NC_baseline_metadata_and_annual_results.csv", "bldg_id\n1\n")
        files = planned_files_for_dataset(config, cluster, "residential")
        assert [f["file"] for f in files] == [
            "Metadata_NC_Residential_2024_resstock_amy2018_release_2/NC_baseline_metadata_and_annual_results.csv"]
        del os.environ[SETTINGS_ENV]
        files = planned_files_for_dataset(config, cluster, "residential")
        assert files == [{"state": "NC", "group": "residential_tmy3", "folder": "Metadata_NC_Residential",
                          "exists": False, "file": None}]
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(root)
        shutil.rmtree(settings)


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")
    print(f"ALL {len(tests)} TESTS PASSED")
