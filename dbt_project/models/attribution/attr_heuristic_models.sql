{{ config(materialized='table') }}

-- Four heuristic attribution models, computed side by side on the SAME path
-- table so differences come only from the credit rule, never from the data.
--
--   first_touch : 100% to touch_position = 1
--   last_touch  : 100% to the final pre-opp touch
--   linear      : 1 / path_length to every touch
--   time_decay  : 2^(-days_before_opp / half_life), normalised per opportunity
--   position_40_20_40 : 40% first, 40% last, 20% spread across the middle
--
-- half_life is 14 days, the most common vendor default (GA4, Adobe). It is a
-- CHOICE, not a fact — analysis/05_scorecard.py sweeps it from 3 to 60 days to
-- show how much the answer moves.

{% set half_life = 14 %}

with paths as (
    select * from {{ ref('int_opportunity_touch_paths') }}
),

decay as (
    select *,
        power(2.0, -1.0 * days_before_opp / {{ half_life }}) as decay_weight
    from paths
),

decay_norm as (
    select *,
        decay_weight / sum(decay_weight) over (partition by opportunity_id) as time_decay_credit
    from decay
),

position_weighted as (
    select *,
        case
            when path_length = 1 then 1.0
            when path_length = 2 then 0.5
            when touch_position = 1 then 0.40
            when touch_position_desc = 1 then 0.40
            else 0.20 / (path_length - 2)
        end as position_credit
    from decay_norm
)

select
    opportunity_id,
    account_id,
    touchpoint_id,
    touch_ts,
    touch_date,
    channel,
    channel_group,
    campaign_id,
    campaign_name_current as campaign_name,
    region,
    is_won,
    is_closed,
    amount_arr_usd,
    touch_position,
    touch_position_desc,
    path_length,
    days_before_opp,

    case when touch_position = 1 then 1.0 else 0.0 end        as credit_first_touch,
    case when touch_position_desc = 1 then 1.0 else 0.0 end   as credit_last_touch,
    1.0 / path_length                                          as credit_linear,
    time_decay_credit                                          as credit_time_decay,
    position_credit                                            as credit_position_based
from position_weighted
