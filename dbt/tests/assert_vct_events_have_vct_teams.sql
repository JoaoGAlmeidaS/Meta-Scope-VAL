-- Evento VCT de verdade é disputado por times do circuito: os parceiros jogam vários eventos VCT
-- na temporada (Kickoff, Stages, internacionais). Torneio aberto que o vlr.gg lista como VCT
-- (Project Blender 2026, pegadinha 43) aparece aqui: mais da metade dos times nunca jogou outro
-- evento VCT. Cada um entraria no Elo com o rating inicial do VCT e rotularia de VCT times da VCL.
-- Aviso, não erro: o seed `event_overrides.csv` exclui ou reclassifica depois do julgamento.
-- Só evento com 8 times ou mais: torneio aberto é chave grande (o Blender tinha 64), e evento
-- pequeno, como o recorte de duas partidas do lake de fixtures, não diz nada.

{{ config(severity='warn') }}

with teams_by_event as (

    select event_id, team1_id as team_id from {{ ref('fct_match') }} where not is_excluded
    union
    select event_id, team2_id from {{ ref('fct_match') }} where not is_excluded

),

vct_events as (

    select event_id, event_name from {{ ref('dim_event') }} where tier = 'vct' and not is_excluded

),

with_other_vct as (

    -- times do evento que jogaram algum outro evento VCT
    select distinct t.event_id, t.team_id
    from teams_by_event t
    join teams_by_event o on o.team_id = t.team_id and o.event_id <> t.event_id
    join vct_events v on v.event_id = o.event_id

)

select
    v.event_id,
    v.event_name,
    count(distinct t.team_id)                                   as teams,
    count(distinct t.team_id) filter (where w.team_id is null)  as teams_without_other_vct_event
from vct_events v
join teams_by_event t using (event_id)
left join with_other_vct w on w.event_id = t.event_id and w.team_id = t.team_id
group by all
having count(distinct t.team_id) >= 8
   and count(distinct t.team_id) filter (where w.team_id is null) * 2 > count(distinct t.team_id)
