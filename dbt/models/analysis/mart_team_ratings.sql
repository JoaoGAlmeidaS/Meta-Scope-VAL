-- Ranking Elo dos times ativos na janela (D15/D16). O rating é o que ficou depois da última
-- partida do time até a data de referência; entram só os times com partida na janela. Ranks: geral,
-- e por região × tier (os circuitos quase não se cruzam: compare dentro do mesmo grupo).
-- `is_provisional`: menos de `rating_provisional_series` séries na janela no tier atual do time (o
-- da última partida). Promovido da VCL chega ao VCT com poucas séries lá: o rating ainda assenta.

with elo as (

    select e.*, m.match_date, m.tier_level, m.is_in_analysis_window
    from {{ ref('fct_team_elo') }} e
    join {{ ref('fct_match') }} m using (match_id)
    where m.match_date <= {{ as_of_date() }}

),

latest as (

    select team_id, rating_after as rating, match_at as last_match_at, tier_level
    from elo
    qualify row_number() over (partition by team_id order by match_at desc, match_id desc) = 1

),

in_window as (

    select
        team_id,
        count(*)                        as matches_in_window,
        sum(result)                     as wins_in_window,
        max(rating_after)               as peak_rating_in_window,
        min(match_at)                   as first_match_in_window_at
    from elo
    where is_in_analysis_window
    group by team_id

),

in_window_by_tier as (

    select team_id, tier_level, count(*) as tier_matches_in_window
    from elo
    where is_in_analysis_window
    group by all

)

select
    l.team_id,
    t.team_name,
    t.team_tag,
    t.region,
    t.logo_url,
    l.tier_level,
    case l.tier_level when 1 then 'vct' else 'vcl' end           as tier,
    l.rating,
    w.peak_rating_in_window,
    w.matches_in_window,
    coalesce(wt.tier_matches_in_window, 0)                       as tier_matches_in_window,
    coalesce(wt.tier_matches_in_window, 0) < {{ var('rating_provisional_series') }}
                                                                 as is_provisional,
    w.wins_in_window,
    w.wins_in_window / w.matches_in_window                       as win_rate_in_window,
    l.last_match_at,
    rank() over (order by l.rating desc)                         as rank_overall,
    rank() over (partition by t.region, l.tier_level order by l.rating desc)
                                                                 as rank_in_region_tier
from latest l
join in_window w using (team_id)
join {{ ref('dim_team') }} t using (team_id)
left join in_window_by_tier wt
    on wt.team_id = l.team_id and wt.tier_level is not distinct from l.tier_level
where cast(l.last_match_at as date) >= {{ analysis_window_start() }}
