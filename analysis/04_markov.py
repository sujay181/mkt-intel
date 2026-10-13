"""
04_markov.py — Markov-chain attribution via removal effect.

Run:  python analysis/04_markov.py --db warehouse/mkt.duckdb

WHY THIS MODEL IS DIFFERENT
---------------------------
Every heuristic model in attr_heuristic_models.sql answers "how should I split
credit across the touches that DID happen?" A Markov model answers a causal
question instead: "if this channel vanished, how much conversion would I lose?"

It needs the NEGATIVE paths — accounts that were touched and never converted —
which the heuristic models never see. That is the single most important
methodological difference and the thing to say out loud in an interview.

METHOD
------
1. Build one path per account: [start] -> ch1 -> ch2 -> ... -> [conversion|null]
2. Estimate the first-order transition matrix by counting.
3. Compute p_convert = probability of absorbing in [conversion] from [start].
4. For each channel c: delete c from the graph (route its inbound edges
   straight to [null]) and recompute p_convert_without_c.
   removal_effect(c) = (p_convert - p_convert_without_c) / p_convert
5. Normalise removal effects to sum to 1 -> channel credit.

ASSUMPTIONS AND THEIR CONSEQUENCES (say these before someone asks)
  - First-order Markov: the next touch depends only on the current channel.
    Real journeys have longer memory. Higher orders need far more data; with
    ~6k accounts, order 2 is already sparse. Order is a --order flag so you can
    show the sensitivity rather than assert first-order is fine.
  - Self-transitions are collapsed by default (A->A becomes one A). Keeping
    them inflates high-frequency channels like direct. --keep-self-loops
    lets you show both.
  - The absorbing state is "opportunity created", not "closed won", because
    win/loss is dominated by sales execution, not marketing.
"""
from __future__ import annotations

import argparse
import json

import duckdb
import numpy as np
import pandas as pd

CONV = "__conversion__"
NULL = "__null__"
START = "__start__"


def load_paths(con, lookback_days: int, keep_self_loops: bool):
    """One ordered channel path per account, labelled converted / not."""
    df = con.execute(f"""
        with opp as (
            select account_id, min(opportunity_created_date) as opp_date
            from marts.fct_opportunities group by 1
        ),
        t as (
            select tp.account_id, tp.touch_ts, tp.channel, o.opp_date
            from marts.fct_touchpoints tp
            left join opp o on o.account_id = tp.account_id
            where tp.is_attributable
              and tp.channel <> 'unmapped'
              and (o.opp_date is null or tp.touch_date <= o.opp_date)
              and (o.opp_date is null
                   or tp.touch_date >= o.opp_date - interval '{lookback_days}' day)
        )
        select account_id, channel, touch_ts, opp_date is not null as converted
        from t order by account_id, touch_ts
    """).df()

    paths = []
    for acct, g in df.groupby("account_id", sort=False):
        seq = list(g["channel"])
        if not keep_self_loops:
            seq = [c for i, c in enumerate(seq) if i == 0 or c != seq[i - 1]]
        paths.append((seq, bool(g["converted"].iloc[0])))
    return paths


def build_transitions(paths, order: int = 1):
    """Return (states, transition matrix as dict-of-dicts of counts)."""
    counts: dict[str, dict[str, int]] = {}

    def add(a, b):
        counts.setdefault(a, {})
        counts[a][b] = counts[a].get(b, 0) + 1

    for seq, converted in paths:
        if not seq:
            continue
        if order == 1:
            nodes = seq
        else:
            nodes = ["|".join(seq[max(0, i - order + 1):i + 1]) for i in range(len(seq))]
        add(START, nodes[0])
        for a, b in zip(nodes, nodes[1:]):
            add(a, b)
        add(nodes[-1], CONV if converted else NULL)

    states = sorted({s for s in counts} | {t for d in counts.values() for t in d})
    return states, counts


def to_matrix(states, counts, drop_channel: str | None = None, order: int = 1):
    """Row-stochastic matrix. Dropping a channel reroutes its inbound edges to NULL."""
    idx = {s: i for i, s in enumerate(states)}
    n = len(states)
    M = np.zeros((n, n))

    def is_dropped(state: str) -> bool:
        if drop_channel is None or state in (START, CONV, NULL):
            return False
        return drop_channel in state.split("|") if order > 1 else state == drop_channel

    for a, row in counts.items():
        if is_dropped(a):
            continue
        for b, c in row.items():
            target = NULL if is_dropped(b) else b
            M[idx[a], idx[target]] += c

    for state in states:
        if is_dropped(state):
            M[idx[state], :] = 0
            M[idx[state], idx[NULL]] = 1

    rs = M.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1
    return M / rs, idx


def absorb_prob(M, idx, n_iter: int = 2000, tol: float = 1e-12):
    """P(absorb in CONV | start at START) by power iteration."""
    n = M.shape[0]
    P = M.copy()
    for a in (CONV, NULL):
        P[idx[a], :] = 0
        P[idx[a], idx[a]] = 1
    v = np.zeros(n)
    v[idx[START]] = 1.0
    for _ in range(n_iter):
        nv = v @ P
        if np.abs(nv - v).max() < tol:
            v = nv
            break
        v = nv
    return float(v[idx[CONV]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/mkt.duckdb")
    ap.add_argument("--order", type=int, default=1)
    ap.add_argument("--lookback-days", type=int, default=365)
    ap.add_argument("--keep-self-loops", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=0,
                    help="bootstrap resamples for confidence intervals (try 200)")
    a = ap.parse_args()

    con = duckdb.connect(a.db)
    paths = load_paths(con, a.lookback_days, a.keep_self_loops)
    n_conv = sum(1 for _, c in paths if c)
    print(f"Loaded {len(paths):,} account paths ({n_conv:,} converted, "
          f"{n_conv/max(len(paths),1):.1%})")
    if n_conv < 30:
        print("WARNING: too few conversions for a stable Markov estimate. "
              "Re-run the generator with more accounts.")

    channels = sorted({c for seq, _ in paths for c in seq})

    def removal_effects(sample_paths):
        states, counts = build_transitions(sample_paths, a.order)
        M, idx = to_matrix(states, counts, None, a.order)
        base = absorb_prob(M, idx)
        out = {}
        for ch in channels:
            Md, idxd = to_matrix(states, counts, ch, a.order)
            out[ch] = (base - absorb_prob(Md, idxd)) / base if base > 0 else 0.0
        return base, out

    base_p, re = removal_effects(paths)
    total = sum(max(v, 0) for v in re.values()) or 1.0
    res = pd.DataFrame({
        "channel": channels,
        "removal_effect": [re[c] for c in channels],
        "markov_credit_share": [max(re[c], 0) / total for c in channels],
    })

    if a.bootstrap:
        rng = np.random.default_rng(7)
        boots = []
        for b in range(a.bootstrap):
            samp = [paths[i] for i in rng.integers(0, len(paths), len(paths))]
            _, r = removal_effects(samp)
            t = sum(max(v, 0) for v in r.values()) or 1.0
            boots.append([max(r[c], 0) / t for c in channels])
            if (b + 1) % 50 == 0:
                print(f"  bootstrap {b+1}/{a.bootstrap}")
        B = np.array(boots)
        res["ci_lower"] = np.percentile(B, 2.5, axis=0)
        res["ci_upper"] = np.percentile(B, 97.5, axis=0)

    # allocate pipeline dollars by markov share
    total_pipe = con.execute("""
        select sum(amount_arr_usd) from marts.fct_opportunities
        where opportunity_id in (select distinct opportunity_id
                                 from attribution.attr_heuristic_models)
    """).fetchone()[0] or 0.0
    res["credited_pipeline_usd"] = res["markov_credit_share"] * total_pipe
    res["model_name"] = f"markov_order{a.order}"
    res["base_conversion_prob"] = base_p

    con.execute("create schema if not exists attribution;")
    con.register("markov_df", res)
    con.execute("create or replace table attribution.attr_markov_channel as select * from markov_df")

    # scored against truth, same shape as attr_model_vs_truth
    con.execute("""
        create or replace table attribution.attr_markov_vs_truth as
        with truth as (
            select channel, sum(true_credit_arr_usd) as true_arr
            from truth.account_touch_credit group by 1
        ),
        ts as (select channel, true_arr / sum(true_arr) over () as true_share from truth)
        select m.model_name, m.channel, ts.true_share as true_share_of_arr,
               m.markov_credit_share as modelled_share_of_arr,
               m.markov_credit_share - ts.true_share as share_error,
               abs(m.markov_credit_share - ts.true_share) as abs_share_error
        from attribution.attr_markov_channel m join ts on ts.channel = m.channel
    """)

    mae = con.execute("select avg(abs_share_error) from attribution.attr_markov_vs_truth").fetchone()[0]
    print(f"\nBase conversion probability from [start]: {base_p:.4f}")
    print(res.sort_values("markov_credit_share", ascending=False).to_string(index=False))
    print(f"\nMarkov order-{a.order} MAE vs ground truth: {mae:.4f}")
    print("Wrote attribution.attr_markov_channel and attribution.attr_markov_vs_truth")

    with open("exports/markov_summary.json", "w") as f:
        json.dump({"order": a.order, "base_conversion_prob": base_p, "mae_share": mae,
                   "n_paths": len(paths), "n_converted": n_conv}, f, indent=2)


if __name__ == "__main__":
    main()
