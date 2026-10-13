-- Patches do seed (D8), com a vigência de cada um. A partida recebe o patch vigente na data dela
-- (ASOF JOIN nos fatos); torneio que trava patch anterior não é modelado (pegadinha 18).

with patches as (

    select * from {{ ref('patches') }}

)

select
    patch,
    major                                                       as patch_major,
    release_date,
    lead(release_date) over (order by release_date)             as next_release_date,
    lead(release_date) over (order by release_date) is null     as is_latest,
    source_url
from patches
