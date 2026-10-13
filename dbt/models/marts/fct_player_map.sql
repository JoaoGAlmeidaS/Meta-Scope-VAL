-- Jogador × mapa (D11), com nome e tag da época, agente e stats. Base do fct_composition.

with players as (

    select * from {{ ref('stg_player_maps') }}

),

maps as (

    select * from {{ ref('fct_map') }}

)

select
    p.map_id,
    p.match_id,
    mp.event_id,
    mp.season,
    mp.match_at,
    mp.patch,
    mp.map_name,
    mp.is_excluded,
    mp.is_in_analysis_window,
    p.player_id,
    p.player_name,
    p.team_id,
    p.team_tag,
    p.agent,
    p.team_id = mp.winner_team_id                       as won_map,
    p.rating,
    p.acs,
    p.kills,
    p.deaths,
    p.assists,
    p.kast_pct,
    p.adr,
    p.headshot_pct,
    p.first_kills,
    p.first_deaths
from players p
join maps mp using (map_id)
