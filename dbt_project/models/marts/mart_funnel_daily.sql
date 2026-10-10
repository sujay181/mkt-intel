{{ config(materialized='table') }}

-- Daily funnel by channel and region. Stage counts are attributed to the
-- FIRST touch of the account, so a row here answers "what did this channel
-- put into the top of the funnel on this day", not "who closed it".
-- For closing credit use mart_attribution_comparison.

with touch_day as (
    select touch_date as date_day, channel, region,
           count(distinct account_id) as accounts_touched,
           count(distinct session_id) as sessions,
           count(distinct case when form_submit_count > 0 then person_id end) as form_submitters
    from {{ ref('fct_touchpoints') }} where is_attributable group by 1,2,3
),
lead_day as (
    select l.created_date as date_day,
           coalesce(ft.first_touch_channel, 'unmapped') as channel,
           l.region,
           count(*) as leads_created,
           count(*) filter (where l.is_mql) as mqls,
           count(*) filter (where l.is_sql) as sqls
    from {{ ref('stg_sfdc__leads') }} l
    left join {{ ref('dim_account') }} ft on ft.account_id = l.account_id
    group by 1,2,3
),
opp_day as (
    select opportunity_created_date as date_day,
           coalesce(first_touch_channel, 'unmapped') as channel,
           region,
           count(*) as opps_created,
           sum(amount_arr_usd) as opp_pipeline_usd,
           count(*) filter (where is_won) as opps_won,
           sum(case when is_won then amount_arr_usd else 0 end) as won_arr_usd
    from {{ ref('fct_opportunities') }} group by 1,2,3
),
spend_day as (
    select spend_date as date_day, channel, region, sum(cost_usd) as cost_usd
    from {{ ref('fct_spend_daily') }} group by 1,2,3
),
spine as (
    select date_day, channel, region from touch_day
    union select date_day, channel, region from lead_day
    union select date_day, channel, region from opp_day
    union select date_day, channel, region from spend_day
)
select
    s.date_day, d.fiscal_year, d.fiscal_quarter, d.month_start_date,
    s.channel, s.region,
    coalesce(t.sessions, 0)          as sessions,
    coalesce(t.accounts_touched, 0)  as accounts_touched,
    coalesce(t.form_submitters, 0)   as form_submitters,
    coalesce(l.leads_created, 0)     as leads_created,
    coalesce(l.mqls, 0)              as mqls,
    coalesce(l.sqls, 0)              as sqls,
    coalesce(o.opps_created, 0)      as opps_created,
    coalesce(o.opp_pipeline_usd, 0)  as opp_pipeline_usd,
    coalesce(o.opps_won, 0)          as opps_won,
    coalesce(o.won_arr_usd, 0)       as won_arr_usd,
    coalesce(sp.cost_usd, 0)         as cost_usd,
    {{ safe_divide('sp.cost_usd', 'l.mqls') }}          as cost_per_mql,
    {{ safe_divide('sp.cost_usd', 'o.opps_created') }}  as cost_per_opportunity,
    {{ safe_divide('o.opp_pipeline_usd', 'sp.cost_usd') }} as pipeline_roas
from spine s
left join {{ ref('dim_date') }} d on d.date_day = s.date_day
left join touch_day t on t.date_day = s.date_day and t.channel = s.channel and t.region = s.region
left join lead_day  l on l.date_day = s.date_day and l.channel = s.channel and l.region = s.region
left join opp_day   o on o.date_day = s.date_day and o.channel = s.channel and o.region = s.region
left join spend_day sp on sp.date_day = s.date_day and sp.channel = s.channel and sp.region = s.region
