#!/usr/bin/env python3
"""Regenerate Table 2 from the four case workspaces, checking both seasons.

Outputs table2.csv and table2.md under the active work root's Phase 8 directory.
Phase 4 counts reproduce select_rep_family's report() from its saved final CSVs,
so generation does not rerun assignment or depend on temporary console logs.
"""
import argparse
import ast
from pathlib import Path

import pandas as pd

from pipeline_utils import resolve_work_path


CASES = (
    "NC_GSO_urban__NC", "NC_GSO_urban__TX",
    "TX_AUS_urban__NC", "TX_AUS_urban__TX",
)


def case_counts(runs_root, case, season):
    workspace = runs_root / case / season / "workspace"
    state = case.split("__")[1]
    counts = {"case": case}
    for sector, prefix, type_col in [
        ("commercial", "com", "in.comstock_building_type"),
        ("residential", "res", "in.geometry_building_type_acs"),
    ]:
        metadata = pd.read_csv(resolve_work_path(
            str(workspace), "1_data_provenance", "outputs", "pipeline_state",
            f"{sector}_data_SELECT_STATES.csv"))
        matches = pd.read_csv(resolve_work_path(
            str(workspace), "3_tolerance_matching", f"df_{prefix}_matches_out_{state}.csv"))
        final = pd.read_csv(resolve_work_path(
            str(workspace), "4_quota_assignment", f"{state}_final_{sector}.csv"))
        building_lists = matches["Matched_Buildings"].map(ast.literal_eval)
        matched_ids = set().union(*building_lists)
        chosen = final.groupby(type_col)["Chosen_Parquet"].nunique()
        counts[f"{sector}_statewide_buildings"] = len(metadata)
        counts[f"{sector}_matched_buildings"] = len(matched_ids)
        counts[f"{sector}_matched_parquets"] = matches.loc[
            building_lists.map(bool), "Source_File"].nunique()
        counts[f"{sector}_assigned_parquets"] = final["Chosen_Parquet"].nunique()
        counts[f"{sector}_distinct_types"] = len(chosen)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path,
                        default=Path(__file__).resolve().parent / "runs")
    args = parser.parse_args()
    runs_root = args.runs_root.resolve()
    rows = []
    for case in CASES:
        summer = case_counts(runs_root, case, "summer")
        winter = case_counts(runs_root, case, "winter")
        if summer != winter:
            raise ValueError(f"{case}: season-dependent Table 2 counts: {summer} != {winter}")
        rows.append(summer)
    table = pd.DataFrame(rows)
    markdown = "\n".join([
        "| " + " | ".join(table.columns) + " |",
        "| " + " | ".join(["---"] * len(table.columns)) + " |",
        *("| " + " | ".join(map(str, row)) + " |"
          for row in table.itertuples(index=False, name=None)),
    ]) + "\n"
    output_dir = Path(resolve_work_path("8_results_analysis"))
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_dir / "table2.csv", index=False)
    (output_dir / "table2.md").write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    print(f"Written: {output_dir / 'table2.csv'}")
    print(f"Written: {output_dir / 'table2.md'}")


if __name__ == "__main__":
    main()
