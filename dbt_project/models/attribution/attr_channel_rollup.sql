{{ config(materialized='table') }}

-- Long-format channel credit: one row per (model, channel). This shape is what
-- Tableau needs for a small-multiples "same channel, five models" comparison,
-- and what the scorecard scores against ground truth.
-- Markov credits are appended by analysis/04_markov.py into the same table
-- shape via attribution.attr_markov_channel.

{% set models = [
    ('first_touch',    'credit_first_touch'),
    ('last_touch',     'credit_last_touch'),
    ('linear',         'credit_linear'),
    ('time_decay',     'credit_time_decay'),
    ('position_based', 'credit_position_based')
] %}

with base as (select * from {{ ref('attr_heuristic_models') }})

{% for model_name, col in models %}
select
    '{{ model_name }}'                     as model_name,
    channel,
    region,
    sum({{ col }})                         as credited_opportunities,
    sum({{ col }} * amount_arr_usd)        as credited_pipeline_usd,
    sum(case when is_won then {{ col }} else 0 end)                  as credited_wins,
    sum(case when is_won then {{ col }} * amount_arr_usd else 0 end) as credited_won_arr_usd
from base
group by 1, 2, 3
{% if not loop.last %}union all{% endif %}
{% endfor %}
