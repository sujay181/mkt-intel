"""
load_duckdb.py — land raw/ files into DuckDB as the `raw` schema.

Run:  python warehouse/load_duckdb.py --db warehouse/mkt.duckdb --raw raw

This is your EL. dbt is the T. Keep it that way: NO cleaning happens here.
Everything lands as-is, including dirty UTMs, duplicate leads and mixed dates.

Swapping to BigQuery/Snowflake later means replacing only this file plus the
dbt profile — the models are written in ANSI-ish SQL with a dialect macro for
the two functions that differ (see macros/cross_db.sql).
"""
import argparse
import glob
import os

import duckdb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--raw", default="raw")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.db) or ".", exist_ok=True)
    con = duckdb.connect(a.db)
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")

    # ---- Segment events: JSONL, nested. Land as-is with JSON columns. ----
    pattern = os.path.abspath(f"{a.raw}/segment_events/*.jsonl")
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"No event files at {pattern} — run the generator first.")
    con.execute(f"""
        CREATE OR REPLACE TABLE raw.segment_events AS
        SELECT
            "type"                                   AS event_type,
            COALESCE(TRY_CAST(event AS VARCHAR), NULL) AS event_name,
            "messageId"                              AS message_id,
            "anonymousId"                            AS anonymous_id,
            "userId"                                 AS user_id,
            CAST("timestamp" AS TIMESTAMP)           AS event_ts,
            context                                  AS context_json,
            properties                               AS properties_json,
            TRY_CAST(traits AS JSON)                 AS traits_json
        FROM read_json_auto('{pattern}', union_by_name=true, ignore_errors=true);
    """)

    csvs = {
        "sfdc_accounts":                  f"{a.raw}/salesforce/accounts.csv",
        "sfdc_leads":                     f"{a.raw}/salesforce/leads.csv",
        "sfdc_contacts":                  f"{a.raw}/salesforce/contacts.csv",
        "sfdc_campaigns":                 f"{a.raw}/salesforce/campaigns.csv",
        "sfdc_campaign_members":          f"{a.raw}/salesforce/campaign_members.csv",
        "sfdc_opportunities":             f"{a.raw}/salesforce/opportunities.csv",
        "sfdc_opportunity_stage_history": f"{a.raw}/salesforce/opportunity_stage_history.csv",
        "ads_spend":                      f"{a.raw}/ad_platforms/spend.csv",
    }
    for tbl, path in csvs.items():
        p = os.path.abspath(path)
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.{tbl} AS
            SELECT * FROM read_csv_auto('{p}', header=true, all_varchar=true,
                                        sample_size=-1);
        """)

    # ground truth lands in its own schema so nobody joins it by accident
    con.execute("CREATE SCHEMA IF NOT EXISTS truth;")
    for tbl, path in {
        "account_touch_credit": "ground_truth/account_touch_credit.csv",
        "channel_contribution": "ground_truth/channel_contribution.csv",
    }.items():
        if os.path.exists(path):
            con.execute(f"""CREATE OR REPLACE TABLE truth.{tbl} AS
                            SELECT * FROM read_csv_auto('{os.path.abspath(path)}',
                                                        header=true, sample_size=-1);""")

    print("Loaded tables:")
    for row in con.execute("""
        SELECT schema_name, table_name, estimated_size
        FROM duckdb_tables() ORDER BY 1, 2
    """).fetchall():
        print(f"  {row[0]}.{row[1]:<34} ~{row[2]:>10,} rows")
    con.close()


if __name__ == "__main__":
    main()
