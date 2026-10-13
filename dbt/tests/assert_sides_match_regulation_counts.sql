-- D13: o lado reconstruído bate com `roundsCt`/`roundsT` da API. Rounds vencidos na defesa e no
-- ataque, até o round 24, somam os contadores do mapa (que não contam o overtime: pegadinha 1).

with won as (

    select
        map_id,
        winner_team_id                                          as team_id,
        count(*) filter (where winner_side = 'defense')         as def_rounds,
        count(*) filter (where winner_side = 'attack')          as atk_rounds
    from {{ ref('fct_round') }}
    where round_number <= 24
    group by all

)

select
    m.map_id,
    m.team1_def_rounds, w1.def_rounds as team1_def_reconstructed,
    m.team1_atk_rounds, w1.atk_rounds as team1_atk_reconstructed,
    m.team2_def_rounds, w2.def_rounds as team2_def_reconstructed,
    m.team2_atk_rounds, w2.atk_rounds as team2_atk_reconstructed
from {{ ref('fct_map') }} m
left join won w1 on w1.map_id = m.map_id and w1.team_id = m.team1_id
left join won w2 on w2.map_id = m.map_id and w2.team_id = m.team2_id
where m.is_bridge_ok
  and m.has_round_sides
  and (
      m.team1_def_rounds <> coalesce(w1.def_rounds, 0)
      or m.team1_atk_rounds <> coalesce(w1.atk_rounds, 0)
      or m.team2_def_rounds <> coalesce(w2.def_rounds, 0)
      or m.team2_atk_rounds <> coalesce(w2.atk_rounds, 0)
  )
