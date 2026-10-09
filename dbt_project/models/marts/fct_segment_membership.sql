{{ config(materialized='table') }}

-- Audience activation layer. Every segment is defined ONCE here, versioned in
-- seeds/segment_definitions.csv, and exported to Marketo/Salesforce/LinkedIn by
-- analysis/07_export_segments.py. Marketers never rebuild these rules by hand
-- in the tool UI — that is how three teams end up with three different
-- definitions of "engaged".
--
-- Adding a segment = add a CTE + a row in the seed. Nothing else changes.

{% set as_of = "cast('" ~ var('end_date') ~ "' as date)" %}

with acct as (select * from {{ ref('dim_account') }}),
touch as (select * from {{ ref('fct_touchpoints') }} where is_attributable),
opps  as (select * from {{ ref('fct_opportunities') }}),

-- seg_001 --------------------------------------------------------------
seg_icp_tier1_enterprise as (
    select 'seg_001' as segment_id, account_id
    from acct
    where icp_tier = 'Tier 1' and employee_band in ('1001-5000', '5000+')
),

-- seg_002 --------------------------------------------------------------
recent_touch_counts as (
    select account_id, count(*) as touches_90d
    from touch where touch_date >= {{ as_of }} - interval 90 day
    group by 1
),
seg_engaged_no_opp_90d as (
    select 'seg_002' as segment_id, r.account_id
    from recent_touch_counts r
    where r.touches_90d >= 3
      and not exists (select 1 from opps o
                      where o.account_id = r.account_id and not o.is_closed)
),

-- seg_003 --------------------------------------------------------------
seg_webinar_unconverted as (
    select distinct 'seg_003' as segment_id, t.account_id
    from touch t
    join acct a on a.account_id = t.account_id
    where t.channel = 'webinar' and not a.has_opportunity
),

-- seg_004 --------------------------------------------------------------
seg_apac_multicloud_intent as (
    select 'seg_004' as segment_id, t.account_id
    from touch t join acct a on a.account_id = t.account_id
    where a.region = 'APAC' and t.touch_date >= {{ as_of }} - interval 60 day
    group by 1, 2 having count(*) >= 2
),

-- seg_005 --------------------------------------------------------------
seg_closed_lost_winback as (
    select distinct 'seg_005' as segment_id, o.account_id
    from opps o
    where o.is_closed and not o.is_won
      and o.close_date between {{ as_of }} - interval 365 day
                           and {{ as_of }} - interval 180 day
      and exists (select 1 from touch t where t.account_id = o.account_id
                  and t.touch_date >= {{ as_of }} - interval 90 day)
),

-- seg_006 --------------------------------------------------------------
seg_partner_sourced as (
    select 'seg_006' as segment_id, account_id
    from acct where first_touch_channel = 'partner_referral' and not has_opportunity
),

unioned as (
    select * from seg_icp_tier1_enterprise
    union all select * from seg_engaged_no_opp_90d
    union all select * from seg_webinar_unconverted
    union all select * from seg_apac_multicloud_intent
    union all select * from seg_closed_lost_winback
    union all select * from seg_partner_sourced
)

select
    u.segment_id,
    d.segment_name,
    d.segment_type,
    d.owner,
    d.activation_target,
    d.version,
    u.account_id,
    a.account_name, a.region, a.industry, a.icp_tier, a.employee_band,
    a.lifetime_touches, a.has_opportunity, a.won_arr_usd,
    {{ as_of }} as membership_as_of_date
from unioned u
join {{ ref('segment_definitions') }} d on d.segment_id = u.segment_id
join acct a on a.account_id = u.account_id
