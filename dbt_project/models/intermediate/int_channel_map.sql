{{ config(materialized='table') }}

-- The single place where (utm_source, utm_medium) becomes a channel.
-- Every dashboard reads channel from here. If a marketer launches a campaign
-- with a new UTM pair, it lands in 'unmapped' and the
-- assert_no_unmapped_utm_source test fails the build the next morning —
-- which is the point.

with pairs as (
    select distinct utm_source, utm_medium
    from {{ ref('stg_segment__events') }}
    where utm_source is not null
),

mapped as (
    select
        p.utm_source,
        p.utm_medium,
        coalesce(m.channel, 'unmapped') as channel,
        coalesce(m.channel_group, 'Unknown') as channel_group,
        coalesce(m.is_paid, false) as is_paid
    from pairs p
    left join {{ ref('channel_mapping') }} m
      on m.raw_utm_source = p.utm_source
     and m.raw_utm_medium = p.utm_medium
)

select * from mapped
