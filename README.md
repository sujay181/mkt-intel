# Marketing Attribution & Audience Intelligence Platform

**An end-to-end marketing analytics stack built on simulated data with known ground truth — so attribution models can be *scored*, not just asserted.**

> **Headline result:** on this dataset, believing last-touch attribution would misallocate **$454,254 of a $2,000,000 annual budget** — roughly 23%. It over-credits `direct` by 2.2x and under-credits `partner_referral` by 4.6x. Full scorecard below.

*(Replace the links below with your own before sharing.)*

| | |
|---|---|
| **Live dashboard** | `[Tableau Public link]` |
| **2-minute walkthrough** | `[Loom/YouTube link]` |
| **Insight memo (1 page)** | [`docs/INSIGHT_MEMO.md`](docs/INSIGHT_MEMO.md) |
| **Data dictionary** | [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) |
| **dbt docs** | `[GitHub Pages link]` |

---

## Why this project is built on simulated data

Most marketing attribution portfolios download a public dataset, run last-touch, and produce a channel ROI chart. Nobody — including the author — can tell whether the chart is right, because real data never contains the answer.

This project inverts that. I wrote the data-generating process, so I know the true latent contribution of every touch to every conversion. That makes attribution models **falsifiable**: I can measure how wrong each one is, in percentage points of pipeline share and in dollars of misallocated budget.

That is the entire argument for the approach, and it is the thing to push back with if someone calls synthetic data a shortcut. Every parameter choice is benchmarked against published B2B figures and documented in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

---

## Results

### Model scorecard

Scored against ground truth. MAE is mean absolute error on each channel's share of pipeline, so `0.0305` means the average channel is off by about 3 percentage points.

| Model | MAE | RMSE | Worst channel | Rank corr |
|---|---|---|---|---|
| **position_based (40/20/40)** | **0.0305** | 0.0391 | partner_referral | 0.72 |
| linear | 0.0360 | 0.0454 | direct | 0.37 |
| first_touch | 0.0369 | 0.0433 | webinar | 0.60 |
| markov_order1 | 0.0429 | 0.0483 | — | — |
| time_decay (14d) | 0.0485 | 0.0576 | direct | 0.37 |
| last_touch | 0.0505 | 0.0598 | direct | 0.43 |

### Where the models go wrong

Channel share of pipeline, truth vs model:

| Channel | Truth | First | Last | Linear | Decay | Position |
|---|---|---|---|---|---|---|
| paid_search | 0.201 | 0.152 | 0.146 | 0.151 | 0.151 | 0.150 |
| email_nurture | 0.121 | 0.079 | **0.206** | 0.155 | 0.186 | 0.146 |
| content_syndication | 0.121 | 0.176 | 0.086 | 0.110 | 0.086 | 0.123 |
| partner_referral | 0.113 | 0.057 | **0.025** | 0.043 | 0.037 | 0.042 |
| organic_search | 0.092 | 0.111 | 0.135 | 0.131 | 0.131 | 0.126 |
| direct | 0.080 | 0.083 | **0.180** | 0.169 | **0.195** | 0.143 |
| paid_social | 0.072 | 0.087 | 0.066 | 0.071 | 0.069 | 0.075 |
| field_event | 0.063 | 0.045 | 0.054 | 0.047 | 0.044 | 0.048 |

The pattern is structural, not random. Late-sitting, high-frequency channels (`direct`, `email_nurture`) absorb credit they did not earn. Early, once-per-journey channels (`partner_referral`, `content_syndication`) are systematically starved.

### Three findings worth arguing about

**1. No model gets partner referral right.** Truth says 11.3% of pipeline; the best model says 5.7%, the worst 2.5%. Every heuristic under-credits rare-but-decisive touches, because they all distribute credit by *position*, and position is a proxy for frequency. If a channel's value is concentrated in a single high-impact interaction, positional heuristics cannot see it. Incrementality testing, not better attribution math, is the answer.

**2. Half-life is a choice that moves the answer.** Time-decay's credit for `direct` swings from 20.2% to 17.9% as the half-life moves from 3 to 60 days — a 2.3-point spread from a parameter almost nobody documents. MAE also improves monotonically with longer half-lives, which means the industry-default 14 days is actively worse than 45 on this data. Always publish the half-life next to the number.

**3. A 30-day lookback window costs more accuracy than the model choice does.** Linear attribution's MAE falls from 0.0508 at a 30-day window to 0.0360 at 365 days. Switching from last-touch to position-based buys you 0.020; widening the window buys 0.015. Fix the window before arguing about the model.

### Markov ranked *below* the simple heuristics — and that's reported, not hidden

The Markov removal-effect model (MAE 0.0429) lost to position-based (0.0305) and even to first-touch. With 4,673 account paths and 668 conversions, the first-order transition matrix is too sparse to beat a well-chosen heuristic. The honest conclusion is that model sophistication is not free, and a Markov model needs volume most mid-market B2B companies do not have. Run `analysis/04_markov.py --bootstrap 200` to see the confidence intervals that make this concrete.

---

## Architecture

```
config/simulation.yml          all tunable parameters + TRUE channel effects
        |
generator/simulate.py          6,000 accounts, 24 months, deliberate defects
        |
raw/                           Segment-spec JSONL + Salesforce CSVs + ad spend
ground_truth/                  the answer key (never joined into a mart)
        |
warehouse/load_duckdb.py       EL only. no cleaning.
        |
dbt_project/                   29 models, 42 tests
  staging/        typed, deduped, date-parsed, UTM-normalised
  intermediate/   sessionisation -> identity graph -> touchpoint spine
  marts/          star schema: dim_account, dim_campaign, dim_date,
                  fct_touchpoints, fct_opportunities, fct_spend_daily,
                  mart_funnel_daily, mart_cohort_retention,
                  fct_segment_membership, mart_segment_overlap,
                  mart_data_quality
  attribution/    5 heuristic models -> vs truth -> scorecard
        |
analysis/                      Markov, sensitivity sweeps, segment export
spark/sessionize.py            same sessionisation in PySpark, parity-checked
governance/                    metric registry -> validated data dictionary
exports/tableau/               extracts for the published dashboard
```

### Scale

| | |
|---|---|
| Accounts | 6,000 |
| Segment events | 149,169 |
| Sessions (rebuilt) | 28,951 |
| Attributable touchpoints | 27,905 |
| Leads | 11,887 |
| Opportunities | 668 (213 won) |
| dbt models / tests | 29 / 42 |
| Full pipeline runtime | ~3 minutes on a laptop |

---

## Quickstart

```bash
git clone <your-repo-url> && cd mkt-intel
python -m venv .venv && source .venv/bin/activate
make install
make all
```

`make all` generates the world, loads it, builds and tests every model, validates the metric registry, runs every analysis, and writes Tableau extracts. Individual stages:

```bash
make generate ACCOUNTS=6000   # simulate
make load                     # land into DuckDB
make build                    # dbt seed + run
make test                     # 42 dbt tests
make docs                     # dbt docs + validated data dictionary
make analyse                  # funnel, cohorts, segments, markov, scorecard
make export                   # CSVs for Tableau
make spark                    # PySpark sessionizer + parity check
make smoke                    # fast 300-account end-to-end check
```

Full build instructions, including the BigQuery and Databricks paths, are in [`BUILD_GUIDE.md`](BUILD_GUIDE.md).

---

## Engineering notes

### Two real bugs the test suite caught

**Fan-out via duplicate leads.** `int_identity_graph` originally joined `stg_sfdc__leads` directly to resolve `account_id`. The source contains ~5.5% deliberate duplicate lead rows, so the join multiplied every downstream touchpoint — `unique_fct_touchpoints_touchpoint_id` failed with 609 duplicates, and attribution credit was silently inflated. Fix: pre-aggregate the lookup to one row per `person_id`. The test stays in place to stop it regressing. This is the single most valuable thing in the repo, because it is exactly how attribution quietly breaks in production.

**UTM normalisation by typo list doesn't scale.** The first `clean_utm` implementation was a hardcoded map of known misspellings. It passed at 300 accounts and failed at 6,000 when new leetspeak variants appeared (`llnkedln`, `link3din`, `dir3ct`). Replaced with a principled ladder — strip, reverse digit substitutions, repair the `in`/`ln` transposition, then a two-entry residual map. Fewer rules, broader coverage.

### Data quality, as detected by the pipeline

| Defect | Count | Handled by |
|---|---|---|
| Unresolved sessions | 9,499 | flagged, excluded from attribution, reported in trust panel |
| Bot sessions | 1,046 | dual heuristic (user agent + pageview burst) |
| Leads missing email | 427 | flagged, kept in funnel counts |
| Duplicate lead emails | 11 | normalised via `+alias` stripping |
| Unmapped UTM pairs | 0 | build fails above 5 touchpoints |

The 7-day `paid_social` tracking outage in September 2025 is detectable in `mart_funnel_daily` and is documented as a known limitation of `first_touch_channel` in the data dictionary — because the correct response to a gap is to annotate it, not to backfill a guess.

### Deliberate scope decisions

- **Identity resolution does not use IP or company-domain reverse lookup.** Both inflate account matching and are a common source of silent attribution error. Precedence is `identify()` call → email match → stays anonymous.
- **Attribution excludes post-opportunity touches.** Activity after opportunity creation is customer success, not acquisition. `assert_no_touch_after_opportunity` enforces it.
- **The Markov absorbing state is "opportunity created", not "closed won".** Win/loss is dominated by sales execution, and crediting marketing for it overstates the channel signal.
- **Ground truth lives in its own `truth` schema** and is referenced by exactly one model, `attr_model_vs_truth`. No mart can accidentally join the answer key.

---

## Repurposing this repo

The layers are independent, so the same codebase supports several role angles. Change the README emphasis, not the code:

| Role | Lead with | Point at |
|---|---|---|
| Marketing / growth analyst | attribution scorecard, channel diagnostics | `analysis/05_scorecard.py`, insight memo |
| Analytics engineer | star schema, 42 tests, metric registry | `dbt_project/`, `governance/` |
| Marketing ops | segment governance, versioning, activation exports | `fct_segment_membership`, `analysis/03_segments.py` |
| Product analyst | swap the outcome variable to retention | `config/simulation.yml` — everything downstream is reusable |

---

## Licence

MIT. The simulated data contains no real people or companies.
