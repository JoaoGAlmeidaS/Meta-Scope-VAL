-- D13: rounds vencidos por cada time somam o placar do mapa (overtime incluído).
-- Só mapas com a ponte tag → id fechada: sem ela o vencedor do round é nulo por construção.

with wins as (

    select map_id, winner_team_id, count(*) as rounds_won
    from {{ ref('fct_round') }}
    group by all

)

select
    m.map_id,
    m.team1_score,
    coalesce(w1.rounds_won, 0) as team1_rounds_won,
    m.team2_score,
    coalesce(w2.rounds_won, 0) as team2_rounds_won
from {{ ref('fct_map') }} m
left join wins w1 on w1.map_id = m.map_id and w1.winner_team_id = m.team1_id
left join wins w2 on w2.map_id = m.map_id and w2.winner_team_id = m.team2_id
where m.is_bridge_ok
  and (m.team1_score <> coalesce(w1.rounds_won, 0) or m.team2_score <> coalesce(w2.rounds_won, 0))
