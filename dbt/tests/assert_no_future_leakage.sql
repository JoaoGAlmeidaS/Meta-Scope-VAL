-- D15/D16: teste anti-vazamento do Elo. O rating usado para prever ou avaliar uma partida é o de
-- antes dela, e só partidas anteriores o formaram. Para cada time, o `rating_before` de uma partida
-- tem que ser exatamente o `rating_after` da partida anterior do mesmo time (salvo a regressão
-- da virada de temporada e a reancoragem na promoção VCL → VCT, `is_promotion`, que só puxam para
-- o rating inicial a partir do passado), e a ordem é estritamente temporal.
-- Qualquer linha aqui é vazamento: o rating viu algo que não devia.

with ordered as (

    select
        team_id,
        match_id,
        match_at,
        season,
        is_promotion,
        rating_before,
        lag(rating_after) over w                        as previous_rating_after,
        lag(match_at) over w                            as previous_match_at,
        lag(season) over w                              as previous_season
    from {{ ref('fct_team_elo') }}
    window w as (partition by team_id order by match_at, match_id)

)

select *
from ordered
where previous_match_at > match_at
   or (
       season = previous_season
       and not is_promotion
       and abs(rating_before - previous_rating_after) > 1e-6
   )
