-- Mapas que aparecem em partidas jogadas. O pool ativo muda por patch; aqui fica só o histórico
-- de uso, que a análise recorta pela janela.

with maps as (

    select m.map_name, x.match_at
    from {{ ref('stg_maps') }} m
    join {{ ref('stg_matches') }} x using (match_id)

)

select
    map_name,
    count(*)            as maps_played,
    min(match_at)       as first_played_at,
    max(match_at)       as last_played_at
from maps
group by map_name
