-- Completude da coleta por evento (D13): partidas concluídas na listagem × gravadas ×
-- rejeitadas. Só um evento completo entra na validação cruzada com o gabarito: comparar
-- agregados de um evento pela metade mede a coleta, não a reconstrução.

with listed as (

    select event_id, match_id
    from {{ ref('stg_event_matches') }}
    where listed_status = 'completed'

),

-- Da fonte, não do staging: partida sem mapa jogado foi coletada, só não entra na análise.
collected as (

    select distinct match_id from {{ source('lake', 'raw_match') }}

),

rejected as (

    select match_id, is_final from {{ ref('stg_rejects') }}

),

with_details as (

    select distinct event_id from {{ source('lake', 'raw_match') }}
    union
    select distinct event_id from {{ ref('stg_rejects') }}

),

with_gabarito as (

    select distinct event_id from {{ ref('stg_event_agents') }}

)

select
    l.event_id,
    count(*)                                                        as listed_matches,
    count(c.match_id)                                               as collected_matches,
    count(r.match_id) filter (where r.is_final)                     as rejected_matches,
    count(r.match_id) filter (where not r.is_final)                 as pending_retry_matches,
    count(*) filter (where c.match_id is null and r.match_id is null)
                                                                    as missing_matches,
    l.event_id in (select event_id from with_details)               as has_details,
    l.event_id in (select event_id from with_gabarito)              as has_gabarito,
    count(c.match_id) = count(*)                                    as is_complete
from listed l
left join collected c using (match_id)
left join rejected r using (match_id)
group by l.event_id
