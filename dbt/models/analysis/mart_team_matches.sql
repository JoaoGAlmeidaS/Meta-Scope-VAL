-- D26: partidas de cada time na janela, para o perfil: adversário, resultado, Elo antes e depois.

select
    e.team_id,
    e.match_id,
    m.match_date,
    m.event_id,
    ev.event_name,
    m.series_name,
    e.opponent_id,
    case when m.team1_id = e.team_id then m.team2_name else m.team1_name end
                                                                as opponent_name,
    case when m.team1_id = e.team_id then m.team1_score else m.team2_score end
                                                                as maps_won,
    case when m.team1_id = e.team_id then m.team2_score else m.team1_score end
                                                                as maps_lost,
    e.result,
    e.expected_result,
    e.rating_before,
    e.rating_after
from {{ ref('fct_team_elo') }} e
join {{ ref('fct_match') }} m using (match_id)
join {{ ref('dim_event') }} ev on ev.event_id = m.event_id
where m.is_in_analysis_window
  and not m.is_excluded
