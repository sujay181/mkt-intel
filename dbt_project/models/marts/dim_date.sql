{{ config(materialized='table') }}
with days as (
    select unnest(generate_series(
        cast('{{ var("start_date") }}' as date),
        cast('{{ var("end_date") }}' as date) + interval 1 year,
        interval 1 day)) as d
)
select
    cast(d as date) as date_day,
    extract(year from d)    as calendar_year,
    extract(month from d)   as calendar_month,
    extract(quarter from d) as calendar_quarter,
    extract(dow from d)     as day_of_week,
    extract(dow from d) in (0, 6) as is_weekend,
    date_trunc('week', d)::date  as week_start_date,
    date_trunc('month', d)::date as month_start_date,
    -- Megaport FY starts 1 July
    case when extract(month from d) >= 7
         then extract(year from d) + 1 else extract(year from d) end as fiscal_year,
    'Q' || cast(((extract(month from d)::int - 7) % 12) / 3 + 1 as int) as fiscal_quarter
from days
