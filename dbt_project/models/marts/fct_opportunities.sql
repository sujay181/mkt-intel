{{ config(materialized='table') }}
with paths as (
    select opportunity_id, count(*) as touch_count,
           count(distinct channel) as distinct_channels,
           min(touch_ts) as first_touch_ts, max(touch_ts) as last_touch_ts
    from {{ ref('int_opportunity_touch_paths') }} group by 1
),
ft as (
    select opportunity_id, channel as first_touch_channel, campaign_id as first_touch_campaign_id
    from (select *, row_number() over (partition by opportunity_id order by touch_ts) rn
          from {{ ref('int_opportunity_touch_paths') }}) where rn = 1
),
lt as (
    select opportunity_id, channel as last_touch_channel, campaign_id as last_touch_campaign_id
    from (select *, row_number() over (partition by opportunity_id order by touch_ts desc) rn
          from {{ ref('int_opportunity_touch_paths') }}) where rn = 1
)
select
    o.opportunity_id, o.account_id, o.opportunity_name,
    o.opportunity_created_date, o.close_date, o.stage,
    o.is_closed, o.is_won, o.amount_arr_usd, o.sales_cycle_days,
    o.region, o.industry,
    a.icp_tier, a.employee_band, a.account_name,
    coalesce(p.touch_count, 0)      as touch_count,
    coalesce(p.distinct_channels, 0) as distinct_channels,
    p.first_touch_ts, p.last_touch_ts,
    ft.first_touch_channel, ft.first_touch_campaign_id,
    lt.last_touch_channel,  lt.last_touch_campaign_id,
    date_diff('day', cast(p.first_touch_ts as date), o.opportunity_created_date) as days_first_touch_to_opp,
    p.touch_count is null as is_unattributed
from {{ ref('stg_sfdc__opportunities') }} o
left join {{ ref('dim_account') }} a on a.account_id = o.account_id
left join paths p  on p.opportunity_id = o.opportunity_id
left join ft       on ft.opportunity_id = o.opportunity_id
left join lt       on lt.opportunity_id = o.opportunity_id
