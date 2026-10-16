-- D20: composições na janela, com a força do time. Um registro por time × mapa com os 5 agentes,
-- o patch, o resultado e o Elo pré-partida do time: o shrinkage (Python) compara o resultado com o
-- esperado, porque time forte joga comp "forte" e vence de qualquer jeito.

select
    c.map_id,
    c.match_id,
    c.team_id,
    c.map_name,
    c.patch,
    cast(c.match_at as date)                                    as match_date,
    c.composition_key,
    c.agents,
    c.won_map,
    e.expected_result                                           as expected_match_result,
    e.rating_before - e.opponent_rating_before                  as rating_diff,
    m.best_of,
    m.tier,
    m.is_in_recent_window
from {{ ref('fct_composition') }} c
join {{ ref('fct_team_elo') }} e on e.match_id = c.match_id and e.team_id = c.team_id
join {{ ref('fct_match') }} m on m.match_id = c.match_id
where c.is_in_analysis_window
  and not c.is_excluded
  and c.players = 5
