{{ config(materialized='view') }}

-- Join on spend_date, not booked_date. booked_date lags by 3 days because
-- ad platforms finalise cost after the fact; using it silently shifts every
-- cost-per-lead metric three days to the right.

select
    cast(spend_date as date)   as spend_date,
    cast(booked_date as date)  as booked_date,
    channel,
    campaign_id,
    campaign_name,
    region,
    cast(cost_usd as double)   as cost_usd,
    cast(impressions as integer) as impressions,
    cast(clicks as integer)      as clicks
from {{ source('raw', 'ads_spend') }}
