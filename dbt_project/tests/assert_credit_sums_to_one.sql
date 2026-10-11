-- Every attribution model must distribute exactly 100% of each opportunity.
-- A failure here means a credit rule leaks or double-counts pipeline.
with sums as (
    select opportunity_id,
        sum(credit_first_touch)    as s_ft,
        sum(credit_last_touch)     as s_lt,
        sum(credit_linear)         as s_lin,
        sum(credit_time_decay)     as s_td,
        sum(credit_position_based) as s_pos
    from {{ ref('attr_heuristic_models') }}
    group by 1
)
select * from sums
where abs(s_ft - 1) > 0.0001 or abs(s_lt - 1) > 0.0001
   or abs(s_lin - 1) > 0.0001 or abs(s_td - 1) > 0.0001
   or abs(s_pos - 1) > 0.0001
