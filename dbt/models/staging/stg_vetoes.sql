-- Passos do veto. `remains` vira `decider`: o mapa que sobra. Pode não existir veto nenhum
-- (partida VCL 707490), e o decider pode não ter sido jogado (pegadinha 14).

with source as (

    select * from {{ source('lake', 'raw_veto') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by match_id, step order by season desc) = 1

)

select
    cast(match_id as varchar)                                       as match_id,
    cast(step as integer)                                           as veto_step,
    case action when 'remains' then 'decider' else action end       as veto_action,
    cast(map_name as varchar)                                       as map_name,
    cast(team_tag as varchar)                                       as team_tag,
    cast(team_id as varchar)                                        as team_id

from deduped
