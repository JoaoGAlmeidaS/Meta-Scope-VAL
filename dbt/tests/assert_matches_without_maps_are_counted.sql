-- D9/D13: partida sem mapa jogado (forfeit) é descartada no stg_matches. Aqui ela é contada: o
-- aviso mostra quantas saíram. No D2 não houve forfeit nos casos testados.

{{ config(severity='warn') }}

select match_id, event_id
from {{ source('lake', 'raw_match') }}
where n_maps = 0
