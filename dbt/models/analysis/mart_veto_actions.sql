-- D19/D27: o veto inteiro na janela, por mapa e passo (ban, pick, decider): base da visualização
-- de veto do site. Um registro por mapa × ação × posição no veto × tier × visão recente: os
-- recortes do site somam as contagens (pipeline/analyses.py).

select
    v.map_name,
    v.veto_action,
    v.veto_step,
    m.tier,
    m.is_in_recent_window,
    count(*)                                                    as times,
    count(*) filter (where v.was_played)                        as times_played,
    max(cast(v.match_at as date))                               as last_match_date
from {{ ref('fct_veto') }} v
join {{ ref('fct_match') }} m on m.match_id = v.match_id
where v.is_in_analysis_window
  and not v.is_excluded
group by all
