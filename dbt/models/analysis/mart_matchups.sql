{{ config(
    materialized='external',
    location=env_var('DERIVED_DIR', '../data/derived') ~ '/matchups.parquet'
) }}

-- D21: matriz de confrontos. Para todo par de times ativos na janela, a probabilidade de vitória
-- pela fórmula do Elo, com o rating atual. Gravada em Parquet (critério de pronto do D21) e lida
-- pelo site_artifacts para o predictions/{id}.json. Estatística, não conselho de aposta: os
-- circuitos quase não se cruzam, e a comparação entre regiões vale menos que dentro delas.

with teams as (

    select team_id, rating, region, tier
    from {{ ref('mart_team_ratings') }}

)

select
    a.team_id,
    b.team_id                                                   as opponent_id,
    a.rating                                                    as rating,
    b.rating                                                    as opponent_rating,
    1.0 / (1.0 + pow(10.0, (b.rating - a.rating) / 400.0))      as win_probability,
    a.region = b.region and a.tier = b.tier                     as same_circuit
from teams a
join teams b on a.team_id <> b.team_id
