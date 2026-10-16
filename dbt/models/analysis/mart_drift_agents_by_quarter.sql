-- D17: a tese da janela pelo meta. Pick rate de cada agente por mapa e trimestre sobre o HISTÓRICO
-- INTEIRO (mesma exceção à janela do mart_drift_side_by_quarter): quanto mais antigo o trimestre,
-- mais diferente do meta atual. A distância entre trimestres sai em Python (pipeline/analyses.py).
-- O tier entra no grão (recorte do site), como no drift de lado.

with comps as (

    select
        c.map_name,
        cast(date_trunc('quarter', c.match_at) as date)         as quarter_start,
        m.tier,
        c.agents
    from {{ ref('fct_composition') }} c
    join {{ ref('fct_match') }} m on m.match_id = c.match_id
    where not c.is_excluded
      and c.players = 5

),

totals as (

    select map_name, quarter_start, tier, count(*) as compositions
    from comps
    group by all

),

picks as (

    select map_name, quarter_start, tier, agent, count(*) as compositions_with_agent
    from (select map_name, quarter_start, tier, unnest(agents) as agent from comps)
    group by all

)

select
    p.map_name,
    p.quarter_start,
    p.tier,
    p.agent,
    p.compositions_with_agent,
    t.compositions,
    p.compositions_with_agent / t.compositions                  as pick_rate
from picks p
join totals t using (map_name, quarter_start, tier)
