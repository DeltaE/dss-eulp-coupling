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

# =========================
# Configuration
# =========================

# States & case label
STATES_OF_INTEREST = ["NC"]           # e.g. ["NC", "TX", ...]
CASE_ID = "20250330_comm_NC"

# Dataset location
QUERY_YEAR = 2024
DATASET = "comstock_amy2018_release_1"
BUCKET = "oedi-data-lake"
ROOT_PREFIX = "nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock"

# Upgrades to include (ComStock example from your script)
UPGRADES = [0, 1, 2, 3, 8, 9, 19, 20]

# Your per-state metadata CSVs (same naming pattern you use today)
# Example: ./commercial_data_SELECT_STATES_FILTERED_NC.csv
METADATA_CSV_TEMPLATE = "./commercial_data_SELECT_STATES_FILTERED_NC.csv"

# Output folder
DOWNLOAD_DIR_TEMPLATE = f"./parquet_commercial_{CASE_ID}"

# Download throttling
CHUNK_SIZE = 100
REQUEST_TIMEOUT = 60
SLEEP_BETWEEN_CHUNKS_SEC = 0.25

# Column filters you’d like to apply to the per-state CSV
# Tip: Keep State in sync with STATES_OF_INTEREST. You can also add 'bldg_id': [ ... ] if needed.
column_selection_case = {
    "State": STATES_OF_INTEREST,
    'bldg_id':[
    227194,     227605,     230291,     225038,     226834,     230841,     234257,     226675,     226096,     230918,     233327,     233584,
    229341,     227513,     231933,     224430,     233185,     233222,     227704,     235684,     228644,     225958,     233114,     226488,
    226004,     225292,     229300,     231297,     231803,     229335,     232608,     233946,     225889,     233689,     226570,     229574,
    227326,     232456,     226281,     234494,     234415,     235049,     228957,     229513,     226887,     229607,     227277,     234764,
    232332,     235115,     232651,     231354,     235706,     225329,     233964,     230260,     231392,     234785,     229569,     234905,
    226574,     235934,     226151,     224935,     234729,     226594,     230657,     230301,     230312,     225858,     230350,     232501,
    235441,     230780,     232321,     235025,     227273,     234219,     229042,     225397,     235498,     233077,     233651,     236260,
    234720,     228155,     235809,     235199,     227086,     231934,     235631,     227679,     232906,     224759,     224951,     229802,
    226888,     233305,     233085,     227032,     234575,     229243,     231858,     232824,     231540,     231242,     228376,     235404,
    227542,     232632,     224805,     228328,     229254,     224578,     227166,     224861,     230567,     232930,     226993,     228251,
    228670,     227105,     225390,     227444,     232160,     230152,     231660,     224825,     226179,     233609,     229064,     236149,
    233111,     229757,     224853,     226424,     224733,     230569,     236006,     228165,     234805,     230620,     230004,     231086,
    230895,     235147,     224551,     235875,     228602,     224569,     226122,     227244,     230162,     236071,     229917,     235602,
    235560,     232313,     227729,     234054,     230333,     232006,     229487,     233002,     235734,     229861,     235000,     235736,
    230472,     230625,     229161,     228356,     228808,     230793,     224548,     234065,     230662,     233357,     224706,     226272,
    228689,     232058,     230398,     224738,     230855,     230132,     233970,     225271,     232727,     228119,     231626,     231255,
    232725,     235913,     233790,     227053,     233852,     224675,     234645,     224859,     226138,     232730,     229659,     236177,
    225001,     234304,     230029,     229735,     235554,     231853,     231017,     225653,     226895,     231038,     226630,     227976,
    227155,     231134,     227850,     228776,     230795,     235410,     229002,     229370,     233815,     233168,     224716,     230655,
    225307,     228662,     229847,     231903,     231599,     226563,     224650,     234418,     227726,     226334,     228708,     231453,
    225696,     224463,     233809,     236083,     231718,     229715,     235081,     232996,     225908,     224611,     227671,     229004,
    228737,     228977,     225883,     235209,     232839,     229964,     229257,     233780,     233796,     226869,     224555,     232508,
    232603,     232245,     227189,     233186,     230292,     235990,     224917,     227184,     230179,     226457,     233739,     235153,
    232597,     226176,     234749,     232648,     224780,     232416,     227226,     230085,     234498,     225180,     227003,     229980,
    234580,     226512,     234973,     227942,     231468,     234360,     225686,     231918,     229838,     232470,     235583,     235759,
    234627,     228366,     227974,     229030,     234916,     235746,     230886,     232768,     232837,     226737,     233897,     230760,
    229974,     229006,     228596,     226518,     230187,     228395,     230725,     224426,     235169,     232523,     231428,     230214,
    236017,     224598,     234151,     229821,     225500,     227481,     230265,     235339,     234816,     232483,     229685,     229075,
    226337,     235036,     230093,     235949,     229263,     227267,     224666,     231574,     234687,     226416,     226684,     230812,
    228405,     235924,     233759,     234651,     227564,     235108,     234064,     233166,     226864,     233750,     232105,     228050,
    227077,     225837,     234853,     227261,     230036,     230677,     236118,     233644,     227005,     228287,     225051,     226307,
    226789,     227201,     233287,     235259,     233923,     226962,     230619,     236040,     225878,     231142,     231381,     235389,
    231104,     231340,     233499,     229231,     229065,     227283,     235159,     228679,     228441,     225519,     227588,     230591,
    234246,     234333,     231267,     232409,     235029,     228378,     234028,     229309,     227066,     225618,     235861,     230492,
    232886,     227736,     227668,     234893,     234676,     230041,     226493,     231727,     225590,     232463,     231686,     234860,
    226431,     232126,     228557,     233671,     230322,     225468,     234179,     228198,     232568,     231442,     230532,     228774,
    235503,     232170,     228969,     229900,     234432,     230211,     224927,     230892,     224982,     233414,     230789,     233596,
    231004,     235625,     224971,     230681,     231025,     230584,     232450,     234369,     224703,     234870,     234370,     228918,
    227626,     228937,     226271,     234482,     226101,     226529,     234706,     228383,     233665,     227927,     231181,     234348,
    231290,     228561,     227341,     226866,     234129,     230099,     228755,     231351,     224900,     235090,     231637,     228222,
    225421,     226318,     225503,     224595,     235235,     226354,     229671,     233469,     230145,     231199,     229399,     230364,
    234323,     234010,     230967,     226254,     231645,     225126,     229550,     227958,     224790,     231750,     232216,     225701,
    227180,     225776,     229312,     226810,     234696,     225444,     226394,     224513,     225478,     235452,     232783,     232146,
    232822,     233008,     224593,     226359,     227534,     227857,     225790,     230562,     230501,     231884,     234942,     232092,
    233592,     231977,     235725,     233541,     227228,     227197,     225257,     230870,     234315,     231758,     225300,     228264,
    234850,     228668,     229200,     232403,     224518,     229706,     225443,     229719,     227405,     231012,     226757,     228864,
    231070,     233236,     235277,     224711,     232131,     230074,     224692,     225127,     230629,     233830,     232515,     232428,
    228760,     225835,     229912,     226211,     235956,     235532,     232198,     225462,     224557,     226245,     234789,     235092,
    224515,     228817,     229057,     224497,     229297,     235598,     230264,     226280,     235148,     227687,     233928,     228797,
    232446,     225860,     234692,     227856,     232947,     232722,     225146,     235088,     234947,     230246,     228527,     236171,
    233020,     231205,     235570,     234743,     235160,     229472,     232309,     235245,     225071,     236214,     234464,     226952,
    231761,     227415,     231272,     234453,     229972,     235065,     230630,     230904,     236144,     233468,     233532,     224693,
    231431,     230025,     231382,     228078,     224908,     224867,     226242,     232400,     227766,     229868,     232020,     227558,
    229352,     228298,     233880,     235082,     228267,     236193,     228699,     225549,     226733,     227630,     235349,     226403,
    234478,     227074,     226261,     230609,     232010,     231948,     233088,     228753,     226352
]
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
    Loads ./commercial_data_SELECT_STATES_FILTERED_{STATE}.csv
    Applies filters in filter_dict and returns set of bldg_id (ints).
    """
    path = METADATA_CSV_TEMPLATE.format(STATE=state)
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
