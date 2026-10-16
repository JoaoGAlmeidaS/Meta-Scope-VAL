-- Agentes que aparecem nas partidas, uma linha por agente (nome minúsculo desde o contrato). Sai
-- de `raw_player_map`, como as outras dimensões. O ícone é o mais recente que o vlr.gg mandou
-- (`players[].agents[].img`); o site o usa, com override manual em web/assets/imgs/agentsV/.

with picks as (

    select pm.agent, pm.agent_img, m.match_at, pm.match_id
    from {{ ref('stg_player_maps') }} pm
    join {{ ref('stg_matches') }} m using (match_id)

),

latest_image as (

    select agent, agent_img as image_url
    from picks
    where agent_img is not null
    qualify row_number() over (partition by agent order by match_at desc, match_id desc) = 1

)

select
    p.agent,
    i.image_url,
    count(*)            as player_maps,
    min(p.match_at)     as first_played_at,
    max(p.match_at)     as last_played_at
from picks p
left join latest_image i using (agent)
group by p.agent, i.image_url
