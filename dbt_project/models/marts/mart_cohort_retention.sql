{{ config(materialized='table') }}

-- Account cohorts by FIRST TOUCH MONTH. Measures how long it takes each
-- acquisition cohort to produce pipeline, and how much. This is the view that
-- exposes channels with long payback — content_syndication and field_event
-- look terrible in a 30-day window and excellent at month 9.

with cohorts as (
    select account_id, first_touch_channel, region, icp_tier,
           date_trunc('month', first_touch_ts)::date as cohort_month
    from {{ ref('dim_account') }} where first_touch_ts is not null
),
opp_months as (
    select c.account_id, c.cohort_month, c.first_touch_channel, c.region, c.icp_tier,
           date_diff('month', c.cohort_month,
                     date_trunc('month', o.opportunity_created_date)::date) as months_since_first_touch,
           o.amount_arr_usd, o.is_won
    from cohorts c
    join {{ ref('fct_opportunities') }} o on o.account_id = c.account_id
),
sized as (
    select cohort_month, first_touch_channel, region,
           count(distinct account_id) as cohort_accounts
    from cohorts group by 1,2,3
)
select
    s.cohort_month, s.first_touch_channel, s.region, s.cohort_accounts,
    coalesce(m.months_since_first_touch, 0) as months_since_first_touch,
    count(distinct m.account_id)            as accounts_with_opp,
    sum(coalesce(m.amount_arr_usd, 0))      as pipeline_usd,
    sum(case when m.is_won then coalesce(m.amount_arr_usd, 0) else 0 end) as won_arr_usd,
    {{ safe_divide('count(distinct m.account_id)', 's.cohort_accounts') }} as opp_conversion_rate
from sized s
left join opp_months m
       on m.cohort_month = s.cohort_month
      and m.first_touch_channel = s.first_touch_channel
      and m.region = s.region
group by 1,2,3,4,5
