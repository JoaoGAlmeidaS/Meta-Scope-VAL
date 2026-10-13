-- Times, uma linha por id (D10). Saem das partidas, nunca de `/teams` (ranking, não cadastro).
-- Nome, tag e região são os mais recentes: um retrato. O nome e a tag da época ficam nos fatos
-- (decisão do D10: snapshot + época nos fatos, sem SCD).

with appearances as (

    select * from {{ ref('int_team_matches') }}

),

latest_name as (

    select team_id, team_name
    from appearances
    qualify row_number() over (partition by team_id order by match_at desc, match_id desc) = 1

),

-- A tag só existe do lado dos jogadores (`players[].teamTag`), já resolvida para id pela ponte.
tags as (

    select pm.team_id, pm.team_tag, m.match_at
    from {{ ref('stg_player_maps') }} pm
    join {{ ref('stg_matches') }} m using (match_id)
    where pm.team_id is not null

),

latest_tag as (

    select team_id, team_tag
    from tags
    qualify row_number() over (partition by team_id order by match_at desc, team_tag) = 1

),

latest_region as (

    select r.team_id, r.team_region
    from {{ ref('int_team_match_regions') }} r
    join appearances a using (match_id, team_id)
    qualify row_number() over (partition by r.team_id order by a.match_at desc) = 1

),

stats as (

    select
        team_id,
        count(*)                                    as matches_played,
        count(*) filter (where won_match)           as matches_won,
        min(match_at)                               as first_match_at,
        max(match_at)                               as last_match_at
    from appearances
    group by team_id

)

select
    s.team_id,
    n.team_name,
    t.team_tag,
    r.team_region                                   as region,
    s.first_match_at,
    s.last_match_at,
    s.matches_played,
    s.matches_won
from stats s
join latest_name n using (team_id)
left join latest_tag t using (team_id)
left join latest_region r using (team_id)
