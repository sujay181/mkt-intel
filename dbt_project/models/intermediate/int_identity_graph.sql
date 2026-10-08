{{ config(materialized='table') }}

-- Resolves anonymous_id -> person_id -> account_id.
-- Precedence, highest first:
--   1. explicit identify() call carrying a userId
--   2. email match against a CRM lead (normalised to strip +alias)
--   3. unresolved -> stays anonymous, counted in the funnel as "unknown"
-- Deliberately does NOT use IP or company-domain reverse lookup: that inflates
-- account matching and is the most common source of silent attribution error.

with identifies as (
    select anonymous_id, user_id, trait_email, event_ts,
           row_number() over (partition by anonymous_id order by event_ts) as rn
    from {{ ref('stg_segment__events') }}
    where event_type = 'identify' and user_id is not null
),

direct_match as (
    select anonymous_id, user_id as person_id, trait_email as matched_email,
           'identify_call' as match_method, event_ts as first_identified_at
    from identifies where rn = 1
),

email_match as (
    select e.anonymous_id,
           l.person_id,
           l.email_normalised as matched_email,
           'email_backfill' as match_method,
           min(e.event_ts) as first_identified_at
    from {{ ref('stg_segment__events') }} e
    join {{ ref('stg_sfdc__leads') }} l
      on lower(trim(e.trait_email)) = l.email_normalised
    where e.trait_email is not null
      and e.anonymous_id not in (select anonymous_id from direct_match)
    group by 1, 2, 3, 4
),

unioned as (
    select * from direct_match
    union all
    select * from email_match
),

ranked as (
    select *,
        row_number() over (
            partition by anonymous_id
            order by case match_method when 'identify_call' then 1 else 2 end,
                     first_identified_at
        ) as rn
    from unioned
),

-- Lead rows are intentionally duplicated in the source (~5.5%), so these
-- lookups MUST be pre-aggregated to one row per person_id. Joining the raw
-- lead table here fans out every downstream touchpoint and silently inflates
-- attribution credit. dbt's unique_fct_touchpoints_touchpoint_id test is what
-- caught this; it stays in place to stop it regressing.
lead_account as (
    select person_id, min(account_id) as account_id
    from {{ ref('stg_sfdc__leads') }} where person_id is not null group by 1
),
contact_account as (
    select person_id, min(account_id) as account_id
    from {{ ref('stg_sfdc__contacts') }} where person_id is not null group by 1
)

select
    r.anonymous_id,
    r.person_id,
    r.matched_email,
    r.match_method,
    r.first_identified_at,
    coalesce(l.account_id, c.account_id) as account_id
from ranked r
left join lead_account    l on l.person_id = r.person_id
left join contact_account c on c.person_id = r.person_id
where r.rn = 1
