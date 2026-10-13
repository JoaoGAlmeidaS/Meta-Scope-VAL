-- Eventos como a coleta viu. Overrides (exclusão, tier, região) são aplicados no dim_event.

with source as (

    select * from {{ source('lake', 'raw_event') }}

)

select
    cast(event_id as varchar)                           as event_id,
    cast(name as varchar)                               as event_name,
    cast(status as varchar)                             as event_status,
    cast(tier as varchar)                               as tier,
    cast(tier_ambiguous as boolean)                     as is_tier_ambiguous,
    cast(region as varchar)                             as region,
    cast(season as integer)                             as season,
    cast(country as varchar)                            as country_code,
    try_cast(nullif(prizepool, '') as integer)          as prize_pool_usd,
    cast(first_listed_on as date)                       as first_listed_on,
    cast(last_listed_on as date)                        as last_listed_on,
    cast(collected_at as timestamp)                     as collected_at

from source
