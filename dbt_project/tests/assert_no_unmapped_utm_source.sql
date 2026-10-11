-- Fails the build when a new UTM pair appears that channel_mapping.csv does
-- not cover. This is the guard rail that stops a new campaign quietly
-- disappearing into an 'unmapped' bucket for a whole quarter.
select utm_source, utm_medium, count(*) as touchpoints
from {{ ref('int_touchpoints') }}
where channel = 'unmapped'
group by 1, 2
having count(*) > 5
