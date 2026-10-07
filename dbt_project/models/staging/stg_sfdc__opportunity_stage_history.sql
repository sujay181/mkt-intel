{{ config(materialized='view') }}
select
    stage_history_id,
    opportunity_id,
    stage,
    cast(entered_at as date) as entered_at,
    lead(cast(entered_at as date)) over (
        partition by opportunity_id order by cast(entered_at as date)
    ) as exited_at
from {{ source('raw', 'sfdc_opportunity_stage_history') }}
