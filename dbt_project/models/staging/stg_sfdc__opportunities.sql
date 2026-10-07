{{ config(materialized='view') }}

select
    opportunity_id,
    account_id,
    primary_contact_id,
    opportunity_name,
    {{ parse_mixed_date('created_date') }} as opportunity_created_date,
    {{ parse_mixed_date('close_date') }}   as close_date,
    stage,
    lower(is_closed) in ('true','1')       as is_closed,
    lower(is_won)    in ('true','1')       as is_won,
    cast(amount_arr_usd as double)         as amount_arr_usd,
    region,
    industry,
    cast(sales_cycle_days as integer)      as sales_cycle_days
from {{ source('raw', 'sfdc_opportunities') }}
