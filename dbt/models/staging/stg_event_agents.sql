-- Gabarito do vlr.gg por evento × mapa × agente (pegadinha 12): inteiros arredondados, sem
-- contagem de rounds. Só entra na validação cruzada do D13, nunca numa análise.

with source as (

    select * from {{ source('lake', 'raw_event_agents') }}

)

select
    cast(event_id as varchar)               as event_id,
    cast(season as integer)                 as season,
    cast(map_name as varchar)               as map_name,
    map_name = 'All'                        as is_all_maps,
    cast(played as integer)                 as maps_played,
    cast(atk_win_rate as double)            as attack_win_rate_pct,
    cast(def_win_rate as double)            as defense_win_rate_pct,
    lower(cast(agent as varchar))           as agent,
    cast(pick_rate as double)               as pick_rate_pct

from source
