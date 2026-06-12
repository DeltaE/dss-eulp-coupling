# -*- coding: utf-8 -*-
"""
Created on Sat Nov  8 15:50:05 2025

@author: luisfernando
"""

# -*- coding: utf-8 -*-
# Procedural feeder discovery + flat copy into ./circuits_plain
import json
import os, sys, shutil
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_config_path, resolve_work_path

# --- Paths & knobs ---
try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path(".").resolve()

cfg = load_config()
STATE = cfg["state"]
SMARTDS_ROOT = resolve_config_path(cfg.get("smart_ds_root", "../3_smartds"))
CIRCUITS_PLAIN_DIR = Path(resolve_work_path("2_circuit_matching", "circuits_plain_format"))
CIRCUITS_PLAIN_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_PATH = resolve_config_path(cfg.get("feeder_registry_path", "feeder_registry.json"))

MAX_FEEDERS = cfg.get("max_feeders")
if MAX_FEEDERS is not None:
    MAX_FEEDERS = int(MAX_FEEDERS)


def has_required_dss_files(path):
    try:
        names = {nm.lower() for nm in os.listdir(path)}
    except PermissionError:
        return False
    return "loads.dss" in names and "loadshapes.dss" in names


def discover_feeders(root):
    candidates = [p for p in root.rglob("*") if p.is_dir()]
    candidates.sort(key=lambda p: p.relative_to(root).as_posix().lower())
    return [p for p in candidates if has_required_dss_files(p)]


def make_registry_entry(circuit_id, feeder_path, flat_dir):
    feeder_name = feeder_path.name
    return {
        "circuit_id": circuit_id,
        "circuit": f"circuit_{circuit_id}",
        "substation": feeder_path.parent.name,
        "feeder_name": feeder_name,
        "original_path": feeder_path.relative_to(SMARTDS_ROOT).as_posix() + "/",
        "flat_dir": flat_dir + "/",
    }

# =========================================
# === Discover nested SMART-DS feeders  ===
# =========================================
if not SMARTDS_ROOT.exists():
    sys.stderr.write(f"SMART-DS root not found: {SMARTDS_ROOT}\n")
    sys.exit(1)

feeders = discover_feeders(SMARTDS_ROOT)

if MAX_FEEDERS is not None:
    feeders = feeders[:MAX_FEEDERS]

# =========================================
# === Copy feeders into ./circuits_plain ===
# =========================================
registry_entries = []
for circuit_id, p in enumerate(feeders, start=1):
    # FLAT destination: ./circuits_plain/<feeder_name>
    feeder_name = p.name
    dest = CIRCUITS_PLAIN_DIR / feeder_name

    # simple collision guard: <name>__2, __3, ...
    if dest.exists():
        i = 2
        while (CIRCUITS_PLAIN_DIR / f"{feeder_name}__{i}").exists():
            i += 1
        dest = CIRCUITS_PLAIN_DIR / f"{feeder_name}__{i}"

    # copy, overwriting if Python >= 3.8; otherwise remove first
    try:
        shutil.copytree(p, dest, dirs_exist_ok=True)       # Py 3.8+
    except TypeError:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(p, dest)
    except Exception as e:
        sys.stderr.write(f"Failed to copy '{p}' -> '{dest}': {e}\n")
        sys.exit(2)

    registry_entries.append(make_registry_entry(circuit_id, p, dest.name))

registry = {
    "state": STATE,
    "smart_ds_root": str(SMARTDS_ROOT),
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "feeders": registry_entries,
    "circuit_name_map": {
        entry["feeder_name"]: entry["circuit"] for entry in registry_entries
    },
    "reverse_circuit_map": {
        entry["circuit"]: entry["feeder_name"] for entry in registry_entries
    },
}

REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
with REGISTRY_PATH.open("w", encoding="utf-8") as f:
    json.dump(registry, f, indent=2)
    f.write("\n")

print(f"Copied {len(registry_entries)} feeders into {CIRCUITS_PLAIN_DIR}")
print(f"Wrote feeder registry: {REGISTRY_PATH}")

