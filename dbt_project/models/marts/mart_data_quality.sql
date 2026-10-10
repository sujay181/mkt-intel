{{ config(materialized='table') }}

-- Powers the "Can I trust this dashboard?" panel in Tableau.
-- One row per metric per day. Every number here is a defect the pipeline
-- detected; if a value spikes, the dashboard shows a warning band instead of
-- silently reporting a dip in performance.

with days as (select date_day from {{ ref('dim_date') }}
              where date_day <= cast('{{ var("end_date") }}' as date)),

unmapped as (
    select touch_date as date_day, count(*) as v from {{ ref('int_touchpoints') }}
    where channel = 'unmapped' group by 1),
bots as (
    select cast(session_start_ts as date) as date_day, count(*) as v
    from {{ ref('int_sessions') }} where is_bot_session group by 1),
unresolved as (
    select cast(session_start_ts as date) as date_day, count(*) as v
    from {{ ref('int_sessions') }} s
    where not exists (select 1 from {{ ref('int_identity_graph') }} g
                      where g.anonymous_id = s.anonymous_id) group by 1),
null_email as (
    select created_date as date_day, count(*) as v
    from {{ ref('stg_sfdc__leads') }} where is_email_missing group by 1),
dupes as (
    select created_date as date_day, count(*) as v
    from (select created_date, email_normalised, count(*) c
          from {{ ref('stg_sfdc__leads') }} where email_normalised is not null
          group by 1,2 having count(*) > 1) group by 1),
total_sessions as (
    select cast(session_start_ts as date) as date_day, count(*) as v
    from {{ ref('int_sessions') }} group by 1)

select d.date_day, 'unmapped_touchpoints' as metric, coalesce(u.v,0) as value,
       coalesce(t.v,0) as denominator from days d
  left join unmapped u on u.date_day=d.date_day left join total_sessions t on t.date_day=d.date_day
union all
select d.date_day, 'bot_sessions', coalesce(b.v,0), coalesce(t.v,0) from days d
  left join bots b on b.date_day=d.date_day left join total_sessions t on t.date_day=d.date_day
union all
select d.date_day, 'unresolved_sessions', coalesce(r.v,0), coalesce(t.v,0) from days d
  left join unresolved r on r.date_day=d.date_day left join total_sessions t on t.date_day=d.date_day
union all
select d.date_day, 'leads_missing_email', coalesce(n.v,0), null from days d
  left join null_email n on n.date_day=d.date_day
union all
select d.date_day, 'duplicate_lead_emails', coalesce(x.v,0), null from days d
  left join dupes x on x.date_day=d.date_day
