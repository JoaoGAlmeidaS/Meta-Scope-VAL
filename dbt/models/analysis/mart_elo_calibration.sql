-- D21: calibração da previsão pelo Elo, na janela. Um registro por partida, do ponto de vista do
-- time 1: a probabilidade pré-partida e o resultado (empate 0,5). Log loss, Brier e curva de
-- calibração saem em Python (notebook 07 e o site).

select
    m.match_id,
    m.event_id,
    m.match_date,
    m.tier,
    m.is_in_recent_window,
    m.is_international,
    e.expected_result                                           as team1_win_probability,
    e.result                                                    as team1_result,
    abs(e.rating_before - e.opponent_rating_before)             as rating_gap
from {{ ref('fct_match') }} m
join {{ ref('fct_team_elo') }} e on e.match_id = m.match_id and e.team_id = m.team1_id
where m.is_in_analysis_window
  and not m.is_excluded
