{{ config(materialized='view') }}

-- Flattens Segment's nested context/properties into typed columns and
-- deduplicates on message_id (Segment guarantees at-least-once delivery,
-- so duplicate messageIds are expected in any real pipeline).

with src as (
    select
        message_id,
        event_type,
        event_name,
        anonymous_id,
        user_id,
        event_ts,
        json_extract_string(context_json, '$.campaign.source')  as utm_source_raw,
        json_extract_string(context_json, '$.campaign.medium')  as utm_medium_raw,
        json_extract_string(context_json, '$.campaign.name')    as utm_campaign_raw,
        json_extract_string(context_json, '$.campaign.content') as utm_content,
        json_extract_string(context_json, '$.page.path')        as page_path,
        json_extract_string(context_json, '$.page.referrer')    as referrer,
        json_extract_string(context_json, '$.device.type')      as device_type,
        json_extract_string(context_json, '$.userAgent')        as user_agent,
        json_extract_string(context_json, '$.locale')           as locale,
        json_extract_string(properties_json, '$.session_id')    as raw_session_id,
        json_extract_string(properties_json, '$.campaign_id')   as campaign_id,
        json_extract_string(properties_json, '$.channel_hint')  as channel_hint,
        json_extract_string(properties_json, '$.form_id')       as form_id,
        json_extract_string(traits_json, '$.email')             as trait_email,
        json_extract_string(traits_json, '$.company')           as trait_company,
        json_extract_string(traits_json, '$.title')             as trait_title,
        json_extract_string(traits_json, '$.country')           as trait_country,
        row_number() over (partition by message_id order by event_ts) as _dedupe_rn
    from {{ source('raw', 'segment_events') }}
    where event_ts between cast('{{ var("start_date") }}' as timestamp)
                       and cast('{{ var("end_date") }}' as timestamp) + interval 1 year
)

select
    message_id,
    event_type,
    event_name,
    anonymous_id,
    user_id,
    event_ts,
    cast(event_ts as date) as event_date,
    {{ clean_utm('utm_source_raw') }} as utm_source,
    {{ clean_utm('utm_medium_raw') }} as utm_medium,
    trim(utm_campaign_raw)            as utm_campaign_name,
    utm_content,
    page_path,
    nullif(referrer, '')              as referrer,
    device_type,
    user_agent,
    locale,
    raw_session_id,
    campaign_id,
    channel_hint,
    form_id,
    lower(trim(trait_email))          as trait_email,
    trait_company,
    trait_title,
    trait_country,
    -- bot heuristic, tuned against the generator's injected bot sessions
    case when user_agent ilike '%crawler%' or user_agent ilike '%bot%'
         then true else false end     as is_bot_user_agent
from src
where _dedupe_rn = 1
