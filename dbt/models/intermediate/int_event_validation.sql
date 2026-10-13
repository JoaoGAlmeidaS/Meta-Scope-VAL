-- Validação cruzada com o gabarito do vlr.gg (D13), por evento × mapa, só em evento completo e
-- dentro do escopo da análise (fora do seed de exclusões: torneio de terceiro e China Evolution
-- Series não entram na análise, e os dados deles não precisam de exceção escrita).
--
-- O `/events/{id}/agents` é um cálculo independente sobre os mesmos dados brutos: se a nossa
-- reconstrução bate com ele, a coleta está completa e o lado e a composição estão certos.
--
--   maps_played      mapas jogados por mapa          → completude           (tolerância 0)
--   attack_win_rate  % de rounds vencidos no ataque  → reconstrução de lado (tolerância em p.p.)
--   pick_rate        % de composições com o agente   → composições          (tolerância em p.p.)
--
-- O vlr.gg calcula o `atkWinRate` só com o tempo regulamentar (rounds 1–24): descoberto no D13
-- com o evento 2977, em que os 8 mapas batem exatamente assim e 3 erram por 1 p.p. com overtime.
--
-- Showmatch (pegadinha 41): o gabarito do VCT o deixa fora (2498, 2499, 2500, 2501), e a leitura
-- `complete` também.
--
-- Mapa refeito por lobby remake ("Map N stats are incomplete", pegadinha 36): o vlr.gg ora o deixa
-- fora do agregado (2776, 2780, 2976), ora o conta (3063), sem nada na API que diga qual. Cada
-- check é calculado nas duas leituras — `all` (todo mapa) e `complete` (sem o mapa refeito) — e
-- vale a que bate; sem mapa refeito no evento × mapa, as duas são iguais. Sem nenhuma bater, fica
-- a mais próxima do gabarito.
--
-- O gabarito é inteiro arredondado: o nosso valor é arredondado antes de comparar. A linha
-- `All` é o evento inteiro. Divergência aceita vai para o seed validation_exceptions, com motivo.

{% set tolerance = var('validation_tolerance_pp') %}

with events as (

    select c.event_id
    from {{ ref('int_event_completeness') }} c
    join {{ ref('dim_event') }} e using (event_id)
    where c.is_complete and c.has_gabarito and not e.is_excluded

),

readings as (

    select * from (values ('all'), ('complete')) as r (reading)

),

event_maps as (

    select event_id, map_id, map_name, has_complete_stats and not is_showmatch as is_competitive_complete
    from {{ ref('fct_map') }}
    where event_id in (select event_id from events)

),

maps as (

    select r.reading, m.event_id, m.map_id, m.map_name
    from event_maps m
    cross join readings r
    where r.reading = 'all' or m.is_competitive_complete

    union all

    select r.reading, m.event_id, m.map_id, 'All'
    from event_maps m
    cross join readings r
    where r.reading = 'all' or m.is_competitive_complete

),

played as (

    select reading, event_id, map_name, count(*) as ours
    from maps
    group by all

),

attack as (

    select
        m.reading,
        m.event_id,
        m.map_name,
        100.0 * count(*) filter (where r.winner_side = 'attack') / count(*) as ours
    from {{ ref('fct_round') }} r
    join maps m using (map_id)
    where r.winner_side is not null  -- mapa sem histórico de lado não entra (pegadinha 22)
      and r.round_number <= 24       -- metodologia do gabarito: sem overtime
    group by all

),

-- Uma linha por agente em cada composição (time × mapa).
comps as (

    select m.reading, m.event_id, m.map_name, p.map_id, p.team_id, p.agent
    from {{ ref('fct_player_map') }} p
    join maps m using (map_id)
    where p.team_id is not null

),

comp_totals as (

    select reading, event_id, map_name, count(distinct map_id || '|' || team_id) as compositions
    from comps
    group by all

),

picks as (

    select
        c.reading,
        c.event_id,
        c.map_name,
        c.agent,
        100.0 * count(distinct c.map_id || '|' || c.team_id) / any_value(t.compositions) as ours
    from comps c
    join comp_totals t using (reading, event_id, map_name)
    group by all

),

gabarito as (

    select g.*, r.reading
    from {{ ref('stg_event_agents') }} g
    cross join readings r
    where g.event_id in (select event_id from events)

),

gabarito_maps as (

    select distinct reading, event_id, map_name, maps_played, attack_win_rate_pct
    from gabarito

),

checks as (

    select
        reading, event_id, map_name, 'maps_played' as check_name, cast(null as varchar) as agent,
        cast(o.ours as double) as ours, cast(g.maps_played as double) as theirs,
        0 as tolerance_pp
    from played o
    full join gabarito_maps g using (reading, event_id, map_name)

    union all

    select
        reading, event_id, map_name, 'attack_win_rate', null,
        o.ours, g.attack_win_rate_pct,
        {{ tolerance }}
    from attack o
    full join gabarito_maps g using (reading, event_id, map_name)

    union all

    select
        reading, event_id, map_name, 'pick_rate', agent,
        p.ours, g.pick_rate_pct,
        {{ tolerance }}
    from picks p
    full join (select reading, event_id, map_name, agent, pick_rate_pct from gabarito) g
        using (reading, event_id, map_name, agent)

),

-- Chave que falta numa leitura (agente só no mapa refeito, por exemplo) vale 0 contra 0 nela.
check_keys as (

    select distinct event_id, map_name, check_name, agent, tolerance_pp
    from checks

),

grid as (

    select
        r.reading,
        k.*,
        coalesce(c.ours, 0)                                             as ours,
        coalesce(c.theirs, 0)                                           as theirs
    from check_keys k
    cross join readings r
    left join checks c
        on c.reading = r.reading
       and c.event_id = k.event_id
       and c.map_name = k.map_name
       and c.check_name = k.check_name
       and c.agent is not distinct from k.agent

),

scored as (

    select
        *,
        round(ours) - theirs                                            as diff,
        abs(round(ours) - theirs) <= tolerance_pp                       as is_within_tolerance
    from grid

)

select
    event_id,
    map_name,
    check_name,
    agent,
    ours,
    theirs,
    diff,
    tolerance_pp,
    is_within_tolerance,
    reading = 'all'                                                     as counts_remade_maps
from scored
qualify row_number() over (
    partition by event_id, map_name, check_name, agent
    order by is_within_tolerance desc, abs(diff), reading
) = 1
