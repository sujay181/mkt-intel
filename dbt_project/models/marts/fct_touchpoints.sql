{{ config(materialized='table') }}
select
    t.touchpoint_id, t.session_id, t.person_id, t.account_id,
    t.touch_ts, t.touch_date, t.channel, t.channel_group, t.is_paid,
    t.campaign_id, t.campaign_name_current as campaign_name,
    t.utm_source, t.utm_medium, t.device_type,
    t.pageview_count, t.form_submit_count, t.match_method,
    t.touch_seq_in_account, t.is_attributable,
    a.region, a.industry, a.icp_tier, a.employee_band
from {{ ref('int_touchpoints') }} t
left join {{ ref('dim_account') }} a on a.account_id = t.account_id
