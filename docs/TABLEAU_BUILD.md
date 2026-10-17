# Tableau Public Build Guide

Sheet-by-sheet instructions for the published dashboard. Uses Tableau Public (free) because it produces a shareable link; Power BI has no free equivalent.

## Data source setup

Run `make export` first. Then in Tableau Public:

1. **Connect** → Text File → `exports/tableau/funnel_daily.csv`
2. Drag in the other CSVs and build these relationships (use *relationships*, the noodle, not joins — it avoids fan-out on the many-to-many pairs):

| Left | Right | On |
|---|---|---|
| `funnel_daily` | `accounts` | (none — separate sheets) |
| `opportunities` | `accounts` | `account_id` |
| `attribution_channel_rollup` | `attribution_vs_truth` | `model_name`, `channel` |
| `segment_membership` | `accounts` | `account_id` |
| `cohort_retention` | (standalone) | |
| `data_quality` | (standalone) | |

Set every date field's data type to Date, not String — Tableau guesses wrong on ISO strings in about a third of cases.

---

## Calculated fields

Create these once; every sheet uses them.

```
// Pipeline ROAS, suppressed where cost is meaningless
[ROAS] =
IF SUM([Cost Usd]) < 100 THEN NULL
ELSE SUM([Opp Pipeline Usd]) / SUM([Cost Usd]) END

// MQL to SQL rate
[MQL to SQL] = SUM([Sqls]) / NULLIF(SUM([Mqls]), 0)

// Attribution error in percentage points
[Share Error PP] = (SUM([Modelled Share Of Arr]) - SUM([True Share Of Arr])) * 100

// Budget implication at a parameterised spend level
[Budget Implication] = SUM([Modelled Share Of Arr]) * [Annual Budget]

// Data quality rate
[DQ Rate] = SUM([Value]) / NULLIF(SUM([Denominator]), 0)

// Trust banding — drives the warning colour
[DQ Status] =
IF [DQ Rate] > 0.05 THEN "Fail"
ELSEIF [DQ Rate] > 0.02 THEN "Warn"
ELSE "OK" END
```

## Parameters

| Parameter | Type | Values | Used by |
|---|---|---|---|
| `Annual Budget` | Float | 500,000 – 5,000,000, step 100,000 | Budget implication sheet |
| `Attribution Model` | String | list from `model_name` | Model comparison sheet |
| `Date Grain` | String | Day / Week / Month | Trend sheets |

---

## Dashboard 1 — Channel Performance

**Purpose:** what each channel produced and what it cost. The view a demand gen lead opens on Monday.

| Sheet | Type | Marks | Notes |
|---|---|---|---|
| KPI strip | Text tables ×5 | Pipeline, Opps, MQLs, Cost, ROAS | Big numbers, no decimals on currency |
| Pipeline trend | Line | `month_start_date` × `SUM(Opp Pipeline Usd)`, colour by `channel` | Add a reference band over Sep 2025 labelled "paid_social tracking outage" |
| Channel table | Highlight table | `channel` rows; Leads, MQLs, SQLs, Opps, Cost/Opp, ROAS | Colour ROAS column only |
| Volume × quality | Scatter | X `SUM(Leads)`, Y `[MQL to SQL]`, size `SUM(Opp Pipeline Usd)`, label `channel` | Add median reference lines on both axes to create the four quadrants |
| Region split | Stacked bar | `region` × pipeline, colour `channel` | |

**Filters:** date range, region, fiscal quarter. Apply to all sheets using this data source.

---

## Dashboard 2 — Attribution Comparison

**Purpose:** the headline. This is the dashboard you screenshot for applications.

| Sheet | Type | Detail |
|---|---|---|
| Model small multiples | Bar, columns = `model_name` | Rows `channel`, bars `SUM(Credited Pipeline Usd)`. Sort channels consistently across all panels or the comparison is unreadable |
| Truth overlay | Bar + reference line | Per channel: bars = modelled share, black reference line = `true_share_of_arr`. This single chart is the whole project |
| Error chart | Diverging bar | `[Share Error PP]` by channel, filtered to `[Attribution Model]` parameter. Red right, blue left, zero centred |
| Scorecard | Text table | From `attribution_scorecard.csv`: model, MAE, RMSE, worst channel, rank correlation. Sort by MAE ascending |
| Budget implication | Side-by-side bar | Budget if truth vs budget if selected model, by channel, using `[Annual Budget]` parameter |

**Caption to put directly on the dashboard, not in a tooltip:**

> Ground truth is known because this dataset is simulated. Model error is measured, not estimated. See ASSUMPTIONS.md.

Without that line a viewer assumes the truth column is another model, and the point is lost.

---

## Dashboard 3 — Cohorts & Payback

| Sheet | Type | Detail |
|---|---|---|
| Payback curve | Line | X `months_since_first_touch`, Y cumulative % of lifetime pipeline, colour `first_touch_channel` |
| Cohort heatmap | Heat map | Rows `cohort_month`, columns `months_since_first_touch`, colour = conversion rate |
| 30-day visibility | Bar | Share of lifetime pipeline visible within 30 days, by channel, sorted ascending |

The third sheet is the argument for a longer attribution window. Channels at the left of that bar chart are the ones a short window silently defunds.

---

## Dashboard 4 — Segments & Data Trust

| Sheet | Type | Detail |
|---|---|---|
| Segment sizes | Bar | Accounts per segment, labelled with owner and version |
| Overlap matrix | Heat map | `segment_a` × `segment_b`, colour = Jaccard. Annotate anything above 0.30 |
| Segment quality | Scatter | X segment size, Y % with opportunity, size = won ARR |
| Trust panel | Line ×5 | One line per DQ metric over time, coloured by `[DQ Status]` |
| Outage annotation | Text | Fixed callout describing the Sept 2025 gap |

The trust panel is what makes the rest of the dashboard credible. Put it on the same tab as the segment work rather than hiding it behind a menu.

---

## Publishing

1. Server → Tableau Public → Save to Tableau Public As…
2. Sign in (free account)
3. In your profile, set the workbook to **Show** and enable **Allow others to download**
4. Set the thumbnail to Dashboard 2 — the attribution comparison is the hook
5. Copy the link into the README table and into your CV

## Presentation notes

- Sort channels identically on every chart. Inconsistent ordering is the fastest way to look careless.
- Round currency to whole dollars and rates to one decimal. Six decimal places signal a raw export, not an analysis.
- Every dashboard needs a one-line subtitle stating what decision it supports. If you cannot write that line, the dashboard does not have a purpose.
- Put the "simulated data, known ground truth" caption on Dashboard 2 in visible text, not a tooltip.
