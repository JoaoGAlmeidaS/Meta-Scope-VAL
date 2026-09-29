-- D8: patches em ordem de lançamento têm número crescente (11.07 < 11.07b < 11.08).
-- Pega data digitada errada no seed mantido à mão.

with patches as (

    select
        patch,
        release_date,
        cast(split_part(patch, '.', 1) as integer) * 1000
            + cast(regexp_extract(split_part(patch, '.', 2), '^[0-9]+') as integer) * 10
            + case when patch like '%b' then 1 else 0 end as patch_key
    from {{ ref('patches') }}

)

select *
from (
    select *, lag(patch_key) over (order by release_date) as previous_key
    from patches
)
where previous_key >= patch_key
