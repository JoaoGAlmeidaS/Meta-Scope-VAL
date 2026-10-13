-- Passos do veto, uma linha por (match_id, veto_step) (D11). `was_played` separa o decider
-- que não chegou a ser jogado (BO3 2–0) do que foi (pegadinha 14).

with vetoes as (

    select * from {{ ref('stg_vetoes') }}

),

matches as (

    select * from {{ ref('fct_match') }}

),

maps as (

    select match_id, map_name, map_id from {{ ref('fct_map') }}

)

select
    v.match_id,
    m.event_id,
    m.season,
    m.match_at,
    m.patch,
    m.is_excluded,
    m.is_in_analysis_window,
    v.veto_step,
    v.veto_action,
    v.map_name,
    v.team_id,
    v.team_tag,
    mp.map_id,
    mp.map_id is not null                               as was_played
from vetoes v
join matches m using (match_id)
left join maps mp on mp.match_id = v.match_id and mp.map_name = v.map_name
