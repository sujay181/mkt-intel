{{ config(materialized='table') }}

-- Rebuilds sessions from raw pageviews with a 30-minute inactivity timeout
-- rather than trusting the client-supplied session_id (which is device-local
-- and breaks across subdomains). This is the same logic as spark/sessionize.py;
-- analysis/06_parity_check.py asserts the two agree within 0.5%.

with events as (
    select *
    from {{ ref('stg_segment__events') }}
    where anonymous_id is not null
),

gapped as (
    select *,
        lag(event_ts) over (partition by anonymous_id order by event_ts) as prev_ts
    from events
),

flagged as (
    select *,
        case when prev_ts is null
               or date_diff('minute', prev_ts, event_ts) > {{ var('session_timeout_minutes') }}
             then 1 else 0 end as is_new_session
    from gapped
),

numbered as (
    select *,
        sum(is_new_session) over (
            partition by anonymous_id order by event_ts
            rows between unbounded preceding and current row
        ) as session_seq
    from flagged
),

agg as (
    select
        {{ dbt_utils.generate_surrogate_key(['anonymous_id', 'session_seq']) }} as session_id,
        anonymous_id,
        session_seq,
        min(event_ts)  as session_start_ts,
        max(event_ts)  as session_end_ts,
        date_diff('second', min(event_ts), max(event_ts)) as session_duration_sec,
        count(*) filter (where event_type = 'page')       as pageview_count,
        count(*) filter (where event_type = 'identify')   as identify_count,
        count(*) filter (where event_name = 'Form Submitted') as form_submit_count,
        max(user_id)                                      as resolved_user_id,
        bool_or(is_bot_user_agent)                        as has_bot_user_agent,
        -- first non-null UTM in the session wins (Segment repeats it per event)
        min(utm_source)   as utm_source,
        min(utm_medium)   as utm_medium,
        min(utm_campaign_name) as utm_campaign_name,
        min(campaign_id)  as campaign_id,
        min(channel_hint) as channel_hint,
        min(referrer)     as referrer,
        min(device_type)  as device_type
    from numbered
    group by 1, 2, 3
)

select *,
    -- two independent bot signals; either one disqualifies the session
    (has_bot_user_agent or pageview_count >= {{ var('bot_pageview_threshold') }}) as is_bot_session
from agg
