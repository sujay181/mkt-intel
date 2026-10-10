{{ config(materialized='table') }}

-- Pairwise segment overlap. Answers the question that kills campaign
-- performance: "how many accounts are getting hit by three programs at once?"
-- Jaccard index is symmetric; overlap_rate_a is directional (share of A in B).

with m as (select segment_id, account_id from {{ ref('fct_segment_membership') }}),
sizes as (select segment_id, count(distinct account_id) as n from m group by 1),
pairs as (
    select a.segment_id as segment_a, b.segment_id as segment_b,
           count(distinct a.account_id) as overlap_accounts
    from m a join m b on a.account_id = b.account_id and a.segment_id < b.segment_id
    group by 1, 2
)
select
    p.segment_a, p.segment_b,
    sa.n as size_a, sb.n as size_b,
    p.overlap_accounts,
    {{ safe_divide('p.overlap_accounts', 'sa.n') }} as overlap_rate_a,
    {{ safe_divide('p.overlap_accounts', 'sb.n') }} as overlap_rate_b,
    {{ safe_divide('p.overlap_accounts', '(sa.n + sb.n - p.overlap_accounts)') }} as jaccard_index
from pairs p
join sizes sa on sa.segment_id = p.segment_a
join sizes sb on sb.segment_id = p.segment_b
