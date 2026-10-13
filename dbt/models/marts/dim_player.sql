-- Jogadores, uma linha por id (D10). Saem de `raw_player_map`, nunca de `/players` (leaderboard
-- top 100, não cadastro). Nome e time são os mais recentes; os da época ficam no fct_player_map.

with appearances as (

    select pm.player_id, pm.player_name, pm.team_id, pm.agent, pm.map_id, m.match_at
    from {{ ref('stg_player_maps') }} pm
    join {{ ref('stg_matches') }} m using (match_id)

),

latest as (

    select player_id, player_name, team_id
    from appearances
    qualify row_number() over (partition by player_id order by match_at desc, map_id desc) = 1

),

main_agent as (

    select player_id, agent
    from appearances
    group by player_id, agent
    qualify row_number() over (partition by player_id order by count(*) desc, agent) = 1

),

stats as (

    select
        player_id,
        count(*)            as maps_played,
        min(match_at)       as first_match_at,
        max(match_at)       as last_match_at
    from appearances
    group by player_id

)

select
    s.player_id,
    l.player_name,
    l.team_id                   as latest_team_id,
    a.agent                     as main_agent,
    s.maps_played,
    s.first_match_at,
    s.last_match_at
from stats s
join latest l using (player_id)
join main_agent a using (player_id)
