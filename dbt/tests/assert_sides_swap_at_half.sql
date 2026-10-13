-- D13: dentro de cada tempo o atacante é um só, e ele troca no intervalo (round 13).
-- Falha com um atacante que muda no meio do tempo ou que continua atacando depois do intervalo.

with halves as (

    select
        map_id,
        half,
        count(distinct attacker_team_id)    as attackers,
        min(attacker_team_id)               as attacker_team_id
    from {{ ref('fct_round') }}
    where half in (1, 2)
      and attacker_team_id is not null
    group by all

)

select map_id, half, attackers, attacker_team_id, 'atacante muda dentro do tempo' as problem
from halves
where attackers > 1

union all

select h1.map_id, 2, h2.attackers, h2.attacker_team_id, 'atacante não troca no intervalo'
from halves h1
join halves h2 on h2.map_id = h1.map_id and h1.half = 1 and h2.half = 2
where h1.attackers = 1
  and h2.attackers = 1
  and h1.attacker_team_id = h2.attacker_team_id
