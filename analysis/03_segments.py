"""
03_segments.py — segment sizing, overlap and export for activation.

Run: python analysis/03_segments.py --db warehouse/mkt.duckdb --export

Writes one CSV per segment to exports/segments/ in the column shape that
Marketo, Salesforce Campaign Member import and LinkedIn Matched Audiences
each expect. In production this step is reverse-ETL (Hightouch/Census);
the CSV is the honest stand-in and the column contract is identical.
"""
import argparse, os, duckdb, pandas as pd

TARGET_COLUMNS = {
    "Marketo List":              ["email","first_name","last_name","company","segment_name","version"],
    "Salesforce Campaign":       ["account_id","account_name","segment_id","segment_name","version"],
    "LinkedIn Matched Audience": ["company","country","segment_name"],
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args(); con = duckdb.connect(a.db)
    pd.set_option("display.width", 200)

    print("=== SEGMENT SIZES AND QUALITY ===")
    print(con.execute("""
        select segment_id, segment_name, activation_target, version,
               count(*) accounts,
               round(avg(lifetime_touches),1) avg_touches,
               round(100.0*avg(case when has_opportunity then 1 else 0 end),1) pct_with_opp,
               round(sum(won_arr_usd)) won_arr
        from marts.fct_segment_membership group by 1,2,3,4 order by accounts desc
    """).df().to_string(index=False))

    print("\n=== OVERLAP (accounts in both) ===")
    print(con.execute("""
        select segment_a, segment_b, overlap_accounts,
               round(jaccard_index,3) jaccard, round(overlap_rate_a,3) share_of_a
        from marts.mart_segment_overlap where overlap_accounts > 0
        order by jaccard desc limit 15
    """).df().to_string(index=False))
    print("\nAny pair above ~0.30 Jaccard is a message-collision risk: the same")
    print("accounts are in two programs. Suppress one or merge the definitions.")

    if a.export:
        os.makedirs("exports/segments", exist_ok=True)
        df = con.execute("""
            select m.*, l.email, l.first_name, l.last_name
            from marts.fct_segment_membership m
            left join (select account_id, min(email) email, min(first_name) first_name,
                              min(last_name) last_name
                       from staging.stg_sfdc__leads where email is not null
                       group by 1) l on l.account_id = m.account_id
        """).df()
        df["company"] = df["account_name"]
        df["country"] = df["region"]
        for sid, g in df.groupby("segment_id"):
            target = g["activation_target"].iloc[0]
            cols = [c for c in TARGET_COLUMNS.get(target, ["account_id"]) if c in g.columns]
            out = g[cols].drop_duplicates()
            path = f"exports/segments/{sid}_{target.replace(' ','_').lower()}.csv"
            out.to_csv(path, index=False)
            print(f"  wrote {path}  ({len(out)} rows, target={target})")

if __name__ == "__main__":
    main()
