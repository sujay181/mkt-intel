{{ config(materialized='view') }}

-- One campaign was renamed mid-quarter while keeping its campaign_id.
-- Both names are surfaced so downstream joins on NAME (which marketers do)
-- still resolve to a single campaign_id.

select
    campaign_id,
    campaign_name                      as campaign_name_original,
    coalesce(renamed_to, campaign_name) as campaign_name_current,
    channel                            as channel_declared,
    fiscal_year,
    fiscal_quarter,
    cast(start_date as date)           as campaign_start_date,
    cast(end_date as date)             as campaign_end_date,
    lower(is_renamed) in ('true','1')  as was_renamed,
    try_cast(rename_effective as date) as rename_effective_date
from {{ source('raw', 'sfdc_campaigns') }}
