
#!/usr/bin/env python3
import os
import re
import csv
import sys
import argparse
import pickle
from pathlib import Path

if len(sys.argv) > 1:
    root = Path(sys.argv[1])
else:
    root = Path("circuits_plain_format")

root = root.resolve()
print(f"[INFO] Root: {root}")

if not root.exists() or not root.is_dir():
    print(f"[ERROR] Not a directory: {root}")
    sys.exit(2)

# Regex for daily=VALUE (value can be "quoted", 'quoted', or bare until whitespace/comment)
RE_DAILY = re.compile(r'(?i)\byearly\s*=\s*("([^"]+)"|\'([^\']+)\'|([^\s!]+))')

'''
These files have a yearly= defition, but notably we are looking for a daily= definition.
'''

circuits = [d for d in root.iterdir() if d.is_dir()]
circuits.sort(key=lambda p: p.name.lower())

if not circuits:
    print("[WARN] No circuit subdirectories found.")
    sys.exit(0)

total = 0
for cdir in circuits:
    circuit_name = cdir.name
    loads_path = None

    # Prefer "Loads.dss" case-insensitive in the circuit folder
    for p in cdir.iterdir():
        if p.is_file() and p.name.lower() == "loads.dss":
            loads_path = p
            break

    # Fallback: any *.dss with "loads" in the name
    if loads_path is None:
        for p in cdir.glob("*.dss"):
            if "loads" in p.name.lower():
                loads_path = p
                break

    if loads_path is None:
        print(f"[SKIP] {circuit_name}: Loads.dss not found")
        continue

    # Parse daily= tokens
    daily_names = set()
    try:
        with loads_path.open("r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.rstrip("\n")

                # Strip comments: '!' and '//' (take the earliest if both present)
                cut_idx = None
                bang = line.find('!')
                slashes = line.find('//')
                if bang != -1 and slashes != -1:
                    cut_idx = min(bang, slashes)
                elif bang != -1:
                    cut_idx = bang
                elif slashes != -1:
                    cut_idx = slashes
                if cut_idx is not None:
                    line = line[:cut_idx]

                line = line.strip()
                # print(line)
                if not line:
                    continue

                # Find all daily=... occurrences in the line
                for m in RE_DAILY.finditer(line):
                    token = m.group(2) or m.group(3) or m.group(4) or ""
                    token = token.strip().strip('"').strip("'")
                    if token and token.lower() not in ("none", "null"):
                        daily_names.add(token)
    except Exception as e:
        print(f"[ERROR] {circuit_name}: reading {loads_path} failed: {e}")
        continue

    # print('check these pickles')
    # sys.exit()

    # Save per-circuit pickle in the circuit folder
    out_path = cdir / f"daily_list_set_{circuit_name}.pkl"
    daily_names_list = list(daily_names)
    try:
        with out_path.open("wb") as fh:
            pickle.dump(daily_names_list, fh, protocol=4)
        print(f"[OK] {circuit_name}: {len(daily_names)} names -> {out_path}")
        total += 1
    except Exception as e:
        print(f"[ERROR] {circuit_name}: failed to write {out_path}: {e}")

print(f"[DONE] Pickles written for {total} circuit(s).")

