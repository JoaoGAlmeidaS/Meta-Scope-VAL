-- D20: velocidade do meta, na janela. Por mês e agente: em quantas composições (time × mapa) o
-- agente apareceu e o total de composições do mês, para o pick rate e a reorganização pós-patch.
-- Tier e visão recente entram no grão: os recortes do site somam as contagens antes da taxa
-- (pipeline/analyses.py), e o `pick_rate` daqui vale para a linha, não para o mês inteiro.

with comps as (

    select date_trunc('month', match_date) as month, tier, is_in_recent_window, agents
    from {{ ref('mart_compositions') }}

),

totals as (

    select month, tier, is_in_recent_window, count(*) as compositions
    from comps
    group by all

),

picks as (

    select month, tier, is_in_recent_window, agent, count(*) as compositions_with_agent
    from (select month, tier, is_in_recent_window, unnest(agents) as agent from comps)
    group by all

)

select
    cast(p.month as date)                                       as month,
    p.tier,
    p.is_in_recent_window,
    p.agent,
    p.compositions_with_agent,
    t.compositions,
    p.compositions_with_agent / t.compositions                  as pick_rate
from picks p
join totals t using (month, tier, is_in_recent_window)
