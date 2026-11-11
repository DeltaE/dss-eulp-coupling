# -*- coding: utf-8 -*-
"""
fetch_tou_rates.py
------------------
Fetch one residential time-of-use rate per donor state from the OpenEI U.S. Utility
Rate Database (URDB, API version 7) and save it as a dated copy for the Phase 7 deploy
(ev_control: offpeak_start). A maintainer runs it from the repository root, outside
run_case.py --all:

    python 7_circuit_instantiation/fetch_tou_rates.py [--states NC TX]

API documentation: https://apps.openei.org/services/doc/rest/util_rates

Inputs
- 7_circuit_instantiation/data_tariffs/rate_queries.yaml: per state, the address of
  the query and the utility whose rates are kept.
- configs/local.yaml, openei_api_key_file: a text file that holds the API key. The key
  is never printed, logged or written; messages show the request with api_key=REMOVED.

Steps, per state
1. GET https://api.openei.org/utility_rates with version=7, format=json, detail=full,
   sector=Residential, approved=true, the address, orderby=startdate, direction=desc
   and limit=500, paging with offset while a page holds 500 records.
2. Candidates are the rates of the query's utility (the record's utility field) whose
   weekday or weekend energy schedule holds at least two period numbers within one
   month, so the rate has cheaper hours within a day. A candidate is current when it
   has no enddate or its enddate is after the fetch time.
3. Choice: the current candidate with the newest startdate (equal dates go to the lower
   label). With no current candidate, the ended candidate with the newest startdate,
   marked not current. With no candidate, no file is written for that state.

Outputs
- 7_circuit_instantiation/data_tariffs/<STATE>_urdb_rate.json (indent 1, sorted keys):
  source_url (the rate's uri), api_request, fetched_utc, query, current, candidates
  (label, utility, name, startdate, enddate, current, n_periods) and rate (the chosen
  record as returned).

Stops (exit 1)
- configs/local.yaml or openei_api_key_file missing; the key file missing or empty.
- A state not in rate_queries.yaml.
- A request fails or does not return a JSON object with an items list.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
TARIFF_DIR = os.path.join(HERE, "data_tariffs")
API_URL = "https://api.openei.org/utility_rates"
PAGE_LIMIT = 500


def read_api_key():
    local_path = os.path.join(REPO_ROOT, "configs", "local.yaml")
    if not os.path.exists(local_path):
        sys.exit(f"Missing {local_path}. Copy configs/local.yaml.example and set openei_api_key_file.")
    with open(local_path, encoding="utf-8") as f:
        local = yaml.safe_load(f) or {}
    key_file = local.get("openei_api_key_file")
    if not key_file:
        sys.exit("configs/local.yaml does not set openei_api_key_file.")
    if not os.path.exists(key_file):
        sys.exit(f"The OpenEI key file named by openei_api_key_file does not exist: {key_file}")
    with open(key_file, encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        sys.exit(f"The OpenEI key file is empty: {key_file}")
    return key


def request_url(query, offset, key):
    params = {"version": 7, "format": "json", "api_key": key, "detail": "full",
              "sector": "Residential", "approved": "true", "address": query["address"],
              "orderby": "startdate", "direction": "desc", "limit": PAGE_LIMIT}
    if offset:
        params["offset"] = offset
    return f"{API_URL}?{urlencode(params)}"


def fetch_all(query, key):
    """Return (records, the first request URL with api_key=REMOVED)."""
    shown = request_url(query, 0, "REMOVED")
    records, offset = [], 0
    while True:
        url = request_url(query, offset, key)
        safe = request_url(query, offset, "REMOVED")
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            sys.exit(f"Request failed: {safe}: {type(e).__name__}: {str(e).replace(key, 'REMOVED')}")
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            sys.exit(f"Request did not return a JSON object with an items list: {safe}")
        records.extend(data["items"])
        if len(data["items"]) < PAGE_LIMIT:
            return records, shown
        offset += PAGE_LIMIT


def periods(rate):
    """The period numbers that the weekday and weekend energy schedules hold."""
    found = set()
    for key in ("energyweekdayschedule", "energyweekendschedule"):
        for row in rate.get(key) or []:
            found.update(int(p) for p in row)
    return found


def n_day_periods(rate):
    """The largest count of distinct period numbers in one month's 24 hours of the
    weekday or weekend energy schedule. A rate whose periods change only between
    months (a seasonal rate) gives 1: it has no cheaper hours within a day."""
    counts = [0]
    for key in ("energyweekdayschedule", "energyweekendschedule"):
        counts.extend(len({int(p) for p in row}) for row in rate.get(key) or [])
    return max(counts)


def is_current(rate, now_ts):
    end = rate.get("enddate")
    return end in (None, "") or float(end) > now_ts


def choose(records, now_ts, utility=None):
    """Return (chosen record or None, current flag, candidate list). With utility, only
    records whose utility field equals it are candidates."""
    cands = [r for r in records if n_day_periods(r) >= 2
             and (utility is None or r.get("utility") == utility)]
    order = sorted(cands, key=lambda r: (-float(r.get("startdate") or 0), str(r.get("label"))))
    listing = [{"label": r.get("label"), "utility": r.get("utility"), "name": r.get("name"),
                "startdate": r.get("startdate"), "enddate": r.get("enddate"),
                "current": is_current(r, now_ts), "n_periods": len(periods(r))} for r in order]
    current = [r for r in order if is_current(r, now_ts)]
    if current:
        return current[0], True, listing
    if order:
        return order[0], False, listing
    return None, False, listing


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--states", nargs="+", default=None,
                    help="donor states to fetch (default: every state in rate_queries.yaml)")
    args = ap.parse_args()
    with open(os.path.join(TARIFF_DIR, "rate_queries.yaml"), encoding="utf-8") as f:
        queries = yaml.safe_load(f) or {}
    states = args.states or sorted(queries)
    for st in states:
        if st not in queries:
            sys.exit(f"State {st} is not in rate_queries.yaml.")
    key = read_api_key()
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    for st in states:
        records, shown = fetch_all(queries[st], key)
        rate, current, listing = choose(records, now_ts, queries[st].get("utility"))
        print(f"{st}: {len(records)} rates returned, {len(listing)} with a time-of-use schedule.")
        if rate is None:
            print(f"{st}: no candidate; no file written.")
            continue
        out = {"source_url": rate.get("uri"), "api_request": shown,
               "fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "query": queries[st],
               "current": current, "candidates": listing, "rate": rate}
        out_path = os.path.join(TARIFF_DIR, f"{st}_urdb_rate.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"{st}: chose {rate.get('label')} ({rate.get('utility')}: {rate.get('name')}), "
              f"current={current} -> {out_path}")


if __name__ == "__main__":
    main()
