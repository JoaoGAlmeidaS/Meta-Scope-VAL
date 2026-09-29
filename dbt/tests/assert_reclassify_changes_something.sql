-- D8: `reclassify` sem tier nem região novos é linha morta no seed; `exclude` não troca nada.

select *
from {{ ref('event_overrides') }}
where (action = 'reclassify' and tier is null and region is null)
   or (action = 'exclude' and (tier is not null or region is not null))
