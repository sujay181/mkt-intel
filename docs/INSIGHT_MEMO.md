# Reallocating paid budget on evidence, not attribution convention

**To:** VP Marketing
**From:** [Your name], Marketing Analytics
**Date:** [Date]
**One line:** Our last-touch reporting misallocates roughly **$454,000 of a $2.0M annual paid budget** — about 23% — by over-crediting channels that sit late in the buying journey and starving the ones that start it.

---

## What I found

**1. Last-touch over-credits `direct` by 2.2x and under-credits `partner_referral` by 4.6x.**
Measured against known per-touch contribution, `direct` accounts for 8.0% of pipeline but last-touch assigns it 18.0%. `partner_referral` truly contributes 11.3% and receives 2.5%. The bias is structural: `direct` is where buyers arrive once they have already decided, so it collects credit for decisions made elsewhere.

**2. Our 30-day attribution window costs more accuracy than our choice of model.**
Widening the lookback from 30 days to 365 improves attribution error from 0.051 to 0.036. Switching from last-touch to a position-based model improves it by 0.020. The window is the bigger lever and the cheaper fix — it is a configuration change, not a new tool.

**3. No attribution model correctly values partner referral.**
The best-performing model still under-credits it by half. Every positional heuristic distributes credit by *where* a touch sits, which is a proxy for *how often* it appears. A channel whose value is concentrated in one decisive interaction is invisible to all of them. This is a limitation of the method, not a tuning problem.

---

## What I recommend

1. **Change the reporting window from 30 to 180 days this quarter.** Configuration only, no vendor involved, recovers most of the measurable error.
2. **Report position-based alongside last-touch for one quarter** rather than switching outright, so the team can see where the two disagree before budget moves.
3. **Run a geo holdout on partner referral and content syndication in Q2.** These are the two channels the models disagree about most, and a holdout is the only way to measure incrementality rather than correlation.

Expected effect of (1) and (2): a shift of roughly $180k from `direct`- and `email_nurture`-attributed spend toward `partner_referral` and `content_syndication`. I would move it in two tranches, not one.

---

## What would change my mind

- **If a holdout shows partner referral is not incremental**, the models are closer to right than I am, and recommendation 3 is what surfaces that. I would rather be corrected by an experiment than be confidently wrong in a dashboard.
- **If our real decay is much faster than assumed** — buyers forgetting a webinar within two weeks rather than two months — short-window attribution is more defensible than this analysis concludes.
- **If a large share of `direct` is genuinely undetected referral** from dark social or partner conversations, then `direct` is not over-credited, it is mislabelled, and the fix is tracking rather than modelling.

---

## What I would do next

1. Geo holdout design for the two contested channels, sized for a 90-day read
2. Add post-opportunity touches as a separate expansion-attribution view, so lifecycle marketing is measured on its own outcome rather than borrowing acquisition credit
3. Instrument dark social and partner-sourced traffic to reduce the `direct` bucket at source

---

## Method and limitations

Analysis run on a simulated dataset of 6,000 accounts over 24 months where the true per-touch contribution is known by construction, which is what makes model error measurable rather than assumed. Five heuristic models plus a first-order Markov removal-effect model were scored against that truth.

The Markov model performed worse than simple heuristics here (error 0.043 vs 0.031), because 668 conversions across 4,673 paths leave the transition matrix too sparse. That argues against buying a Markov-based tool at our current volume.

Findings that transfer are structural — the direction and mechanism of each bias. The specific percentages are properties of this dataset. Full parameter documentation in `ASSUMPTIONS.md`.

---

*Replace bracketed fields and the recommendation figures if you re-run with a different seed or budget.*
