-- D13: validação cruzada com o gabarito do vlr.gg. Falha em toda divergência fora da tolerância
-- que não esteja justificada no seed validation_exceptions (evento, mapa, check, agente).

select v.*
from {{ ref('int_event_validation') }} v
left join {{ ref('validation_exceptions') }} x
    on x.event_id = v.event_id
   and x.map_name = v.map_name
   and x.check_name = v.check_name
   and coalesce(x.agent, '') = coalesce(v.agent, '')
where not v.is_within_tolerance
  and x.check_name is null
