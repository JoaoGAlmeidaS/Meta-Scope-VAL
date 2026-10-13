-- Participações de cada time em eventos domésticos (VCT ou VCL, já com overrides): é daqui que
-- sai a região do time na época (D8). Internacional e evento excluído não contam.

with appearances as (

    select * from {{ ref('int_team_matches') }}

),

events as (

    select * from {{ ref('dim_event') }}

)

select
    a.team_id,
    a.event_id,
    e.region,
    min(a.match_at) as first_match_at
from appearances a
join events e using (event_id)
where not e.is_international
  and not e.is_excluded
  and e.region is not null
group by all
