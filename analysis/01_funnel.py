"""
01_funnel.py — funnel conversion rates and channel diagnostics.

Run: python analysis/01_funnel.py --db warehouse/mkt.duckdb

Produces exports/funnel_by_channel.csv and prints the two diagnostics that
actually change decisions:
  * stage-to-stage conversion by channel (where each channel leaks)
  * volume vs quality quadrant (high volume + low SQL rate = a spend problem)
"""
import argparse, duckdb, pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    a = ap.parse_args()
    con = duckdb.connect(a.db)
    pd.set_option("display.width", 200)

    funnel = con.execute("""
        select channel,
               sum(sessions) sessions, sum(accounts_touched) accounts_touched,
               sum(leads_created) leads, sum(mqls) mqls, sum(sqls) sqls,
               sum(opps_created) opps, sum(opp_pipeline_usd) pipeline_usd,
               sum(opps_won) wins, sum(won_arr_usd) won_arr, sum(cost_usd) as spend
        from marts.mart_funnel_daily group by 1 order by pipeline_usd desc
    """).df()

    for a_, b_, name in [("leads","mqls","lead_to_mql"), ("mqls","sqls","mql_to_sql"),
                         ("sqls","opps","sql_to_opp"), ("opps","wins","opp_to_win")]:
        funnel[name] = funnel[b_].astype(float) / funnel[a_].replace(0, float("nan")).astype(float)
    funnel["cost_per_opp"] = funnel["spend"] / funnel["opps"].replace(0, float("nan"))
    funnel["pipeline_roas"] = funnel["pipeline_usd"] / funnel["spend"].replace(0, float("nan"))

    print("=== FUNNEL BY CHANNEL ===")
    print(funnel[["channel","leads","mqls","sqls","opps","lead_to_mql","mql_to_sql",
                  "sql_to_opp","cost_per_opp","pipeline_roas"]].round(3).to_string(index=False))

    med_vol = funnel["leads"].median()
    med_q   = funnel["mql_to_sql"].median()
    funnel["quadrant"] = [
        ("Scale it"      if v >= med_vol and q >= med_q else
         "Fix quality"   if v >= med_vol else
         "Test bigger"   if q >= med_q else
         "Cut or rework")
        for v, q in zip(funnel["leads"], funnel["mql_to_sql"].fillna(0))]
    print("\n=== VOLUME x QUALITY QUADRANT ===")
    print(funnel[["channel","leads","mql_to_sql","quadrant"]].round(3).to_string(index=False))

    print("\n=== TRACKING OUTAGE DETECTION (paid_social, Sep 2025) ===")
    print(con.execute("""
        select date_trunc('week', date_day)::date wk, sum(sessions) sessions
        from marts.mart_funnel_daily
        where channel='paid_social' and date_day between '2025-08-18' and '2025-10-06'
        group by 1 order by 1
    """).df().to_string(index=False))

    funnel.to_csv("exports/funnel_by_channel.csv", index=False)
    print("\nWrote exports/funnel_by_channel.csv")

if __name__ == "__main__":
    main()
