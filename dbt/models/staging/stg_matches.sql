-- D9: staging de partidas. Tipagem explicita, nomes padronizados, sem regra de negocio.
-- Placeholder: o schema do Parquet fechou no D6 (ingestion/lake.py); o select real e do D9.

with source as (

    select * from {{ source('lake', 'raw_match') }}

),

renamed as (

    select
        cast(match_id as varchar)             as match_id,
        cast(event_id as varchar)             as event_id,
        cast(match_datetime as timestamp)     as match_datetime,
        cast(team_a_id as varchar)            as team_a_id,
        cast(team_b_id as varchar)            as team_b_id,
        cast(team_a_score as integer)         as team_a_score,
        cast(team_b_score as integer)         as team_b_score,
        cast(split as varchar)                as split

    from source

)

select * from renamed
