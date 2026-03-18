# -*- coding: utf-8 -*-
"""
Created on Sat Nov  8 15:50:05 2025

@author: luisfernando
"""

# -*- coding: utf-8 -*-
# Procedural feeder discovery + flat copy into ./circuits_plain
import os, sys, shutil
from pathlib import Path

# --- Paths & knobs ---
try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path(".").resolve()

SMARTDS_ROOT = (BASE_DIR / '..' / '3_smartds').resolve()
CIRCUITS_PLAIN_DIR = (BASE_DIR / 'circuits_plain_format').resolve()
CIRCUITS_PLAIN_DIR.mkdir(exist_ok=True)

MAX_FEEDERS = None  # set to an int to limit during testing

# =========================================
# === Discover nested SMART-DS feeders  ===
# =========================================
feeders = []
if not SMARTDS_ROOT.exists():
    sys.stderr.write(f"SMART-DS root not found: {SMARTDS_ROOT}\n")
    sys.exit(1)

for sub in sorted(SMARTDS_ROOT.iterdir()):
    if not sub.is_dir() or not sub.name.startswith('uhs'):
        continue
    for child in sorted(sub.iterdir()):
        if not child.is_dir():
            continue
        # must contain Loads + LoadShapes
        try:
            names = [nm.lower() for nm in os.listdir(child)]
        except PermissionError:
            continue
        if ('loads.dss' in names) and ('loadshapes.dss' in names):
            feeders.append(child)

if MAX_FEEDERS:
    feeders = feeders[:MAX_FEEDERS]

# =========================================
# === Copy feeders into ./circuits_plain ===
# =========================================
for p in feeders:
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

