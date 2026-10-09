{{ config(materialized='table') }}
select
    spend_date, channel, campaign_id, region,
    sum(cost_usd)     as cost_usd,
    sum(impressions)  as impressions,
    sum(clicks)       as clicks,
    {{ safe_divide('sum(cost_usd)', 'sum(clicks)') }} as cost_per_click
from {{ ref('stg_ads__spend') }}
group by 1,2,3,4
