"""
07_export_tableau.py — export marts to Hyper-friendly CSVs for Tableau Public.

Run: python analysis/07_export_tableau.py --db warehouse/mkt.duckdb

Tableau Public cannot connect to a local DuckDB file, so the published workbook
reads these extracts. Keep the file list short: every extra table you publish
is another thing a viewer can misread.
"""
import argparse, os, duckdb

TABLES = [
    ("marts.mart_funnel_daily",            "funnel_daily"),
    ("marts.fct_opportunities",            "opportunities"),
    ("marts.dim_account",                  "accounts"),
    ("marts.dim_campaign",                 "campaigns"),
    ("marts.mart_cohort_retention",        "cohort_retention"),
    ("marts.mart_data_quality",            "data_quality"),
    ("marts.fct_segment_membership",       "segment_membership"),
    ("marts.mart_segment_overlap",         "segment_overlap"),
    ("attribution.attr_channel_rollup",    "attribution_channel_rollup"),
    ("attribution.attr_model_vs_truth",    "attribution_vs_truth"),
    ("attribution.attr_model_scorecard",   "attribution_scorecard"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--out", default="exports/tableau")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    con = duckdb.connect(a.db)
    for src, name in TABLES:
        try:
            path = os.path.join(a.out, f"{name}.csv")
            con.execute(f"copy (select * from {src}) to '{path}' (header, delimiter ',')")
            n = con.execute(f"select count(*) from {src}").fetchone()[0]
            print(f"  {name:<32} {n:>9,} rows -> {path}")
        except Exception as e:
            print(f"  SKIP {name}: {e}")
    print(f"\nDone. Point Tableau at {a.out}/ and use the joins in docs/TABLEAU_BUILD.md")

if __name__ == "__main__":
    main()
