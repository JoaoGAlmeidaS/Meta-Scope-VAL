-- Mapas jogados, uma linha por map_id (D11). `is_decider` vem do veto: o mapa que sobrou.
-- `*_def_rounds`/`*_atk_rounds` só contam o tempo regulamentar; o placar inclui o overtime.

with maps as (

    select * from {{ ref('stg_maps') }}

),

matches as (

    select * from {{ ref('fct_match') }}

),

-- Um registro por mapa: o vlr.gg às vezes digita o veto errado (o mesmo mapa como pick e como
-- decider, ou o decider duas vezes), e o join multiplicaria o mapa. Mapa escolhido no veto nunca
-- é o decider.
vetoes as (

    select
        match_id,
        map_name,
        bool_or(veto_action = 'decider') and not bool_or(veto_action = 'pick') as is_decider
    from {{ ref('stg_vetoes') }}
    where veto_action in ('pick', 'decider')
    group by all

),

-- Mapa sem estatística: sem duração e sem rating de nenhum jogador (644253, 459856). O gabarito
-- do vlr.gg o deixa fora, como o mapa refeito marcado no contrato (pegadinha 36).
player_stats as (

    select map_id, bool_or(rating is not null) as has_player_stats
    from {{ ref('stg_player_maps') }}
    group by map_id

)

select
    mp.map_id,
    mp.match_id,
    m.event_id,
    m.season,
    m.match_at,
    m.patch,
    m.tier,
    m.is_excluded,
    m.is_showmatch,
    m.is_in_analysis_window,
    mp.map_order,
    mp.map_name,
    mp.picked_by_team_id,
    coalesce(v.is_decider, false)                       as is_decider,
    mp.team1_id,
    mp.team1_score,
    mp.team1_def_rounds,
    mp.team1_atk_rounds,
    mp.team2_id,
    mp.team2_score,
    mp.team2_def_rounds,
    mp.team2_atk_rounds,
    case
        when mp.team1_score > mp.team2_score then mp.team1_id
        when mp.team2_score > mp.team1_score then mp.team2_id
    end                                                 as winner_team_id,
    mp.team1_score + mp.team2_score                     as rounds_played,
    mp.team1_score + mp.team2_score > 24                as went_to_overtime,
    mp.duration_s,
    mp.is_bridge_ok,
    mp.has_round_sides,
    mp.has_complete_stats
        and (mp.duration_s is not null or coalesce(ps.has_player_stats, false))
                                                        as has_complete_stats
from maps mp
join matches m using (match_id)
left join vetoes v on v.match_id = mp.match_id and v.map_name = mp.map_name
left join player_stats ps on ps.map_id = mp.map_id
