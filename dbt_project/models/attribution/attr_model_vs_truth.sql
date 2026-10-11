{{ config(materialized='table') }}

-- THE HEADLINE TABLE.
-- Puts every heuristic model's channel credit next to the simulation's actual
-- latent contribution, and computes the error. This is the only table in the
-- project that touches source('truth'), and it exists purely for evaluation.
--
-- Read it as: "last_touch says direct drove X% of pipeline; the truth is Y%;
-- the model is over-crediting by Z percentage points."

with truth as (
    select
        channel,
        sum(true_credit_arr_usd)      as true_arr_usd,
        sum(true_credit_fraction)     as true_credit_units
    from {{ source('truth', 'account_touch_credit') }}
    group by 1
),
truth_share as (
    select channel, true_arr_usd, true_credit_units,
           true_arr_usd / sum(true_arr_usd) over () as true_share_of_arr
    from truth
),
modelled as (
    select model_name, channel,
           sum(credited_pipeline_usd) as modelled_arr_usd
    from {{ ref('attr_channel_rollup') }}
    group by 1, 2
),
modelled_share as (
    select *,
        modelled_arr_usd / sum(modelled_arr_usd) over (partition by model_name)
            as modelled_share_of_arr
    from modelled
)
select
    m.model_name,
    m.channel,
    t.true_share_of_arr,
    m.modelled_share_of_arr,
    m.modelled_share_of_arr - t.true_share_of_arr           as share_error,
    abs(m.modelled_share_of_arr - t.true_share_of_arr)      as abs_share_error,
    {{ safe_divide('m.modelled_share_of_arr - t.true_share_of_arr', 't.true_share_of_arr') }}
        as relative_error,
    case
        when m.modelled_share_of_arr > t.true_share_of_arr * 1.15 then 'over-credited'
        when m.modelled_share_of_arr < t.true_share_of_arr * 0.85 then 'under-credited'
        else 'within 15%'
    end as verdict
from modelled_share m
join truth_share t on t.channel = m.channel
