-- Partidas que a coleta não gravou: contrato, API, não finalizada ou indisponível.
-- `unavailable` é tentada de novo na próxima coleta; as demais são definitivas.

with source as (

    select * from {{ source('lake', 'raw_reject') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by match_id order by collected_at desc) = 1

)

select
    cast(event_id as varchar)           as event_id,
    cast(match_id as varchar)           as match_id,
    cast(season as integer)             as season,
    cast(reason as varchar)             as reject_reason,
    reason <> 'unavailable'             as is_final,
    cast(error as varchar)              as error_message,
    cast(collected_at as timestamp)     as collected_at

from deduped
