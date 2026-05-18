# -*- coding: utf-8 -*-
"""
Created on Tue Nov 11 19:28:35 2025

@author: luisfernando
"""

#!/usr/bin/env python3
# Place this file inside the 8_instantiate_circuits_FILTER folder and run it.
# It will use its own directory as the root.

import sys
import re
import csv
from pathlib import Path

# --- Config (change if you need different behavior) ---
# Regex for folders like: uhs0_1247_circuit_1_0
FOLDER_REGEX = r"^uhs\d+_\d+_circuit_\d+_\d+$"
# Minimum required size for m1/m2 CSVs
MIN_SIZE_BYTES = 1024  # 1 KiB = 1024 bytes
# Robust token match for "m1"/"m2" that won't hit "m12", "m20", etc.
M1_TOKEN = re.compile(r'(^|[^A-Za-z0-9])m1([^A-Za-z0-9]|$)', re.IGNORECASE)
M2_TOKEN = re.compile(r'(^|[^A-Za-z0-9])m2([^A-Za-z0-9]|$)', re.IGNORECASE)
# ------------------------------------------------------

if __name__ == "__main__":
    # Use the script's directory as the root (safe even if you run it from elsewhere)
    root = Path(__file__).resolve().parent
    pattern = re.compile(FOLDER_REGEX, re.IGNORECASE)

    results = []
    failing = []

    # Iterate subfolders that match the pattern
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if not pattern.match(name):
            continue

        mcd = child / "ModifiedCircuitData"
        status = "PASS"
        reasons = []

        if not mcd.is_dir():
            status = "FAIL"
            reasons.append("Missing ModifiedCircuitData/")
        else:
            # Only look at CSV files directly under ModifiedCircuitData (not recursive)
            csv_files = [p for p in mcd.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]

            # Partition by m1/m2 using robust token search (so 'm12' won't count as 'm1')
            m1_files = [p for p in csv_files if M1_TOKEN.search(p.name)]
            m2_files = [p for p in csv_files if M2_TOKEN.search(p.name)]

            # Enforce exactly one m1 and one m2
            if len(m1_files) == 0:
                status = "FAIL"
                reasons.append("No m1 CSV found.")
            elif len(m1_files) > 1:
                status = "FAIL"
                reasons.append("Multiple m1 CSVs found: " + ", ".join(p.name for p in m1_files))

            if len(m2_files) == 0:
                status = "FAIL"
                reasons.append("No m2 CSV found.")
            elif len(m2_files) > 1:
                status = "FAIL"
                reasons.append("Multiple m2 CSVs found: " + ", ".join(p.name for p in m2_files))

            # Size checks (> 1 KiB)
            if len(m1_files) == 1:
                m1_size = m1_files[0].stat().st_size
                if m1_size <= MIN_SIZE_BYTES:
                    status = "FAIL"
                    reasons.append(f"m1 CSV too small ({m1_files[0].name}: {m1_size} B ≤ {MIN_SIZE_BYTES} B).")

            if len(m2_files) == 1:
                m2_size = m2_files[0].stat().st_size
                if m2_size <= MIN_SIZE_BYTES:
                    status = "FAIL"
                    reasons.append(f"m2 CSV too small ({m2_files[0].name}: {m2_size} B ≤ {MIN_SIZE_BYTES} B).")

        if status == "FAIL":
            failing.append(name)

        results.append({
            "circuit_folder": name,
            "status": status,
            "reasons": "; ".join(reasons) if reasons else ""
        })

    # Write report files next to the script
    report_path = root / "circuit_check_report.csv"
    failures_list = root / "failing_circuits.txt"

    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["circuit_folder", "status", "reasons"])
        writer.writeheader()
        writer.writerows(results)

    if failing:
        failures_list.write_text("\n".join(failing), encoding="utf-8")
        print(f"FAIL: {len(failing)} circuit folder(s) did not meet the requirement.")
        print(f"- Report: {report_path}")
        print(f"- Failing list: {failures_list}")
        for n in failing:
            print(f"  - {n}")
        sys.exit(1)
    else:
        print("PASS: all matching circuit folders have m1 and m2 CSVs > 1 KiB.")
        print(f"Report: {report_path}")
        sys.exit(0)
