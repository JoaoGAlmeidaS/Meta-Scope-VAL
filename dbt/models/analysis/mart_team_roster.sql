-- D26: elenco de cada time na janela: quem jogou, quantos mapas, o agente mais usado e a última
-- aparição. O roster "atual" do site são os jogadores das partidas mais recentes.

with appearances as (

    select team_id, player_id, player_name, agent, map_id, match_at
    from {{ ref('fct_player_map') }}
    where is_in_analysis_window and not is_excluded and team_id is not null

),

main_agent as (

    select team_id, player_id, agent
    from appearances
    group by team_id, player_id, agent
    qualify row_number() over (partition by team_id, player_id order by count(*) desc, agent) = 1

)

select
    a.team_id,
    a.player_id,
    arg_max(a.player_name, a.match_at)                          as player_name,
    count(distinct a.map_id)                                    as maps_played,
    any_value(m.agent)                                          as main_agent,
    max(cast(a.match_at as date))                               as last_played_on
from appearances a
join main_agent m using (team_id, player_id)
group by a.team_id, a.player_id
