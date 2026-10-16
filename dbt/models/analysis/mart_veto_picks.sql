-- D19: vantagem de quem escolhe o mapa, na janela. Um registro por mapa escolhido no veto e jogado,
-- com o resultado de quem escolheu e a expectativa pelo Elo pré-partida: o time melhor também
-- tende a vencer o mapa que escolheu, e a pergunta é o ganho além do esperado.

select
    v.match_id,
    v.event_id,
    v.map_id,
    v.map_name,
    v.patch,
    cast(v.match_at as date)                                    as match_date,
    v.team_id                                                   as picker_team_id,
    mp.winner_team_id = v.team_id                               as picker_won,
    e.expected_result                                           as picker_expected_match_result,
    e.rating_before - e.opponent_rating_before                  as picker_rating_diff,
    m.best_of,
    m.tier,
    m.is_in_recent_window
from {{ ref('fct_veto') }} v
join {{ ref('fct_map') }} mp using (map_id)
join {{ ref('fct_team_elo') }} e on e.match_id = v.match_id and e.team_id = v.team_id
join {{ ref('fct_match') }} m on m.match_id = v.match_id
where v.is_in_analysis_window
  and not v.is_excluded
  and v.veto_action = 'pick'
  and v.was_played
  and v.team_id is not null
  and mp.winner_team_id is not null
