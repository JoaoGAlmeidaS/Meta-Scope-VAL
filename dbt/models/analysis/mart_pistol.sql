-- D18: pistol → vitória no mapa, na janela. Um registro por time × mapa, com os pistols vencidos
-- (rounds 1 e 13) e o Elo pré-partida do time, para controlar a força dos times: time melhor
-- vence mais pistol e mais mapa, e a pergunta é o efeito do pistol além disso.

with pistols as (

    select map_id, winner_team_id, count(*) as pistols_won
    from {{ ref('fct_round') }}
    where is_pistol and winner_team_id is not null
    group by all

),

sides as (

    select map_id, match_id, map_name, patch, match_at, team1_id as team_id, winner_team_id
    from {{ ref('fct_map') }}
    where is_in_analysis_window and not is_excluded and is_bridge_ok
    union all
    select map_id, match_id, map_name, patch, match_at, team2_id, winner_team_id
    from {{ ref('fct_map') }}
    where is_in_analysis_window and not is_excluded and is_bridge_ok

)

select
    s.map_id,
    s.match_id,
    s.team_id,
    s.map_name,
    s.patch,
    cast(s.match_at as date)                                    as match_date,
    coalesce(p.pistols_won, 0)                                  as pistols_won,
    s.winner_team_id = s.team_id                                as won_map,
    e.rating_before,
    e.opponent_rating_before,
    e.rating_before - e.opponent_rating_before                  as rating_diff,
    e.expected_result                                           as expected_match_result,
    m.best_of,
    m.tier,
    m.is_in_recent_window
from sides s
left join pistols p on p.map_id = s.map_id and p.winner_team_id = s.team_id
join {{ ref('fct_team_elo') }} e on e.match_id = s.match_id and e.team_id = s.team_id
join {{ ref('fct_match') }} m on m.match_id = s.match_id
