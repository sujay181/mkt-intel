{{ config(materialized='table') }}

-- One row per model. MAE and RMSE are on channel SHARE of pipeline, so they
-- are directly comparable across models and interpretable as percentage points.
-- rank_correlation tells you whether a model at least gets the ORDER right,
-- which is often all a budget conversation needs.

with e as (select * from {{ ref('attr_model_vs_truth') }}),
ranked as (
    select model_name, channel,
           rank() over (partition by model_name order by modelled_share_of_arr desc) as model_rank,
           rank() over (partition by model_name order by true_share_of_arr desc)     as true_rank
    from e
),
spearman as (
    select model_name,
        1 - (6.0 * sum(power(model_rank - true_rank, 2)))
            / (count(*) * (power(count(*), 2) - 1)) as rank_correlation
    from ranked group by 1
)
select
    e.model_name,
    count(*)                                   as channels_evaluated,
    avg(e.abs_share_error)                     as mae_share,
    sqrt(avg(power(e.share_error, 2)))         as rmse_share,
    max(e.abs_share_error)                     as worst_channel_error,
    (select channel from e e2 where e2.model_name = e.model_name
     order by abs_share_error desc limit 1)    as worst_channel,
    count(*) filter (where e.verdict = 'within 15%') as channels_within_15pct,
    s.rank_correlation
from e
join spearman s on s.model_name = e.model_name
group by e.model_name, s.rank_correlation
order by mae_share
