-- D13: mapas vencidos por cada time somam o placar da série. Mapa sem dado nenhum (W.O. de um
-- mapa no meio da série, "TBD" com placar nulo) é descartado pelo contrato e contado em
-- `maps_without_data` (pegadinha 33): a diferença entre placar e mapas vencidos tem que ser
-- exatamente essa, e nenhum time pode ter mais mapas vencidos que o placar. Outra divergência vai
-- para o seed validation_exceptions com a justificativa.

with maps_won as (

    select match_id, winner_team_id, count(*) as maps_won
    from {{ ref('fct_map') }}
    where winner_team_id is not null
    group by all

)

select m.match_id, m.team1_score, w1.maps_won as team1_maps, m.team2_score, w2.maps_won as team2_maps
from {{ ref('fct_match') }} m
left join maps_won w1 on w1.match_id = m.match_id and w1.winner_team_id = m.team1_id
left join maps_won w2 on w2.match_id = m.match_id and w2.winner_team_id = m.team2_id
left join {{ ref('validation_exceptions') }} x
    on x.check_name = 'series_score' and x.match_id = m.match_id
where x.check_name is null
  and (
      coalesce(w1.maps_won, 0) > m.team1_score
      or coalesce(w2.maps_won, 0) > m.team2_score
      or (m.team1_score - coalesce(w1.maps_won, 0)) + (m.team2_score - coalesce(w2.maps_won, 0))
         <> m.maps_without_data
  )
