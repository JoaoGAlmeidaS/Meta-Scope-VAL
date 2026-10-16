-- D26: desempenho de cada time por mapa na janela (mapas jogados e vencidos; o IC sai em Python).

with sides as (

    select map_id, map_name, match_at, team1_id as team_id, winner_team_id
    from {{ ref('fct_map') }}
    where is_in_analysis_window and not is_excluded and winner_team_id is not null
    union all
    select map_id, map_name, match_at, team2_id, winner_team_id
    from {{ ref('fct_map') }}
    where is_in_analysis_window and not is_excluded and winner_team_id is not null

)

select
    team_id,
    map_name,
    count(*)                                                    as maps_played,
    count(*) filter (where winner_team_id = team_id)            as maps_won,
    max(cast(match_at as date))                                 as last_played_on
from sides
group by all
