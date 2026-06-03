# -*- coding: utf-8 -*-
"""
Created on Sun Nov  9 21:51:16 2025

@author: luisfernando
"""

import os
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from urllib.parse import quote
import sys
import requests
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config

# -------------------------
# Configuration
# -------------------------

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
DOWNLOAD_DATE = cfg.get('eulp_download_date', '20250330')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
PARQUET_DATA_ROOT = cfg.get('parquet_data_root', '../parquet_data')
if not os.path.isabs(PARQUET_DATA_ROOT):
    PARQUET_DATA_ROOT = os.path.abspath(os.path.join(REPO_ROOT, PARQUET_DATA_ROOT))

# Match your use case (MN from your link); change as needed
STATES_OF_INTEREST = [STATE]         # e.g. ["NC", "TX", ...]
CASE_ID = f"{DOWNLOAD_DATE}_{STATE}"    # folder suffix for downloads
QUERY_YEAR = 2024
DATASET = "resstock_tmy3_release_2" # or "comstock_amy2018_release_1"
BUCKET = "oedi-data-lake"
ROOT_PREFIX = "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock"

# Which upgrades to include (file names are <bldg_id>-<upgrade>.parquet)
# SECOND LEVER: this multiplies downloads by len(UPGRADES). If downstream
# (Phase 5b/5c) only consumes baseline profiles, set this to [0] for a further 4x cut.
# Left as-is pending confirmation that nothing downstream reads upgrades 1/2/4.
UPGRADES = [0, 1, 2, 4]

# Column filter applied to the metadata CSV.
# NOTE: we now read the Phase 4 *final selection* ({STATE}_final_residential.csv),
# which already contains ONLY the chosen representative buildings. The previous
# _FILTERED_ file held ALL matched buildings (~17k) and caused a massive over-download.
column_selection_case = {
    'State': STATES_OF_INTEREST,
}

# Read the Phase 4 FINAL SELECTION (the chosen representatives), NOT the _FILTERED_ set.
#   {STATE}_final_residential.csv  -> ~hundreds of buildings (one per chosen parquet)
# The old _FILTERED_ file held every matched building and over-downloaded ~80x.
METADATA_CSV_TEMPLATE = "./{STATE}_final_residential.csv"

# Download params
DOWNLOAD_DIR_TEMPLATE = os.path.join(PARQUET_DATA_ROOT, f"parquet_residential_short_{CASE_ID}")
CHUNK_SIZE = 50              # split URL list into chunks to avoid burstiness
REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_CHUNKS_SEC = 0.25

# print('get here')
# sys.exit()

# -------------------------
# Utilities
# -------------------------

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def make_session():
    # Basic session; customize with retries if desired
    s = requests.Session()
    s.headers.update({"User-Agent": "oedi-s3-fetch/1.0"})
    return s

def s3_list_common_prefixes(bucket, prefix, delimiter="/", session=None):
    """
    Returns a list of 'folder-like' prefixes directly under `prefix`.
    Uses ListObjectsV2 with delimiter to emulate directories.
    """
    if session is None:
        session = make_session()
    base = f"https://{bucket}.s3.amazonaws.com/?list-type=2&delimiter={quote(delimiter)}&prefix={quote(prefix)}"
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    results = []
    token = None
    while True:
        url = base if token is None else f"{base}&continuation-token={quote(token)}"
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for cp in root.findall("s3:CommonPrefixes", ns):
            p = cp.find("s3:Prefix", ns).text
            results.append(p)
        trunc = root.find("s3:IsTruncated", ns)
        if trunc is not None and trunc.text == "true":
            token = root.find("s3:NextContinuationToken", ns).text
        else:
            break
    return results

def s3_list_objects(bucket, prefix, session=None, suffix=None):
    """
    Returns a list of Keys under prefix. If suffix is given, filters by it.
    """
    if session is None:
        session = make_session()
    base = f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={quote(prefix)}"
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    keys = []
    token = None
    while True:
        url = base if token is None else f"{base}&continuation-token={quote(token)}"
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for c in root.findall("s3:Contents", ns):
            k = c.find("s3:Key", ns).text
            if not suffix or k.endswith(suffix):
                keys.append(k)
        trunc = root.find("s3:IsTruncated", ns)
        if trunc is not None and trunc.text == "true":
            token = root.find("s3:NextContinuationToken", ns).text
        else:
            break
    return keys

def build_state_prefix(year, dataset, upgrade, state):
    """
    Returns the exact S3 prefix used by the viewer for a given state and upgrade.
    For resstock/comstock it's .../by_state/upgrade=<n>/state=<XX>/
    """
    return (
        f"{ROOT_PREFIX}/{year}/{dataset}/timeseries_individual_buildings/"
        f"by_state/upgrade={upgrade}/state={state}/"
    )

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def download_file(session, url, dest_path):
    # Stream to avoid loading entire file in memory
    with session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

# -------------------------
# 1) Derive target bldg_id per state from your metadata + filters
# -------------------------

def load_target_bldg_ids_for_state(state, filter_dict):
    """
    Loads ./{STATE}_final_residential.csv (the Phase 4 final selection)
    Applies the column filters in filter_dict and returns a set of bldg_id.
    """
    path = METADATA_CSV_TEMPLATE.format(STATE=state)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Metadata CSV not found: {path}")
    df = pd.read_csv(path)
    dff = df.copy()

    # Apply cumulative filters (same pattern you used)
    for col, values in filter_dict.items():
        if col in dff.columns:
            dff = dff[dff[col].isin(values)]
        else:
            # Warn but continue (your original script printed a warning)
            print(f"Warning: Column '{col}' not found in {path}")

    # Expect presence of bldg_id column
    if "bldg_id" not in dff.columns:
        raise KeyError(f"'bldg_id' not found in {path}")
    return set(dff["bldg_id"].astype(int).tolist())

# -------------------------
# 2) Build URL list by listing S3 and filtering by bldg_id
# -------------------------

def build_parquet_urls(states, upgrades):
    """
    Returns list of (url, state) tuples for selected states/upgrades
    whose file name matches bldg_id in metadata.
    """
    session = make_session()
    urls = []
    for state in states:
        # Sync the metadata filter to this state
        # (Your original pattern applies the same dict; make sure 'State':[state] is set)
        filter_for_state = deepcopy(column_selection_case)
        filter_for_state['State'] = [state]

        target_ids = load_target_bldg_ids_for_state(state, filter_for_state)
        print(f"{state}: {len(target_ids)} target bldg_id(s) loaded from metadata.")

        # We only need to list once for upgrade=0 and then derive others,
        # but listing each upgrade explicitly is more robust and still fast.
        for up in upgrades:
            prefix = build_state_prefix(QUERY_YEAR, DATASET, up, state)
            print(f"Listing S3 keys under: s3://{BUCKET}/{prefix}")
            keys = s3_list_objects(BUCKET, prefix, session=session, suffix=".parquet")

            # Filter by filename -> bldg_id
            for k in keys:
                fname = k.rsplit("/", 1)[-1]          # "<bldg>-<up>.parquet"
                base = fname[:-8] if fname.endswith(".parquet") else fname
                # Expect pattern "<bldg>-<upgrade>"
                try:
                    bldg_str, up_str = base.split("-", 1)
                    bldg_id = int(bldg_str)
                    up_id = int(up_str)
                except Exception:
                    continue  # skip any unexpected entries

                if (bldg_id in target_ids) and (up_id == up):
                    urls.append((f"https://{BUCKET}.s3.amazonaws.com/{k}", state))

    return urls

# -------------------------
# 3) Download with chunking
# -------------------------

def download_urls(urls, case_id):
    out_dir = DOWNLOAD_DIR_TEMPLATE.format(CASE_ID=case_id)
    ensure_dir(out_dir)
    session = make_session()

    # Partition work to avoid overwhelming the endpoint
    chunks = list(chunk_list(urls, CHUNK_SIZE))
    for i, chunk in enumerate(chunks, 1):
        print(f"Processing chunk {i}/{len(chunks)} (size={len(chunk)})...")
        for url, state in chunk:
            # Filename from URL
            filename = url.rsplit("/", 1)[-1]
            dest_path = os.path.join(out_dir, filename)
            if os.path.exists(dest_path):
                # Skip if already downloaded
                continue
            try:
                download_file(session, url, dest_path)
                # Optional: print(f"Downloaded {filename}")
            except Exception as e:
                print(f"Failed: {filename} -> {e}")
        time.sleep(SLEEP_BETWEEN_CHUNKS_SEC)

    print(f"Done. Files saved under: {out_dir}")

# -------------------------
# Main
# -------------------------

if __name__ == "__main__":
    start = time.time()
    urls = build_parquet_urls(STATES_OF_INTEREST, UPGRADES)
    print(f"Total URLs to download: {len(urls)}")
    download_urls(urls, CASE_ID)
    elapsed = time.time() - start
    print(f"{elapsed:.1f} seconds / {elapsed/60:.1f} minutes.")

