{{ config(materialized='view') }}
select
    campaign_member_id,
    campaign_id,
    person_id,
    status,
    cast(created_date as date) as member_created_date,
    status = 'Responded'       as did_respond
from {{ source('raw', 'sfdc_campaign_members') }}
