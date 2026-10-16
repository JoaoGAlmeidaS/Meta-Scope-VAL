-- Partidas (séries), uma linha por match_id. Colunas team1/team2 seguem `teams[]` do detalhe.
-- Partida sem mapa jogado (forfeit) é descartada aqui e contada no teste
-- assert_matches_without_maps_are_counted.

with source as (

    select * from {{ source('lake', 'raw_match') }}

),

-- Idempotência: a mesma partida em dois arquivos de evento conta uma vez (a coleta mais recente).
deduped as (

    select *
    from source
    qualify row_number() over (partition by match_id order by collected_at desc) = 1

)

select
    cast(match_id as varchar)                                   as match_id,
    cast(event_id as varchar)                                   as event_id,
    cast(season as integer)                                     as season,
    cast(event_series as varchar)                               as series_name,
    -- Showmatch ("Showmatch: Main Event", "All-Star Match"...): não é jogo competitivo (pegadinha 41).
    coalesce(lower(event_series) like 'showmatch%', false)      as is_showmatch,
    lower(cast(format as varchar))                              as match_format,
    try_cast(regexp_extract(lower(format), 'bo(\d+)', 1) as integer)
                                                                as best_of,
    -- Formato de mapas fixos ("2 maps", fase de grupos do Challengers Spain): não é melhor-de-N e
    -- admite empate (pegadinha 38).
    try_cast(regexp_extract(lower(format), '(\d+) maps', 1) as integer)
                                                                as fixed_maps,
    cast(match_ts as timestamp)                                 as match_at,
    cast(match_ts as date)                                      as match_date,
    cast(team1_id as varchar)                                   as team1_id,
    cast(team1_name as varchar)                                 as team1_name,
    cast(team1_score as integer)                                as team1_score,
    cast(team2_id as varchar)                                   as team2_id,
    cast(team2_name as varchar)                                 as team2_name,
    cast(team2_score as integer)                                as team2_score,
    -- Logo de cada time (CDN do vlr.gg); o contrato já anulou o placeholder (pegadinha 42).
    nullif(cast(team1_img as varchar), '')                      as team1_img,
    nullif(cast(team2_img as varchar), '')                      as team2_img,
    cast(n_maps as integer)                                     as maps_played,
    -- Mapas descartados pelo contrato por não ter dado nenhum, quase sempre W.O. de um mapa no
    -- meio da série (pegadinha 33). Arquivo gravado antes da coluna vale 0.
    coalesce(cast(n_maps_without_data as integer), 0)           as maps_without_data,
    cast(has_tabs as boolean)                                   as has_tabs,
    cast(collected_at as timestamp)                             as collected_at

from deduped
where n_maps > 0
