-- Região de cada time em cada partida (regra do D8, docs/fontes.md):
--   a região do evento doméstico mais recente que o time começou a disputar até a partida;
--   sem nenhum antes, a do primeiro depois; sem nenhum, nula (fica fora da análise regional).
-- ASOF JOIN do DuckDB: o "mais recente até" sem janela nem subconsulta correlacionada.

with appearances as (

    select match_id, team_id, match_at from {{ ref('int_team_matches') }}

),

domestic as (

    select * from {{ ref('int_team_domestic_events') }}

),

before_match as (

    select a.match_id, a.team_id, a.match_at, d.region, d.event_id
    from appearances a
    asof left join domestic d
        on a.team_id = d.team_id
       and a.match_at >= d.first_match_at

),

after_match as (

    select a.match_id, a.team_id, d.region, d.event_id
    from appearances a
    asof left join domestic d
        on a.team_id = d.team_id
       and a.match_at <= d.first_match_at

)

select
    b.match_id,
    b.team_id,
    coalesce(b.region, f.region)            as team_region,
    coalesce(b.event_id, f.event_id)        as region_source_event_id,
    b.region is null and f.region is not null
                                            as is_region_from_later_event
from before_match b
join after_match f using (match_id, team_id)
