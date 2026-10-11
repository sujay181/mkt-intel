-- Attribution must only consider pre-opportunity activity.
select opportunity_id, touchpoint_id, touch_date, opportunity_created_date
from {{ ref('int_opportunity_touch_paths') }}
where touch_date > opportunity_created_date
