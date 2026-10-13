"""
05_scorecard.py — the headline result: which attribution model is least wrong,
and how much does that answer depend on arbitrary parameter choices?

Run: python analysis/05_scorecard.py --db warehouse/mkt.duckdb

Outputs:
  exports/attribution_scorecard.csv     one row per model, MAE/RMSE vs truth
  exports/halflife_sensitivity.csv      time-decay MAE across half-lives
  exports/lookback_sensitivity.csv      MAE across attribution windows
  exports/budget_reallocation.csv       $ implication of believing each model

The sensitivity sweeps matter more than the ranking. Anyone can say
"multi-touch beat last-touch". Showing that time-decay's answer swings by N
percentage points when you move the half-life from 7 to 45 days is the part
that demonstrates you understand the models are assumptions, not measurements.
"""
import argparse, duckdb, numpy as np, pandas as pd

def halflife_sweep(con, halflives):
    rows = []
    for hl in halflives:
        df = con.execute(f"""
            with p as (select * from intermediate.int_opportunity_touch_paths),
            d as (select *, power(2.0, -1.0*days_before_opp/{hl}) w from p),
            n as (select *, w/sum(w) over (partition by opportunity_id) c from d),
            m as (select channel, sum(c*amount_arr_usd) arr from n group by 1),
            ms as (select channel, arr/sum(arr) over () as pct from m),
            t as (select channel, sum(true_credit_arr_usd) a from truth.account_touch_credit group by 1),
            ts as (select channel, a/sum(a) over () as pct from t)
            select ms.channel, ms.pct as modelled, ts.pct as truth
            from ms join ts on ts.channel = ms.channel
        """).df()
        rows.append({"half_life_days": hl,
                     "mae_share": (df.modelled - df.truth).abs().mean(),
                     "direct_share": float(df.loc[df.channel == "direct", "modelled"].sum()),
                     "partner_share": float(df.loc[df.channel == "partner_referral", "modelled"].sum())})
    return pd.DataFrame(rows)

def lookback_sweep(con, windows):
    rows = []
    for w in windows:
        df = con.execute(f"""
            with p as (
                select o.opportunity_id, o.amount_arr_usd, t.channel,
                       row_number() over (partition by o.opportunity_id order by t.touch_ts) rn,
                       count(*) over (partition by o.opportunity_id) n
                from marts.fct_opportunities o
                join marts.fct_touchpoints t on t.account_id = o.account_id
                where t.is_attributable and t.touch_date <= o.opportunity_created_date
                  and t.touch_date >= o.opportunity_created_date - interval '{w}' day
            ),
            m as (select channel, sum(amount_arr_usd/n) as arr from p group by 1),
            ms as (select channel, arr/sum(arr) over () as pct from m),
            t as (select channel, sum(true_credit_arr_usd) a from truth.account_touch_credit group by 1),
            ts as (select channel, a/sum(a) over () as pct from t)
            select ms.channel, ms.pct as modelled, ts.pct as truth
            from ms join ts on ts.channel = ms.channel
        """).df()
        rows.append({"lookback_days": w, "model": "linear",
                     "mae_share": (df.modelled - df.truth).abs().mean(),
                     "channels_covered": len(df)})
    return pd.DataFrame(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--budget", type=float, default=2_000_000,
                    help="annual paid budget to reallocate, for the $ impact table")
    a = ap.parse_args(); con = duckdb.connect(a.db)
    pd.set_option("display.width", 220)

    print("=== MODEL SCORECARD (lower MAE = closer to ground truth) ===")
    sc = con.execute("""
        select model_name, round(mae_share,4) mae_share, round(rmse_share,4) rmse_share,
               worst_channel, round(worst_channel_error,4) worst_error,
               channels_within_15pct, round(rank_correlation,3) rank_corr
        from attribution.attr_model_scorecard order by mae_share
    """).df()
    try:
        mk = con.execute("""
            select model_name, round(avg(abs_share_error),4) mae_share,
                   round(sqrt(avg(power(share_error,2))),4) rmse_share
            from attribution.attr_markov_vs_truth group by 1
        """).df()
        sc = pd.concat([sc, mk], ignore_index=True).sort_values("mae_share")
    except Exception:
        print("  (run analysis/04_markov.py first to include the Markov model)")
    print(sc.to_string(index=False))
    sc.to_csv("exports/attribution_scorecard.csv", index=False)

    print("\n=== WHERE EACH MODEL GOES WRONG (share of pipeline) ===")
    print(con.execute("""
        select channel, round(max(true_share_of_arr),3) truth,
               round(max(case when model_name='first_touch' then modelled_share_of_arr end),3) first_t,
               round(max(case when model_name='last_touch' then modelled_share_of_arr end),3) last_t,
               round(max(case when model_name='linear' then modelled_share_of_arr end),3) linear,
               round(max(case when model_name='time_decay' then modelled_share_of_arr end),3) decay,
               round(max(case when model_name='position_based' then modelled_share_of_arr end),3) pos
        from attribution.attr_model_vs_truth group by 1 order by truth desc
    """).df().to_string(index=False))

    print("\n=== HALF-LIFE SENSITIVITY (time decay) ===")
    hl = halflife_sweep(con, [3, 7, 14, 21, 30, 45, 60])
    print(hl.round(4).to_string(index=False))
    hl.to_csv("exports/halflife_sensitivity.csv", index=False)
    spread = hl.direct_share.max() - hl.direct_share.min()
    print(f"\n  Direct's credited share moves {spread:.1%} across plausible half-lives.")
    print("  That spread is larger than most budget decisions people make from it.")

    print("\n=== LOOKBACK WINDOW SENSITIVITY ===")
    lb = lookback_sweep(con, [30, 60, 90, 180, 365])
    print(lb.round(4).to_string(index=False))
    lb.to_csv("exports/lookback_sensitivity.csv", index=False)

    print("\n=== $ IMPACT: what each model would tell you to spend ===")
    alloc = con.execute(f"""
        select channel,
               round(max(true_share_of_arr) * {a.budget}) budget_if_truth,
               round(max(case when model_name='last_touch' then modelled_share_of_arr end) * {a.budget}) budget_if_last_touch,
               round(max(case when model_name='position_based' then modelled_share_of_arr end) * {a.budget}) budget_if_position
        from attribution.attr_model_vs_truth group by 1 order by budget_if_truth desc
    """).df()
    alloc["last_touch_error_usd"] = alloc.budget_if_last_touch - alloc.budget_if_truth
    print(alloc.to_string(index=False))
    alloc.to_csv("exports/budget_reallocation.csv", index=False)
    mis = alloc.last_touch_error_usd.abs().sum() / 2
    print(f"\n  Believing last-touch misallocates about ${mis:,.0f} of a "
          f"${a.budget:,.0f} budget. THIS IS THE HEADLINE NUMBER FOR YOUR MEMO.")

if __name__ == "__main__":
    main()
