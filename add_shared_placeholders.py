#!/usr/bin/env python3
"""Add shared NC daily_parquets structure + parquet_data placeholder to archive."""
from pathlib import Path

SRC = Path(r"C:\Users\luisfernando\Dropbox\1_RESEARCH\1_FOCUS_PhD"
           r"\Conferences\Conference_EMH_2025_Ottawa\dist\daily_parquets")
DST = Path(r"C:\Users\luisfernando\Desktop\phd_workspace"
           r"\dss-eulp-coupling\archive\daily_parquets")
PD  = Path(r"C:\Users\luisfernando\Desktop\phd_workspace"
           r"\dss-eulp-coupling\archive\parquet_data")

count = 0
for d in sorted(SRC.iterdir()):
    if d.is_dir():
        p = DST / d.name
        p.mkdir(parents=True, exist_ok=True)
        (p / ".gitkeep").write_text("# NC EULP base parquets - excluded from Git\n")
        count += 1
print(f"daily_parquets: {count} feeder dirs created")

PD.mkdir(exist_ok=True)
(PD / ".gitkeep").write_text("# Shared parquet data - excluded from Git\n")
print("parquet_data: placeholder created")
