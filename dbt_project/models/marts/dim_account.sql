{{ config(materialized='table') }}
with first_touch as (
    select account_id,
           min(touch_ts)  as first_touch_ts,
           min(channel)   as first_touch_channel_alpha,
           count(*)       as lifetime_touches,
           count(distinct channel) as distinct_channels
    from {{ ref('int_touchpoints') }}
    where is_attributable
    group by 1
),
ft_channel as (
    select account_id, channel as first_touch_channel
    from (
        select account_id, channel,
               row_number() over (partition by account_id order by touch_ts) rn
        from {{ ref('int_touchpoints') }} where is_attributable
    ) where rn = 1
),
opps as (
    select account_id,
           count(*)                                  as opportunity_count,
           sum(case when is_won then 1 else 0 end)   as won_count,
           sum(case when is_won then amount_arr_usd else 0 end) as won_arr_usd,
           min(opportunity_created_date)             as first_opp_created_date
    from {{ ref('stg_sfdc__opportunities') }} group by 1
)
select
    a.account_id, a.account_name, a.industry, a.employee_band,
    a.region, a.country, a.icp_score_raw, a.icp_tier, a.account_created_date,
    f.first_touch_ts, fc.first_touch_channel,
    coalesce(f.lifetime_touches, 0)  as lifetime_touches,
    coalesce(f.distinct_channels, 0) as distinct_channels,
    coalesce(o.opportunity_count, 0) as opportunity_count,
    coalesce(o.won_count, 0)         as won_count,
    coalesce(o.won_arr_usd, 0)       as won_arr_usd,
    o.first_opp_created_date,
    o.opportunity_count > 0          as has_opportunity,
    coalesce(o.won_count, 0) > 0     as is_customer
from {{ ref('stg_sfdc__accounts') }} a
left join first_touch f on f.account_id = a.account_id
left join ft_channel fc on fc.account_id = a.account_id
left join opps o       on o.account_id = a.account_id
