{{ config(materialized='view') }}

select
    account_id,
    account_name,
    industry,
    employee_band,
    region,
    country,
    cast(icp_score_raw as double)    as icp_score_raw,
    cast(deal_size_mult as double)   as deal_size_mult,
    {{ parse_mixed_date('created_date') }} as account_created_date,
    -- banded ICP so segments are stable when the raw score drifts
    case
        when cast(icp_score_raw as double) >= 1.45 then 'Tier 1'
        when cast(icp_score_raw as double) >= 1.05 then 'Tier 2'
        when cast(icp_score_raw as double) >= 0.70 then 'Tier 3'
        else 'Tier 4'
    end as icp_tier
from {{ source('raw', 'sfdc_accounts') }}
