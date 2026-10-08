{{ config(materialized='table') }}

-- Joins every attributable touch to the opportunity it preceded, inside the
-- lookback window. This is the input to every attribution model.
-- A touch AFTER the opportunity create date is excluded: post-create activity
-- is customer success, not acquisition, and including it is the #1 way to
-- accidentally credit email_nurture for deals it did not source.

with opps as (
    select * from {{ ref('stg_sfdc__opportunities') }}
),

joined as (
    select
        o.opportunity_id,
        o.account_id,
        o.opportunity_created_date,
        o.close_date,
        o.is_won,
        o.is_closed,
        o.amount_arr_usd,
        o.region,
        t.touchpoint_id,
        t.touch_ts,
        t.touch_date,
        t.channel,
        t.channel_group,
        t.is_paid,
        t.campaign_id,
        t.campaign_name_current,
        date_diff('day', t.touch_date, o.opportunity_created_date) as days_before_opp
    from opps o
    join {{ ref('int_touchpoints') }} t
      on t.account_id = o.account_id
     and t.touch_date <= o.opportunity_created_date
     and t.touch_date >= o.opportunity_created_date - interval '{{ var("touch_lookback_days") }}' day
    where t.is_attributable
)

select
    *,
    row_number() over (partition by opportunity_id order by touch_ts)       as touch_position,
    row_number() over (partition by opportunity_id order by touch_ts desc)  as touch_position_desc,
    count(*)     over (partition by opportunity_id)                          as path_length
from joined
