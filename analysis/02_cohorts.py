"""
02_cohorts.py — cohort payback curves by first-touch channel.

Run: python analysis/02_cohorts.py --db warehouse/mkt.duckdb

The point: channels do not convert at the same SPEED. A 30-day attribution
window structurally penalises long-cycle channels. This script quantifies how
much, which is the argument for lengthening the reporting window.
"""
import argparse, duckdb, pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    a = ap.parse_args(); con = duckdb.connect(a.db)
    pd.set_option("display.width", 220)

    curve = con.execute("""
        select first_touch_channel channel, months_since_first_touch m,
               sum(accounts_with_opp) accts, sum(cohort_accounts) cohort,
               sum(pipeline_usd) pipeline
        from marts.mart_cohort_retention group by 1,2 order by 1,2
    """).df()
    curve["cum_pipeline"] = curve.groupby("channel")["pipeline"].cumsum()
    tot = curve.groupby("channel")["pipeline"].transform("sum")
    curve["pct_of_lifetime_pipeline"] = curve["cum_pipeline"] / tot.replace(0, pd.NA)

    print("=== CUMULATIVE % OF LIFETIME PIPELINE REALISED, BY MONTH SINCE FIRST TOUCH ===")
    piv = curve.pivot_table(index="channel", columns="m",
                            values="pct_of_lifetime_pipeline", aggfunc="max")
    print(piv.iloc[:, :10].round(2).to_string())

    print("\n=== SHARE OF PIPELINE VISIBLE INSIDE A 30-DAY WINDOW ===")
    m0 = curve[curve.m <= 1].groupby("channel")["pct_of_lifetime_pipeline"].max().sort_values()
    print(m0.round(3).to_string())
    print("\nChannels near the top of this list are the ones a short attribution")
    print("window silently defunds. That is the recommendation to write up.")

    curve.to_csv("exports/cohort_payback.csv", index=False)
    print("\nWrote exports/cohort_payback.csv")

if __name__ == "__main__":
    main()
