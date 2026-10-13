-- Uma linha por time por partida: a visão "do lado do time", base de dim_team, da região do time
-- e, no D15, do Elo. Nome do time é o da época (o da partida).

with matches as (

    select * from {{ ref('stg_matches') }}

),

sides as (

    select
        match_id, event_id, season, match_at, match_date,
        team1_id as team_id, team1_name as team_name,
        team2_id as opponent_id,
        team1_score as maps_won, team2_score as maps_lost,
        true as is_team1
    from matches

    union all

    select
        match_id, event_id, season, match_at, match_date,
        team2_id, team2_name,
        team1_id,
        team2_score, team1_score,
        false
    from matches

)

select
    *,
    maps_won > maps_lost as won_match
from sides
