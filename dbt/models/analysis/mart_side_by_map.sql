-- D18: vantagem de lado por mapa, na janela. Um registro por mapa jogado com histórico de lado
-- (pegadinha 22), contando só o tempo regulamentar (rounds 1–24): o overtime alterna o lado a cada
-- round e não diz nada sobre o mapa. O IC sai em Python, com bootstrap por mapa (rounds do mesmo
-- mapa não são independentes). `tier` e `is_in_recent_window` (da partida) são os recortes do site.

select
    r.map_id,
    r.match_id,
    r.event_id,
    r.map_name,
    r.patch,
    cast(r.match_at as date)                                    as match_date,
    m.tier,
    m.is_in_recent_window,
    count(*)                                                    as regulation_rounds,
    count(*) filter (where r.winner_side = 'attack')            as attack_rounds_won,
    count(*) filter (where r.winner_side = 'defense')           as defense_rounds_won
from {{ ref('fct_round') }} r
join {{ ref('fct_match') }} m on m.match_id = r.match_id
where r.is_in_analysis_window
  and not r.is_excluded
  and r.has_round_sides
  and r.round_number <= 24
group by all
