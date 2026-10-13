-- Jogador × mapa, com agente (minúsculo desde o contrato) e stats. Multikills e clutches não
-- entram: vêm zerados por mapa (pegadinha 3).

with source as (

    select * from {{ source('lake', 'raw_player_map') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by map_id, player_id order by season desc) = 1

)

select
    cast(match_id as varchar)           as match_id,
    cast(map_id as varchar)             as map_id,
    cast(player_id as varchar)          as player_id,
    cast(player_name as varchar)        as player_name,
    nullif(cast(team_tag as varchar), '')   as team_tag,  -- time sem tag (pegadinha 40)
    cast(team_id as varchar)            as team_id,
    cast(agent as varchar)              as agent,
    cast(rating as double)              as rating,
    cast(acs as integer)                as acs,
    cast(kills as integer)              as kills,
    cast(deaths as integer)             as deaths,
    cast(assists as integer)            as assists,
    cast(kast as integer)               as kast_pct,
    cast(adr as integer)                as adr,
    cast(hs as integer)                 as headshot_pct,
    cast(first_bloods as integer)       as first_kills,
    cast(first_deaths as integer)       as first_deaths

from deduped
