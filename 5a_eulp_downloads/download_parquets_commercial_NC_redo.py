import os
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from urllib.parse import quote
import sys
import requests
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pipeline_utils import load_config, resolve_work_path

# =========================
# Configuration
# =========================

cfg = load_config()
STATE = cfg['state']
SEASON = cfg['season']
DOWNLOAD_DATE = cfg.get('eulp_download_date', '20250330')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
PARQUET_DATA_ROOT = cfg.get('parquet_data_root', '../parquet_data')
if not os.path.isabs(PARQUET_DATA_ROOT):
    PARQUET_DATA_ROOT = os.path.abspath(os.path.join(REPO_ROOT, PARQUET_DATA_ROOT))

# States & case label
STATES_OF_INTEREST = [STATE]           # e.g. ["NC", "TX", ...]
CASE_ID = f"{DOWNLOAD_DATE}_comm_{STATE}"

# Dataset location
QUERY_YEAR = 2024
DATASET = "comstock_amy2018_release_1"
BUCKET = "oedi-data-lake"
ROOT_PREFIX = "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock"

# Upgrades to include (ComStock example from your script)
# SECOND LEVER: 8 upgrades here -> downloads are multiplied by 8. If downstream only
# needs baseline, set UPGRADES = [0] for an 8x cut. Left as-is pending confirmation.
UPGRADES = [0, 1, 2, 3, 8, 9, 19, 20]

# Read the Phase 4 FINAL SELECTION (the chosen representatives), NOT the _FILTERED_ set.
#   {STATE}_final_commercial.csv  -> the chosen representative buildings only.
# The old _FILTERED_ file held every matched building and over-downloaded.
# Final selection CSV is staged into the workspace by run_case.py copy step.
# Resolved via resolve_work_path at read time (see load_target_bldg_ids_for_state).

# Output folder
DOWNLOAD_DIR_TEMPLATE = os.path.join(PARQUET_DATA_ROOT, f"parquet_commercial_{CASE_ID}")

# Download throttling
CHUNK_SIZE = 100
REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_CHUNKS_SEC = 0.25

# Column filters applied to the metadata CSV.
# NOTE: we now read the Phase 4 *final selection* ({STATE}_final_commercial.csv),
# which already contains ONLY the chosen representative buildings. The previous
# _FILTERED_ file held ALL matched buildings and over-downloaded.
column_selection_case = {
    "State": STATES_OF_INTEREST,
}

# =========================
# Helpers
# =========================

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "oedi-s3-fetch/1.0"})
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"])
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def s3_list_objects(bucket, prefix, session=None, suffix=None):
    """
    List all keys under `prefix` using S3 ListObjectsV2 pagination.
    If `suffix` is provided, only return keys ending with it (e.g. ".parquet").
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

        for contents in root.findall("s3:Contents", ns):
            k = contents.find("s3:Key", ns).text
            if suffix is None or k.endswith(suffix):
                keys.append(k)

        is_trunc = root.find("s3:IsTruncated", ns)
        if is_trunc is not None and is_trunc.text == "true":
            token = root.find("s3:NextContinuationToken", ns).text
        else:
            break

    return keys

def build_state_prefix(year, dataset, upgrade, state):
    """
    .../timeseries_individual_buildings/by_state/upgrade=<u>/state=<STATE>/
    """
    return (
        f"{ROOT_PREFIX}/{year}/{dataset}/timeseries_individual_buildings/"
        f"by_state/upgrade={upgrade}/state={state}/"
    )

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def download_file(session, url, dest_path):
    with session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

# =========================
# Metadata -> target bldg_ids
# =========================

def load_target_bldg_ids_for_state(state, filter_dict):
    """
    Loads ./{STATE}_final_commercial.csv (the Phase 4 final selection)
    Applies filters in filter_dict and returns set of bldg_id (ints).
    """
    path = resolve_work_path("5a_eulp_downloads", f"{state}_final_commercial.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Metadata CSV not found: {path}")

    df = pd.read_csv(path)
    dff = df.copy()

    # Apply cumulative filters
    for col, values in filter_dict.items():
        if col in dff.columns:
            dff = dff[dff[col].isin(values)]
        else:
            print(f"Warning: Column '{col}' not found in {path}")

    if "bldg_id" not in dff.columns:
        raise KeyError(f"'bldg_id' not found in {path}")

    return set(pd.to_numeric(dff["bldg_id"], errors="coerce").dropna().astype(int).tolist())

# =========================
# Build list of URLs
# =========================

def build_parquet_urls(states, upgrades):
    """
    Returns list of (url, state, upgrade) tuples for selected states/upgrades
    whose filenames match bldg_id from metadata.
    """
    session = make_session()
    urls = []

    for state in states:
        # Sync filter to this state
        state_filter = deepcopy(column_selection_case)
        state_filter["State"] = [state]
        target_ids = load_target_bldg_ids_for_state(state, state_filter)
        print(f"{state}: {len(target_ids)} target bldg_id(s) loaded from metadata.")

        for up in upgrades:
            prefix = build_state_prefix(QUERY_YEAR, DATASET, up, state)
            print(f"Listing s3://{BUCKET}/{prefix}")
            keys = s3_list_objects(BUCKET, prefix, session=session, suffix=".parquet")

            # Filter keys by bldg_id parsed from filename "<bldg>-<upgrade>.parquet"
            for k in keys:
                fname = k.rsplit("/", 1)[-1]
                if not fname.endswith(".parquet"):
                    continue
                core = fname[:-8]  # strip ".parquet"
                parts = core.split("-", 1)
                if len(parts) != 2:
                    continue
                try:
                    bldg_id = int(parts[0])
                    up_id = int(parts[1])
                except ValueError:
                    continue

                if (bldg_id in target_ids) and (up_id == up):
                    urls.append((f"https://{BUCKET}.s3.amazonaws.com/{k}", state, up))

    return urls

# =========================
# Download
# =========================

def download_urls(urls, case_id):
    out_dir = DOWNLOAD_DIR_TEMPLATE.format(CASE_ID=case_id)
    ensure_dir(out_dir)
    session = make_session()

    # Small report by upgrade
    if urls:
        from collections import Counter
        cnt = Counter(up for _u, _s, up in [(u, s, up) for (u, s, up) in urls])
        print("Counts by upgrade:", dict(cnt))

    chunks = list(chunk_list(urls, CHUNK_SIZE))
    for i, chunk in enumerate(chunks, 1):
        print(f"Processing chunk {i}/{len(chunks)} (size={len(chunk)})...")
        for url, state, up in chunk:
            fname = url.rsplit("/", 1)[-1]
            dest = os.path.join(out_dir, fname)
            if os.path.exists(dest):
                continue
            try:
                download_file(session, url, dest)
            except Exception as e:
                print(f"Failed: {fname} -> {e}")
        time.sleep(SLEEP_BETWEEN_CHUNKS_SEC)

    print(f"Done. Files saved under: {out_dir}")

# =========================
# Main
# =========================

if __name__ == "__main__":
    start = time.time()
    urls = build_parquet_urls(STATES_OF_INTEREST, UPGRADES)
    print(f"Total URLs to download: {len(urls)}")
    download_urls(urls, CASE_ID)
    elapsed = time.time() - start
    print(f"{elapsed:.1f} seconds / {elapsed/60:.1f} minutes.")
