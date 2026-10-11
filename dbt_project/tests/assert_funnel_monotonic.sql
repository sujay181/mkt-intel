-- SQLs can never exceed MQLs, and opportunities can never exceed SQLs,
-- at the channel-month grain. A violation means the stage-date logic drifted.
with m as (
    select month_start_date, channel,
           sum(mqls) as mqls, sum(sqls) as sqls, sum(opps_created) as opps
    from {{ ref('mart_funnel_daily') }} group by 1, 2
)
select * from m where sqls > mqls
