-- Eventos com os overrides aplicados (seed event_overrides, D8): o tier e a região valem daqui
-- em diante. `is_excluded` não apaga nada — os fatos carregam a flag e os marts de análise filtram.

with events as (

    select * from {{ ref('stg_events') }}

),

overrides as (

    select * from {{ ref('event_overrides') }}

),

resolved as (

    select
        e.*,
        coalesce(o.tier, e.tier)                    as resolved_tier,
        coalesce(o.region, e.region)                as resolved_region,
        coalesce(o.action = 'exclude', false)       as is_excluded,
        o.reason                                    as override_reason
    from events e
    left join overrides o using (event_id)

)

select
    event_id,
    event_name,
    season,
    event_status,
    resolved_tier                                   as tier,
    case resolved_tier when 'vct' then 1 when 'vcl' then 2 end
                                                    as tier_level,
    resolved_region                                 as region,
    resolved_region = 'international'               as is_international,
    is_excluded,
    override_reason,
    tier                                            as source_tier,
    region                                          as source_region,
    is_tier_ambiguous,
    first_listed_on                                 as start_date,
    last_listed_on                                  as end_date,
    country_code,
    prize_pool_usd
from resolved
