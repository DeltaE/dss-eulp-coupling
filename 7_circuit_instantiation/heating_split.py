# -*- coding: utf-8 -*-
"""
heating_split.py
----------------
The heating split of Phase 7b: which heating group (baseline, dm, un) every load of a
circuit draws. instantiate_circuits.py (Phase 7b) calls split_heating for every feeder
and mix; find_max_day_curve_impl.py --mix (phase mix_days) calls read_loads and
split_heating on the same Loads.dss to find the circuit's peak day.
"""

import hashlib
import math
import random
import re


def _stable_seed_offset(key: str) -> int:
    """sha256 of key, first 8 bytes as an integer, modulo 10_000_000. The same offset
    as _stable_seed_offset in instantiate_circuits.py."""
    digest = hashlib.sha256(key.encode()).digest()[:8]
    return int.from_bytes(digest, "big") % 10_000_000


def read_loads(loads_path):
    """Read a Loads.dss as Phase 7b does. Returns (unique_bases, base_to_daily):
    the load names without their _<n> leg suffix (except the name 'load'), and for each
    such name the set of its yearly= loadshape names."""
    unique_bases = set()
    base_to_daily = {}
    with open(loads_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line.lower().startswith('new load.'):
                continue
            m_name = re.search(r"New\s+Load\.(\S+)", line, flags=re.IGNORECASE)
            if not m_name: continue
            full = m_name.group(1)
            base = re.sub(r"_[0-9]+$", "", full)
            if base != 'load':
                unique_bases.add(base)
            m_daily = re.search(r"\byearly=(\S+)", line, flags=re.IGNORECASE)
            if m_daily:
                base_to_daily.setdefault(base, set()).add(m_daily.group(1).strip())
    return unique_bases, base_to_daily


def is_baseline_only(shares):
    """True when the normalized shares put every load in the baseline group."""
    p_b  = float(shares.get('baseline', 0.0))
    p_dm = float(shares.get('dm',       0.0))
    p_un = float(shares.get('un',       0.0))
    tot = p_b + p_dm + p_un
    return tot <= 0 or (p_dm / tot == 0.0 and p_un / tot == 0.0)


def split_heating(unique_bases, base_to_daily, shares, heating_seed, substation_name, feeder_name):
    """
    Label every load of one feeder and mix with a heating group.

    1. Normalizes the baseline, dm and un shares (all 0 -> 1, 0, 0).
    2. Counts per group from the sorted load names by largest remainder, then moves one
       load to any group with a positive share and a count of 0.
    3. Shuffles the labels, then the load names, with
       random.Random(heating_seed + _stable_seed_offset("<substation>|<feeder>")).
    4. Pairs names and labels; every yearly loadshape of a name takes its label, so a
       loadshape shared by several names keeps the label of the last one.

    Returns a dict: p_b, p_dm, p_un, n_b, n_dm, n_un, N, mix_seed_offset, bases,
    labels, daily_to_scen (loadshape name -> 'baseline' | 'dm' | 'un').
    """
    # 1) Normalize shares
    p_b  = float(shares.get('baseline', 0.0))
    p_dm = float(shares.get('dm',       0.0))
    p_un = float(shares.get('un',       0.0))
    tot = p_b + p_dm + p_un
    if tot <= 0:
        p_b, p_dm, p_un = 1.0, 0.0, 0.0
    else:
        p_b, p_dm, p_un = (p_b/tot, p_dm/tot, p_un/tot)

    # 2) Exact counts via largest-remainder rounding
    bases = sorted(unique_bases)
    N = len(bases)
    raw = {'baseline': p_b*N, 'dm': p_dm*N, 'un': p_un*N}
    cnt = {k: int(math.floor(v)) for k, v in raw.items()}
    need = N - sum(cnt.values())
    frac = sorted(((raw[k] - cnt[k], k) for k in raw), reverse=True)
    for i in range(need):
        cnt[frac[i % len(frac)][1]] += 1

    # Optional: ensure min-one for any category with positive share (keeps sum=N)
    if p_b > 0 and cnt['baseline'] == 0:
        donor = max((d for d in ('dm','un') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
        if donor: cnt[donor] -= 1; cnt['baseline'] += 1
    if p_dm > 0 and cnt['dm'] == 0:
        donor = max((d for d in ('baseline','un') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
        if donor: cnt[donor] -= 1; cnt['dm'] += 1
    if p_un > 0 and cnt['un'] == 0:
        donor = max((d for d in ('dm','baseline') if cnt[d] > 1), key=lambda d: cnt[d], default=None)
        if donor: cnt[donor] -= 1; cnt['un'] += 1

    n_b, n_dm, n_un = cnt['baseline'], cnt['dm'], cnt['un']  # totals sum exactly to N

    # 3) Deterministic RNG per feeder (random look, reproducible)
    # Same offset feeds ev/storage/pv seeds in instantiate_circuits.py (pick()); it
    # depends only on (substation_name, feeder_name), not on which seed it's added to.
    mix_seed_offset = _stable_seed_offset(f"{substation_name}|{feeder_name}")
    rng = random.Random(int(heating_seed) + mix_seed_offset)

    # 4) Build randomized labels with exact counts, and randomized base order
    labels = (['baseline'] * n_b) + (['dm'] * n_dm) + (['un'] * n_un)
    rng.shuffle(labels)
    rng.shuffle(bases)

    # 5) Map daily loadshape names to scenarios
    daily_to_scen = {}
    for base, scen in zip(bases, labels):
        for ls in base_to_daily.get(base, []):
            daily_to_scen[ls] = scen

    return {"p_b": p_b, "p_dm": p_dm, "p_un": p_un,
            "n_b": n_b, "n_dm": n_dm, "n_un": n_un, "N": N,
            "mix_seed_offset": mix_seed_offset, "bases": bases, "labels": labels,
            "daily_to_scen": daily_to_scen}
