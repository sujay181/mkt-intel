{{ config(materialized='table') }}
with spend as (
    select campaign_id, sum(cost_usd) as total_cost_usd,
           min(spend_date) as first_spend_date, max(spend_date) as last_spend_date
    from {{ ref('stg_ads__spend') }} group by 1
),
touches as (
    select campaign_id, count(*) as touch_count,
           count(distinct account_id) as accounts_touched
    from {{ ref('int_touchpoints') }} where campaign_id is not null group by 1
)
select
    c.campaign_id,
    c.campaign_name_current  as campaign_name,
    c.campaign_name_original,
    c.was_renamed,
    c.channel_declared,
    c.fiscal_year, c.fiscal_quarter,
    c.campaign_start_date, c.campaign_end_date,
    coalesce(s.total_cost_usd, 0) as total_cost_usd,
    coalesce(t.touch_count, 0)    as touch_count,
    coalesce(t.accounts_touched, 0) as accounts_touched,
    {{ safe_divide('s.total_cost_usd', 't.accounts_touched') }} as cost_per_account_touched
from {{ ref('stg_sfdc__campaigns') }} c
left join spend s   on s.campaign_id = c.campaign_id
left join touches t on t.campaign_id = c.campaign_id
