{{ config(materialized='view') }}

-- Raw leads land as all-VARCHAR. Two defects are handled here:
--   1. created_date / mql_date arrive in ISO *or* DD/MM/YYYY (12% of rows)
--   2. ~3.4% of emails are null -> they cannot be identity-resolved and are
--      flagged rather than dropped, so the funnel still counts them.

select
    lead_id,
    person_id,
    account_id,
    lower(trim(email))                          as email,
    -- strip the +1 alias the duplicate-injector adds, for identity matching
    regexp_replace(lower(trim(email)), '\+[0-9]+@', '@') as email_normalised,
    first_name,
    last_name,
    company,
    title,
    country,
    region,
    lead_source,
    nullif(self_reported_source, '')            as self_reported_source,
    {{ parse_mixed_date('created_date') }}      as created_date,
    {{ parse_mixed_date('mql_date') }}          as mql_date,
    status,
    email is null                               as is_email_missing,
    case when status in ('MQL','SQL') then true else false end as is_mql,
    case when status = 'SQL'          then true else false end as is_sql
from {{ source('raw', 'sfdc_leads') }}
