# Build Guide

Everything needed to build, run, extend and present this project. Work through it in order; each phase produces something demonstrable on its own, so you can stop at any phase boundary and still have something to show.

**Total effort: roughly 3–4 focused weekends.** The repo already contains working code for every phase — this guide tells you what to run, what to verify, and what to write up.

---

## 0. Environment

### Requirements

- Python 3.10+ (3.12 recommended)
- Git
- 2 GB free disk
- No database server, no cloud account, no credit card

### Setup

```bash
git clone <your-repo-url> && cd mkt-intel
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
make install
```

`make install` installs `requirements.txt` and runs `dbt deps`.

### Verify in under a minute

```bash
make smoke
```

This generates 300 accounts, loads them, builds all 29 models and runs all 42 tests. Expect `PASS=29` then `PASS=42`. If both pass, your environment is correct and everything else in this guide will work.

### If `dbt deps` fails

`hub.getdbt.com` is unreachable from some corporate networks and CI runners. `packages.yml` already uses the git form of `dbt_utils`, which works anywhere GitHub is reachable. The hub form is commented above it if you prefer.

### If DuckDB complains about the `json` extension

Remove any `extensions: [json]` line from `dbt_project/profiles.yml`. JSON is statically linked in DuckDB 1.x and declaring it triggers a download that some networks block.

---

## Phase 1 — Generate the world *(half a day)*

**Goal:** working raw data and ground truth. Ship this before touching anything else.

```bash
make generate ACCOUNTS=6000
```

Runs in about 90 seconds. Produces:

```
raw/segment_events/events_YYYY-MM.jsonl   149k Segment-spec events
raw/salesforce/*.csv                       accounts, leads, contacts, campaigns,
                                           campaign_members, opportunities,
                                           opportunity_stage_history
raw/ad_platforms/spend.csv                 20k daily spend rows
ground_truth/account_touch_credit.csv      THE ANSWER KEY
ground_truth/channel_contribution.csv      aggregated truth by channel
ground_truth/run_manifest.json             seed, row counts, config digest
```

### Verify

```bash
python -c "
import pandas as pd
t = pd.read_csv('ground_truth/channel_contribution.csv')
print(t[['channel','true_share_of_arr','configured_true_effect']].to_string(index=False))"
```

You should see nine channels with shares summing to 1.0, and `partner_referral` with a high configured effect but modest share (it is rare). If every channel has nearly identical share, the journey model is not differentiating — check `decay_lambda` and `saturation_k`.

### Tuning

Everything lives in `config/simulation.yml`. The three parameters worth adjusting:

- `base_logit` — controls how many accounts convert. Target 12–16%. More negative means fewer.
- `touches_mean` — controls path length. Below 3 the multi-touch comparison gets thin.
- `n_accounts` — below 2,000 the Markov model becomes seed-dependent.

After any change, re-run and check `run_manifest.json` for the new `config_digest`. Record it if you quote numbers from that run.

### Write up

Start `ASSUMPTIONS.md` now, while the parameter choices are fresh. It is far harder to reconstruct three weeks later, and it is the document that answers "isn't synthetic data a cop-out?"

---

## Phase 2 — Warehouse and staging *(one day)*

**Goal:** typed, tested, documented staging layer over dirty raw data.

```bash
make load
cd dbt_project && DBT_PROFILES_DIR=. dbt run --select staging && DBT_PROFILES_DIR=. dbt test --select staging
```

### What the staging layer must handle

| Defect | Model | Mechanism |
|---|---|---|
| Duplicate Segment messages | `stg_segment__events` | `row_number()` on `message_id` |
| Nested JSON | `stg_segment__events` | `json_extract_string` into typed columns |
| Dirty UTMs | `stg_segment__events` | `clean_utm` macro |
| Mixed date formats | all SFDC models | `parse_mixed_date` macro |
| `+alias` duplicate emails | `stg_sfdc__leads` | `email_normalised` |
| Campaign rename | `stg_sfdc__campaigns` | both `_original` and `_current` names |
| Late-arriving spend | `stg_ads__spend` | keeps both dates, documents which to join on |

### Verify

```sql
-- should return zero rows
select utm_source, count(*) from staging.stg_segment__events
where utm_source ~ '[0-9]' and utm_source not in ('on24')
group by 1;
```

### Extending to BigQuery

Uncomment the `bq` target in `profiles.yml`, create a free BigQuery sandbox project (no card required), then:

```bash
pip install dbt-bigquery
gcloud auth application-default login
cd dbt_project && DBT_PROFILES_DIR=. dbt run --target bq
```

The only dialect-specific code is in `macros/cross_db.sql`, which already branches on `target.type`. If a model fails on BigQuery, the fix belongs in that macro, not in the model.

---

## Phase 3 — Intermediate and marts *(one day)*

**Goal:** star schema and the touchpoint spine.

```bash
make build && make test
```

### The four models that matter

**`int_sessions`** — rebuilds sessions with a 30-minute timeout rather than trusting the client `session_id`. Be ready to explain why: client session IDs are device-local, reset across subdomains, and are trivially spoofed.

**`int_identity_graph`** — resolves `anonymous_id` → `person_id` → `account_id`. Precedence is `identify()` call, then email match, then unresolved. **It deliberately does not use IP or domain reverse-lookup.** That is a defensible analytical decision and a good interview answer.

> **This is where the fan-out bug lives.** The lookups from `person_id` to `account_id` must be pre-aggregated, because the lead source contains duplicates. Joining the raw lead table multiplies every downstream touchpoint. The `unique_fct_touchpoints_touchpoint_id` test catches it. Read that CTE and understand it — it is the most interview-relevant code in the repo.

**`int_touchpoints`** — the spine. Every attribution model reads this and nothing else. Inclusion rules are documented in `governance/metrics.yml` under `touchpoint`.

**`int_opportunity_touch_paths`** — joins touches to the opportunities they preceded, inside the lookback window, excluding post-creation activity.

### Verify

```sql
select count(*) as touchpoints,
       count(distinct account_id) as accounts,
       avg(path_length) as avg_path
from intermediate.int_opportunity_touch_paths;
```

Expect roughly 27,900 touchpoints and an average path around 4–5.

---

## Phase 4 — Attribution *(one to two days — the headline)*

**Do not let this phase slip to last.** It is the reason the project exists.

```bash
cd dbt_project && DBT_PROFILES_DIR=. dbt run --select attribution
cd .. && python analysis/04_markov.py
python analysis/05_scorecard.py
```

### What each piece does

- `attr_heuristic_models` — five credit rules on identical paths, so differences come only from the rule
- `attr_channel_rollup` — long format, one row per (model, channel), the shape Tableau wants
- `attr_model_vs_truth` — the only model that touches the `truth` schema
- `attr_model_scorecard` — MAE, RMSE, rank correlation per model
- `analysis/04_markov.py` — removal-effect model, the only one that uses non-converting paths
- `analysis/05_scorecard.py` — sensitivity sweeps and the dollar-impact table

### The Markov model in one paragraph

Heuristics ask "how do I split credit across touches that happened?" Markov asks "if this channel vanished, how much conversion would I lose?" It needs the **negative paths** — accounts touched but never converted — which no heuristic model sees. That is the methodological difference, and it is the thing to say out loud in an interview.

Run with confidence intervals before you quote it:

```bash
python analysis/04_markov.py --bootstrap 200
```

Takes about two minutes. If the intervals overlap heavily across channels, say so — that is the finding.

### The two sensitivity sweeps

These matter more than the ranking. Anyone can report that multi-touch beat last-touch. Showing that time-decay's answer moves 2.3 points when you change an undocumented default, and that the lookback window costs more accuracy than the model choice does, demonstrates you understand these are assumptions rather than measurements.

### Write up

`analysis/05_scorecard.py` prints your headline dollar figure. That sentence is the first line of your insight memo and the first line of your README.

---

## Phase 5 — Segments and governance *(half a day)*

```bash
python analysis/03_segments.py --export
python governance/build_dictionary.py
```

### The governance argument

Every audience is defined once in `fct_segment_membership.sql` and registered in `seeds/segment_definitions.csv` with an owner, a version and an `effective_from` date. Rebuilding a segment inside Marketo or LinkedIn is prohibited, because it creates a definition the warehouse cannot see or audit.

`mart_segment_overlap` computes pairwise Jaccard index. Any pair above 0.30 is a message-collision risk — the same accounts are in multiple programs — and needs a documented suppression rule or a merge.

`governance/build_dictionary.py` renders `metrics.yml` into `docs/DATA_DICTIONARY.md` **and validates every model and column reference against the live warehouse**, exiting 1 on drift. It runs in CI. Documentation that is not validated is documentation that is wrong.

### Adding a segment

1. Add a CTE to `fct_segment_membership.sql`
2. Add a row to `seeds/segment_definitions.csv`
3. `make build && make test`

Nothing else changes. That is the point.

---

## Phase 6 — PySpark *(half a day, optional but listed on the JD)*

```bash
pip install pyspark==3.5.1
make spark
```

### Why it exists

Not because 149k rows need Spark. Because running the **same business logic in two engines** is the honest way to show a metric definition must survive a change of compute. `analysis/06_parity_check.py` asserts the two agree within 0.5% and fails loudly otherwise.

The `clean_utm` ladder in `macros/cross_db.sql` and the `clean()` function in `spark/sessionize.py` implement an identical sequence. If you change one, change both — the parity check will tell you if you forgot.

### On Databricks Community Edition

1. Sign up at community.cloud.databricks.com (free, no card)
2. Upload `raw/segment_events/*.jsonl` to `/FileStore/mkt/segment_events/`
3. Create a cluster — Community gives one free driver-only node
4. Paste `spark/sessionize.py` into a notebook, set `INPUT = "dbfs:/FileStore/mkt/segment_events/*.jsonl"`
5. Screenshot the notebook for your README

The free cluster terminates after two hours of idle. Re-create it; nothing is lost.

---

## Phase 7 — Dashboard *(one day)*

```bash
make export
```

Writes eleven CSVs to `exports/tableau/`. Full build instructions — sheet by sheet, with joins, calculated fields and the parameter control — are in [`docs/TABLEAU_BUILD.md`](docs/TABLEAU_BUILD.md).

**Use Tableau Public specifically.** It gives a public link you can paste into an application. Power BI has no free equivalent.

---

## Phase 8 — The two artifacts that get interviews *(half a day)*

The repo is necessary but not sufficient. Hiring managers read a page; they rarely clone a repo.

### The insight memo

One page. Use `docs/INSIGHT_MEMO.md` as the template. Structure:

1. The recommendation, in one sentence with a dollar figure
2. The evidence, in three bullets
3. What would change your mind
4. What you would do next

The fourth section is what separates an analyst from a dashboard operator.

### The walkthrough video

Two minutes, screen recording, no face needed. Sequence:

- 0:00–0:20 — the headline number and what it means
- 0:20–1:00 — the dashboard, one filter interaction
- 1:00–1:30 — the scorecard, and why ground truth makes it possible
- 1:30–2:00 — one bug the test suite caught

Link both at the top of the README.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `dbt deps` 403 on hub.getdbt.com | Network blocks the dbt hub | Already using the git form in `packages.yml` |
| `HTTPException: Failed to download extension "json"` | Network blocks DuckDB extension CDN | Remove `extensions: [json]` from `profiles.yml` |
| `Parser Error: syntax error at or near "positional"` / `"cost"` / `"share"` | DuckDB reserved words | Rename the CTE or alias. Reserved words differ by engine — a real portability lesson worth mentioning |
| `unique_fct_touchpoints_touchpoint_id` fails | A join fanned out, almost certainly on duplicate leads | Pre-aggregate the lookup to one row per key |
| `assert_no_unmapped_utm_source` fails | New UTM variant not covered by the cleaning ladder | Extend `clean_utm` **and** the Spark `clean()`, then re-run parity |
| `assert_pipeline_conservation` fails | Credit rule leaks or double-counts | Check that credit sums to exactly 1.0 per opportunity |
| Markov MAE wildly unstable between runs | Too few conversions | Raise `ACCOUNTS`, or report the instability as a finding |
| `float() argument must be... not 'NAType'` | pandas nullable dtype in division | Use `float("nan")` rather than `pd.NA` |
| Tableau Public won't connect | It cannot read DuckDB files | Connect to `exports/tableau/*.csv` |

---

## What to do when someone challenges the project

**"Synthetic data isn't real analysis."** The project's claim is about the structural behaviour of attribution models given a known truth. That requires ground truth, which no real dataset has. `ASSUMPTIONS.md` documents every parameter against published benchmarks, and the findings that transfer are structural, not numeric.

**"You designed the data to make last-touch fail."** Yes, and it says so in `ASSUMPTIONS.md`. The parameter orderings — warm referral high, direct low, nurture modest-but-frequent — match the consensus direction in the literature even where magnitudes are contested. If you think `direct` genuinely drives 20% of pipeline, that is a substantive disagreement settled by holdout testing, not by a model.

**"Why didn't Markov win?"** Because 668 conversions across 4,673 paths make the transition matrix sparse. Reporting that honestly is better than rigging a win. It is also the practical finding: most mid-market B2B companies do not have the volume for a Markov model, and should not buy a tool that sells them one.

**"What would you do differently at a real company?"** Run geo or audience holdout tests on the two channels the models disagree about most. Attribution models reconcile observational data; only an experiment measures incrementality. Saying this unprompted is the strongest single thing you can do in an attribution interview.
