-- Total credited pipeline must equal total actual pipeline for every model
-- (within rounding). Catches fan-out bugs from a bad join in the path table.
with actual as (
    select sum(amount_arr_usd) as total_arr
    from {{ ref('fct_opportunities') }}
    where opportunity_id in (select distinct opportunity_id from {{ ref('attr_heuristic_models') }})
),
credited as (
    select model_name, sum(credited_pipeline_usd) as total_arr
    from {{ ref('attr_channel_rollup') }} group by 1
)
select c.model_name, c.total_arr as credited, a.total_arr as actual
from credited c cross join actual a
where abs(c.total_arr - a.total_arr) > 1.0
