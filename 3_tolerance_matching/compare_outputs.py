# -*- coding: utf-8 -*-
"""
Semantic diff between the original (golden) and optimized output CSVs.

Usage:
    python compare_outputs.py df_com_matches_out_NC.GOLDEN.csv df_com_matches_out_NC.csv

Compares per (Source_File, State): the Tolerance and the SET of matched building ids.
This is the correct notion of "zero regression" -- it is robust to two cosmetic things
that are NOT real differences:
  - numpy >= 2.0 serializes ints as "np.int64(5)" while the optimized version writes "5"
  - row ordering, if it ever differs

Building ids are extracted as integers from each list cell regardless of formatting.
"""
import re
import sys
import pandas as pd


def parse_ids(cell):
    if pd.isna(cell):
        return frozenset()
    return frozenset(int(x) for x in re.findall(r"-?\d+", str(cell)))


def parse_tol(cell):
    if pd.isna(cell) or str(cell).strip() in ("", "None", "nan"):
        return None
    return int(float(cell))


def load(path):
    df = pd.read_csv(path)
    d = {}
    for _, r in df.iterrows():
        key = (r["Source_File"], r["State"])
        d[key] = (parse_tol(r["Tolerance"]), parse_ids(r["Matched_Buildings"]))
    return d


def main(golden_path, new_path):
    g, n = load(golden_path), load(new_path)
    keys = set(g) | set(n)
    diffs = 0
    for k in sorted(keys, key=lambda x: (str(x[1]), str(x[0]))):
        if k not in g:
            print(f"  ONLY IN NEW:    {k}"); diffs += 1; continue
        if k not in n:
            print(f"  ONLY IN GOLDEN: {k}"); diffs += 1; continue
        gt, gi = g[k]
        nt, ni = n[k]
        if gt != nt:
            print(f"  TOL DIFF {k}: golden={gt} new={nt}"); diffs += 1
        if gi != ni:
            print(f"  SET DIFF {k}: +{sorted(ni - gi)[:10]} -{sorted(gi - ni)[:10]}"); diffs += 1
    if diffs == 0:
        print(f"IDENTICAL: {len(keys)} source-file rows match exactly (tolerance + matched set).")
    else:
        print(f"\n{diffs} difference(s) found.")
    return diffs


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1], sys.argv[2]) else 0)
