-- Composições: uma linha por time × mapa, com os 5 agentes (D11). `composition_key` é a lista
-- ordenada, para agrupar a mesma comp independente de quem jogou o quê. Jogador sem time
-- resolvido pela ponte fica de fora (o mapa aparece com menos de 5 e o teste acusa).

with players as (

    select * from {{ ref('fct_player_map') }}
    where team_id is not null

)

select
    map_id,
    match_id,
    event_id,
    season,
    match_at,
    patch,
    map_name,
    is_excluded,
    is_in_analysis_window,
    team_id,
    list_sort(list(agent))                              as agents,
    array_to_string(list_sort(list(agent)), '+')        as composition_key,
    count(*)                                            as players,
    bool_and(won_map)                                   as won_map
from players
group by all
