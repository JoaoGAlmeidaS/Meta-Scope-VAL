-- D19: força relativa entre regiões, na janela. Um registro por partida internacional entre times
-- de regiões diferentes, com a região de cada time na época (int_team_match_regions) e o
-- resultado contra o esperado pelo Elo pré-partida. Região nula (time sem evento doméstico) fica
-- fora.

select
    m.match_id,
    m.event_id,
    m.match_date,
    m.tier,
    m.is_in_recent_window,
    m.team1_id,
    m.team1_region,
    m.team2_id,
    m.team2_region,
    case when m.is_draw then 0.5 when m.winner_team_id = m.team1_id then 1.0 else 0.0 end
                                                                as team1_result,
    e.expected_result                                           as team1_expected_result,
    e.rating_before - e.opponent_rating_before                  as team1_rating_diff
from {{ ref('fct_match') }} m
join {{ ref('fct_team_elo') }} e on e.match_id = m.match_id and e.team_id = m.team1_id
where m.is_in_analysis_window
  and not m.is_excluded
  and m.is_international
  and m.team1_region is not null
  and m.team2_region is not null
  and m.team1_region <> m.team2_region
