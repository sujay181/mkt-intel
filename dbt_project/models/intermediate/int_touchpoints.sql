{{ config(materialized='table') }}

-- THE SPINE. One row per marketing touch that can be attributed to an account.
-- Every attribution model reads this and nothing else.
--
-- Inclusion rules (documented in governance/metrics.yml as `touchpoint`):
--   - session is not a bot session
--   - session resolves to an account via int_identity_graph
--   - session carries a mappable channel
--   - session_start_ts is within touch_lookback_days of the opp create date
--     (applied downstream, not here, so the raw spine stays reusable)

with sessions as (
    select * from {{ ref('int_sessions') }} where not is_bot_session
),

resolved as (
    select
        s.session_id,
        s.anonymous_id,
        s.session_start_ts,
        s.session_end_ts,
        s.pageview_count,
        s.form_submit_count,
        s.utm_source,
        s.utm_medium,
        s.utm_campaign_name,
        s.campaign_id,
        s.device_type,
        s.referrer,
        coalesce(s.resolved_user_id, g.person_id) as person_id,
        g.account_id,
        g.match_method
    from sessions s
    left join {{ ref('int_identity_graph') }} g on g.anonymous_id = s.anonymous_id
),

with_channel as (
    select
        r.*,
        coalesce(cm.channel, 'unmapped')          as channel,
        coalesce(cm.channel_group, 'Unknown')     as channel_group,
        coalesce(cm.is_paid, false)               as is_paid,
        c.campaign_name_current,
        c.fiscal_year,
        c.fiscal_quarter
    from resolved r
    left join {{ ref('int_channel_map') }} cm
           on cm.utm_source = r.utm_source and cm.utm_medium = r.utm_medium
    left join {{ ref('stg_sfdc__campaigns') }} c on c.campaign_id = r.campaign_id
)

select
    {{ dbt_utils.generate_surrogate_key(['session_id']) }} as touchpoint_id,
    session_id,
    anonymous_id,
    person_id,
    account_id,
    session_start_ts                      as touch_ts,
    cast(session_start_ts as date)        as touch_date,
    channel,
    channel_group,
    is_paid,
    campaign_id,
    campaign_name_current,
    fiscal_year,
    fiscal_quarter,
    utm_source,
    utm_medium,
    device_type,
    pageview_count,
    form_submit_count,
    match_method,
    account_id is not null                as is_attributable,
    row_number() over (partition by account_id order by session_start_ts) as touch_seq_in_account
from with_channel
