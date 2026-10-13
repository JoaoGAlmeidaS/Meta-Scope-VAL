-- D13: mapa escolhido no veto foi jogado, salvo quando a série acabou antes dele. Sobram sem jogo
-- o decider da BO3 2–0 (pegadinha 14) e o último pick da BO5 3–0: nos dois casos o lake tem todos
-- os mapas da série (mapas = soma do placar). Mapa de W.O. sem dado (`maps_without_data`,
-- pegadinha 33) conta como mapa da série. Pick sem mapa numa série incompleta é coleta incompleta:
-- vai para o seed validation_exceptions com a justificativa, ou é defeito.

select v.match_id, v.event_id, v.map_name, v.veto_action
from {{ ref('fct_veto') }} v
join {{ ref('fct_match') }} m using (match_id)
left join {{ ref('validation_exceptions') }} x
    on x.check_name = 'unplayed_pick'
   and x.match_id = v.match_id
   and x.map_name = v.map_name
where v.veto_action = 'pick'
  and not v.was_played
  and m.maps_played + m.maps_without_data < m.team1_score + m.team2_score
  and x.check_name is null
