-- Partidas que entram no Elo (D15): competitivas (sem evento excluído e sem showmatch, que o
-- `is_excluded` do fct_match já cobre), com o resultado da série do ponto de vista do time 1.
-- Empate (formato "2 maps", pegadinha 38) vale 0,5. Todo o histórico coletado entra: o que está
-- antes da janela é o aquecimento do rating.

select
    match_id,
    match_at,
    season,
    event_id,
    tier_level,
    is_international,
    team1_id,
    team2_id,
    case
        when is_draw then 0.5
        when winner_team_id = team1_id then 1.0
        else 0.0
    end                                                 as team1_result
from {{ ref('fct_match') }}
where not is_excluded
  and (winner_team_id is not null or is_draw)
