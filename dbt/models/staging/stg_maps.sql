-- Mapas jogados, uma linha por map_id. Lado padronizado: CT = defesa, T = ataque.
-- `*_def_rounds` e `*_atk_rounds` contam só o tempo regulamentar (rounds 1–24); o placar inclui
-- o overtime (pegadinha 1). Mapa sem histórico de lado (pegadinha 22): contadores nulos e
-- `has_round_sides = false`; o placar e a composição continuam valendo. Mapa refeito por lobby
-- remake (pegadinha 36): `has_complete_stats = false`; arquivo gravado antes da coluna vale true.

with source as (

    select * from {{ source('lake', 'raw_map') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by map_id order by season desc) = 1

)

select
    cast(map_id as varchar)                 as map_id,
    cast(match_id as varchar)               as match_id,
    cast(map_order as integer)              as map_order,
    cast(map_name as varchar)               as map_name,
    cast(status as varchar)                 as map_status,
    cast(picked_by_team_id as varchar)      as picked_by_team_id,
    cast(duration_s as integer)             as duration_s,
    cast(team1_id as varchar)               as team1_id,
    cast(team1_score as integer)            as team1_score,
    cast(team1_rounds_ct as integer)        as team1_def_rounds,
    cast(team1_rounds_t as integer)         as team1_atk_rounds,
    cast(team2_id as varchar)               as team2_id,
    cast(team2_score as integer)            as team2_score,
    cast(team2_rounds_ct as integer)        as team2_def_rounds,
    cast(team2_rounds_t as integer)         as team2_atk_rounds,
    cast(bridge_ok as boolean)              as is_bridge_ok,
    cast(has_round_sides as boolean)        as has_round_sides,
    coalesce(cast(has_complete_stats as boolean), true)
                                            as has_complete_stats

from deduped
