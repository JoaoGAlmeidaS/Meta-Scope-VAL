-- D17: a tese da janela. Vantagem de lado por mapa e trimestre sobre o HISTÓRICO INTEIRO (a única
-- exceção à janela, de propósito: o drift é o argumento para a janela de 12 meses). Rounds 1–24,
-- só mapas com lado e em escopo. Os patches do trimestre vão junto, para marcar no gráfico.
-- O histórico anterior a 2025 virá de um dataset importado à parte (fonte a definir).
-- O tier entra no grão (recorte do site); a visão recente não: o drift é o histórico inteiro.

select
    r.map_name,
    cast(date_trunc('quarter', r.match_at) as date)             as quarter_start,
    m.tier,
    count(distinct r.map_id)                                    as maps,
    count(*)                                                    as regulation_rounds,
    count(*) filter (where r.winner_side = 'attack')            as attack_rounds_won,
    coalesce(list_sort(list(distinct r.patch) filter (where r.patch is not null)), [])
                                                                as patches
from {{ ref('fct_round') }} r
join {{ ref('fct_match') }} m on m.match_id = r.match_id
where not r.is_excluded
  and r.has_round_sides
  and r.round_number <= 24
group by all
