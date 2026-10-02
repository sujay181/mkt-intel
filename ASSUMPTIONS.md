# Assumptions

Every number in `config/simulation.yml` is a modelling choice. This file records what each one is, why it was set that way, and what breaks if it is wrong. If you change a parameter, change the entry here in the same commit.

The benchmark ranges below come from widely published B2B SaaS figures (Gartner and Forrester buying-group research, SaaS Capital and OpenView benchmark reports, HubSpot and Demand Gen Report channel benchmarks, and Salesforce/Marketo funnel conversion studies). They are cited as *ranges*, not point estimates, because the underlying studies disagree with each other — which is itself a reason to treat any single attribution number with suspicion.

---

## Why simulate at all

The project's central claim is that attribution models can be scored. Scoring requires knowing the true per-touch contribution to each conversion. No production dataset contains that, because it is unobservable in principle — you cannot run the same buyer twice with and without the webinar.

So the choice is between:

1. Real data, unfalsifiable conclusions
2. Simulated data, falsifiable conclusions, documented assumptions

This project takes option 2 and states the assumptions openly. The correct criticism is not "it's synthetic" but "parameter X is unrealistic, and here's why that changes the conclusion" — which is a conversation worth having, and which this file exists to enable.

**What the simulation cannot tell you:** whether these specific channel effects hold at any real company. It tells you about the *structural behaviour of attribution models* given a known truth — that late-sitting high-frequency channels absorb credit under last-touch, that rare decisive touches are invisible to positional heuristics. Those findings transfer. The specific numbers do not.

---

## Volumes and shape

| Parameter | Value | Benchmark | Rationale & risk |
|---|---|---|---|
| `n_accounts` | 6,000 | — | Large enough that the Markov transition matrix is estimable and channel-level MAE is stable across seeds; small enough to run in ~3 min. Below ~2,000 the Markov model becomes seed-dependent. |
| `persons_per_account` | 1–6, mode 2 | Gartner: 6–10 for enterprise B2B | **Deliberately conservative.** A larger buying committee would increase touches per account and make multi-touch models look better relative to single-touch. Setting it low is the harder test for the project's thesis. |
| Date range | 24 months | — | Must exceed the longest sales cycle plus the 365-day lookback, or the cohort analysis truncates. |
| Region split | NA 45 / EMEA 30 / APAC 25 | — | Approximates a Brisbane-headquartered global infrastructure vendor. Affects nothing analytically; exists so regional filters are meaningful. |

## Funnel rates

| Parameter | Value | Benchmark range | Rationale & risk |
|---|---|---|---|
| `visitor_to_known_rate` | 0.26 | 1–5% site-wide; 20–40% on gated assets | This applies **per touch**, not per pageview, and only to touches that reach a form or gated asset. Not comparable to a site-wide conversion rate. |
| `known_to_mql_rate` | 0.41 | 25–50% | Mid-range. Raising it inflates MQL volume without changing attribution conclusions. |
| `mql_to_sql_rate` | 0.38 | 20–50% | Mid-range. |
| `sql_to_opp_rate` | 0.72 | 60–80% | |
| `opp_to_won_rate` | 0.235 | 15–30% | Combined with region multipliers gives a realised win rate near 32% on the generated data, at the high end. Marketing attribution conclusions are insensitive to this because the absorbing state is opportunity creation, not win. |
| `sales_cycle_days` | mean 88, sd 34 | 60–120 days mid-market; 6–12 months enterprise | **The most consequential parameter in the file.** It sets how far back the lookback window must reach. A longer cycle would widen the gap between the 30-day and 365-day window results, strengthening finding #3. |

## Deal size

| Parameter | Value | Rationale |
|---|---|---|
| `base_arr` | $41,000 | Mid-market network-as-a-service ACV. Multiplied by employee band (0.35x to 3.4x), giving a realistic range from ~$14k SMB to ~$140k enterprise. |
| `lognormal_sigma` | 0.62 | Produces a right-skewed distribution with a long tail, matching observed B2B deal-size distributions. A normal distribution would understate the influence of a handful of large deals on channel ROI. |

---

## Channel true effects — the core assumption

`true_effect` is the latent contribution of one touch on that channel to the conversion log-odds. These are the numbers the attribution models are trying to recover, and they are the most contestable thing in the project.

| Channel | true_effect | Position in journey | Why set this way |
|---|---|---|---|
| partner_referral | 0.95 | rare, mid | Warm introductions convert at multiples of cold channels across every published B2B benchmark. Set highest deliberately: it creates a channel that every positional heuristic fails on, which is finding #1. |
| field_event | 0.74 | rare, early | High-intent, high-cost, low-volume. |
| webinar | 0.68 | early, ~once | High engagement, long lag to conversion. |
| content_syndication | 0.55 | early, ~once | Paid lead-gen with real but front-loaded impact. |
| paid_search | 0.42 | entry + repeat | Captures existing intent rather than creating it. |
| email_nurture | 0.31 | repeat, late | Real but modest per-touch effect, high frequency. |
| paid_social | 0.22 | entry, early | Awareness-weighted. |
| organic_search | 0.18 | repeat, late | Navigational traffic from buyers already in-market. |
| direct | 0.12 | repeat, latest | **Lowest true effect, highest repeat weight, sits last.** This is the designed trap: `direct` is mostly buyers who already decided, arriving to complete an action. Last-touch credits it 2.2x its true contribution. |

**The design intent is stated openly because hiding it would be dishonest.** I chose effects that would expose known failure modes of positional attribution. The defence is that these orderings — warm referral high, direct low, nurture modest-but-frequent — are the consensus direction in the literature, even where the magnitudes are contested. If you believe `direct` genuinely drives 20% of pipeline rather than 8%, that is a substantive disagreement, and the way to settle it is a holdout test, not a model.

## Journey mechanics

| Parameter | Value | Rationale & risk |
|---|---|---|
| `touches_mean` | 4.3 | Published B2B ranges run 5–20+ touches. Set low deliberately: fewer touches is the harder case for multi-touch models to win. Realised mean is ~4.7 touches per account. |
| `decay_lambda` | 0.011/day | Half-life of roughly 63 days on the latent effect. **This is an assumption about memory, not about attribution.** It means a touch 60 days before the decision retains ~half its influence. If real decay is faster, short-window attribution looks better than this project concludes. |
| `saturation_k` | 0.62 | Each repeat touch on the same channel contributes 62% of the previous one. Without saturation, high-frequency channels would dominate the truth as well as the models, and the comparison would collapse. |
| `base_logit` | -3.05 | Tuned so ~14% of touched accounts produce an opportunity, giving 668 opportunities at 6,000 accounts. |
| `icp_coefficient` | 0.85 | Firmographic fit matters roughly as much as two good touches. Prevents the simulation implying marketing is the only driver of conversion. |

---

## Injected data defects

Each defect exists so a specific pipeline control can catch it. Rates are set high enough to be detectable at 6,000 accounts.

| Defect | Rate | Realistic? | Caught by |
|---|---|---|---|
| Dirty UTMs | 8.5% | High but plausible where UTM governance is manual | `clean_utm` macro + `assert_no_unmapped_utm_source` |
| Duplicate leads | 5.5% | Typical for un-deduplicated CRM | `email_normalised` + `unique_fct_touchpoints_touchpoint_id` |
| Bot sessions | 2.1% | Conservative; real crawler traffic often exceeds 10% | Dual heuristic in `int_sessions` |
| Null emails | 3.4% | Typical | Flagged, not dropped |
| Mixed date formats | 12% | Common in CSV exports crossing locales | `parse_mixed_date` macro |
| Tracking outage | 7 days, paid_social | Happens to everyone | `mart_data_quality`, annotated in dashboard |
| Campaign rename | 1 campaign | Happens constantly | `campaign_name_original` + `campaign_name_current` |
| Spend late arrival | 3 days | Standard for ad platforms | Join on `spend_date`, never `booked_date` |

---

## Known limitations of the simulation

These are real weaknesses. State them before someone else does.

1. **First-order journey structure.** Channel selection for touch *n* depends only on whether it is the first touch, not on the preceding channel. Real journeys have sequence logic (a webinar tends to be followed by email nurture). This makes the Markov model's first-order assumption artificially *correct* — so the Markov result here is, if anything, flattering to Markov, and it still lost.

2. **No competitive or macro effects.** No seasonality, no competitor activity, no budget cycles. A real Q4 spike would change channel mix in ways the models would have to absorb.

3. **Offline touches are invisible.** Sales calls, booth conversations and word of mouth do not exist in the simulation. In reality they carry real effect that shows up as unexplained conversion — which is one reason `direct` over-credits in production even more than it does here.

4. **One opportunity per account.** No expansion, no renewal, no multi-product. Fine for acquisition attribution; useless for lifetime value.

5. **Conversion is a single latent draw.** Real buying decisions are committee processes with internal disagreement. The model collapses that into one probability.

6. **Win/loss is only weakly linked to marketing.** Deliberate — but it means this project cannot say anything about which channels produce *better* customers, only which produce pipeline.

---

## Reproducibility

Every run is deterministic given `seed`. `ground_truth/run_manifest.json` records the seed, the date range, row counts and a SHA-1 digest of the full config, so any figure in the README can be traced to the exact configuration that produced it.

To verify a claim in the README:

```bash
make generate ACCOUNTS=6000 && make load && make build && make analyse
```

To test robustness to the seed, change `seed` in `config/simulation.yml` and re-run. The model *ranking* should be stable; the MAE values will move by roughly ±0.003.
