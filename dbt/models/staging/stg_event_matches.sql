-- Listagem de partidas de cada evento: serve à completude da coleta (D13), não à análise.
-- Datas sem fuso e times sem id (pegadinha 16): o que vale para análise vem do detalhe.

with source as (

    select * from {{ source('lake', 'raw_event_match') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by event_id, match_id order by season desc) = 1

)

select
    cast(event_id as varchar)       as event_id,
    cast(match_id as varchar)       as match_id,
    cast(season as integer)         as season,
    cast(status as varchar)         as listed_status,
    cast(listed_on as date)         as listed_on,
    cast(team1_name as varchar)     as team1_name,
    cast(team1_score as integer)    as team1_score,
    cast(team2_name as varchar)     as team2_name,
    cast(team2_score as integer)    as team2_score

from deduped
