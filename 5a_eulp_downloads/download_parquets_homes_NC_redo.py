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

# -------------------------
# Configuration
# -------------------------

# Match your use case (MN from your link); change as needed
STATES_OF_INTEREST = ["NC"]         # e.g. ["NC", "TX", ...]
CASE_ID = "20250330_NC"    # folder suffix for downloads
QUERY_YEAR = 2024
DATASET = "resstock_tmy3_release_2" # or "comstock_amy2018_release_1"
BUCKET = "oedi-data-lake"
ROOT_PREFIX = "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock"

# Which upgrades to include (file names are <bldg_id>-<upgrade>.parquet)
UPGRADES = [0, 1, 2, 4]

# Your original column filter (keep/edit as needed)
column_selection_case = {
    'State':['NC'],
    'bldg_id':[
    280535, 529030, 344090, 457130, 51248, 97064, 279056, 438217, 156448, 164952, 35477, 420203, 167400, 218062,
    72447, 367703, 84697, 481382, 91378, 97925, 178981, 527921, 17111, 59917, 261886, 220549, 178093, 6026,
    527501, 432723, 319515, 359965, 235585, 546364, 485394, 262127, 529033, 493987, 407787, 344018, 535227, 139348,
    263649, 239844, 379231, 313792, 534332, 222362, 435560, 72777, 35373, 264802, 67210, 193963, 68118, 462831,
    287287, 8782, 9317, 267097, 265199, 352076, 136435, 38417, 259129, 419312, 286489, 92439, 517977, 118125,
    247367, 457116, 546233, 460644, 404686, 130527, 478918, 354365, 404797, 337045, 250118, 98294, 98674, 15396,
    129565, 244868, 534901, 3287, 15650, 107647, 428637, 222728, 200756, 517627, 240691, 454538, 202962, 451679,
    328107, 282264, 154971, 126100, 73055, 334241, 88537, 36597, 464775, 467570, 247612, 116266, 194672, 363975,
    529756, 203533, 329979, 283333, 413132, 53909, 212677, 45392, 532168, 507754, 199135, 507902, 348156, 473225,
    521039, 174039, 387763, 518840, 381400, 544432, 60154, 246233, 64957, 70635, 447079, 502536, 97124, 434770,
    287291, 188940, 203311, 189739, 168854, 138890, 212492, 545651, 479216, 199058, 108419, 401346, 111958, 417893,
    136108, 23436, 472351, 478693, 130213, 190125, 478171, 446954, 143236, 204029, 216945, 388824, 62209, 266419,
    394308, 119047, 80170, 390007, 347276, 231804, 204241, 118222, 455247, 272261, 296854, 396519, 154882, 119211,
    487394, 486640, 65464, 257869, 232311, 272431, 69383, 121670, 94364, 162506, 17134, 258869, 660, 173600,
    217789, 501337, 234287, 58966, 224061, 83078, 43483, 213633, 86151, 511168, 34965, 26565, 492347, 448472,
    114512, 509702, 354097, 330728, 101087, 528778, 247582, 457829, 414074, 30486, 178112, 224275, 10560, 179307,
    432679, 402350, 324000, 458193, 491844, 341075, 200878, 390095, 373084, 260245, 98055, 288150, 83997, 3268,
    123790, 289532, 321144, 206334, 400900, 502706, 19803, 476516, 66479, 524421, 306028, 522637, 282044, 15373,
    328007, 307599, 156896, 248378, 323108, 245135, 183001, 6456, 173686, 283447, 31765, 430363, 44529, 11668,
    30407, 217842, 375123, 24785, 399644, 45508, 491298, 326186, 444657, 128919, 196063, 397370, 4326, 232001,
    197032, 98514, 440300, 158466, 284740, 43831, 73164, 68408, 350461, 430198, 151208, 277033, 9326, 227698,
    173139, 523510, 117315, 189705, 132061, 165855, 464019, 167987, 441994, 123009, 419799, 457181, 19256, 441337,
    136069, 464736, 371618, 81558, 83034, 265788, 150612, 75554, 409622, 269518, 80629, 302888, 77448, 340504,
    367862, 326128, 466863, 287519, 359000, 422987, 480467, 75643, 165446, 455102, 489128, 524791, 38621, 197962,
    199237, 481022, 196782, 120437, 33321, 37802, 454355, 279058, 179415, 391643, 467343, 417792, 253062, 55743,
    365297, 130368, 345074, 327027, 321381, 265915, 401881, 367039, 499540, 497563, 299351, 323952, 79083, 537198,
    19424, 444115, 549881, 342312, 401468, 6626, 204366, 224885, 323480, 293010, 302499, 243792, 336459, 21154,
    388024, 62198, 376022, 104347, 395696, 19595, 384776, 126000
]}

# Where to read your prefiltered metadata CSVs per state (same pattern you used)
# e.g., ./residential_data_SELECT_STATES_FILTERED_MN.csv
METADATA_CSV_TEMPLATE = "./residential_data_SELECT_STATES_FILTERED_NC.csv"

# Download params
DOWNLOAD_DIR_TEMPLATE = f"./parquet_residential_short_{CASE_ID}"
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
    Loads ./residential_data_SELECT_STATES_FILTERED_{STATE}.csv
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

