{{ config(materialized='view') }}
select
    contact_id, person_id, account_id,
    lower(trim(email)) as email,
    first_name, last_name, title,
    {{ parse_mixed_date('created_date') }} as contact_created_date
from {{ source('raw', 'sfdc_contacts') }}
