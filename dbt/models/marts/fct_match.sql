-- Partidas (séries), uma linha por match_id (D11). Os fatos cobrem todo o histórico coletado:
-- a janela vira flag aqui e filtro nos marts de análise (D16); o drift (D17) lê tudo.
-- Nome do time é o da época; a região do time é a da época (int_team_match_regions).

with matches as (

    select * from {{ ref('stg_matches') }}

),

events as (

    select * from {{ ref('dim_event') }}

),

patches as (

    select * from {{ ref('dim_patch') }}

),

regions as (

    select * from {{ ref('int_team_match_regions') }}

),

with_patch as (

    select m.*, p.patch
    from matches m
    asof left join patches p
        on m.match_date >= p.release_date

)

select
    m.match_id,
    m.event_id,
    m.season,
    m.series_name,
    m.match_at,
    m.match_date,
    m.patch,
    e.tier,
    e.tier_level,
    e.region                                            as event_region,
    e.is_international,
    -- Fora da análise: evento excluído pelo seed ou showmatch (pegadinha 41). Todos os fatos
    -- herdam esta flag; `is_showmatch` fica à parte para quem precisar distinguir.
    coalesce(e.is_excluded, false) or m.is_showmatch     as is_excluded,
    m.is_showmatch,
    m.match_format,
    m.best_of,
    m.fixed_maps,
    m.maps_played,
    m.maps_without_data,
    m.team1_id,
    m.team1_name,
    r1.team_region                                      as team1_region,
    m.team2_id,
    m.team2_name,
    r2.team_region                                      as team2_region,
    m.team1_score,
    m.team2_score,
    case
        when m.team1_score > m.team2_score then m.team1_id
        when m.team2_score > m.team1_score then m.team2_id
    end                                                 as winner_team_id,
    m.team1_score = m.team2_score                       as is_draw,
    m.has_tabs,
    m.match_date between {{ analysis_window_start() }} and {{ as_of_date() }}
                                                        as is_in_analysis_window,
    m.match_date between {{ elo_warmup_start() }} and {{ as_of_date() }}
                                                        as is_in_elo_range
from with_patch m
left join events e using (event_id)
left join regions r1 on r1.match_id = m.match_id and r1.team_id = m.team1_id
left join regions r2 on r2.match_id = m.match_id and r2.team_id = m.team2_id
