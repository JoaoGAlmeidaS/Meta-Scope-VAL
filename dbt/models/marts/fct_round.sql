-- Rounds, uma linha por (map_id, round_number) (D11), com o lado de cada time reconstruído.
--
-- A API só diz o lado de quem venceu (pegadinha 1). O perdedor está no outro lado, então cada
-- round já traz atacante e defensor — inclusive no overtime, em que os lados trocam a cada round.
-- A consistência com `roundsCt`/`roundsT` e a troca no intervalo são testadas no D13. Em mapa
-- sem histórico de lado (pegadinha 22), atacante e defensor ficam nulos; o vencedor não.
--
-- Economia orientada por lado. Pistol (rounds 1 e 13) vem da API como `eco` (pegadinha 4): aqui
-- ele vira `pistol`, e nenhuma métrica de eco o conta.

with rounds as (

    select * from {{ ref('stg_rounds') }}

),

maps as (

    select * from {{ ref('fct_map') }}

),

oriented as (

    select
        r.*,
        mp.event_id,
        mp.season,
        mp.match_at,
        mp.patch,
        mp.map_name,
        mp.is_excluded,
        mp.is_in_analysis_window,
        mp.has_round_sides,
        mp.team1_id,
        mp.team2_id,
        case r.winner_team_id
            when mp.team1_id then mp.team2_id
            when mp.team2_id then mp.team1_id
        end                                             as loser_team_id,
        r.round_number in (1, 13)                       as is_pistol
    from rounds r
    join maps mp using (map_id)

),

sided as (

    select
        *,
        case winner_side
            when 'attack' then winner_team_id
            when 'defense' then loser_team_id
        end                                             as attacker_team_id,
        case winner_side
            when 'defense' then winner_team_id
            when 'attack' then loser_team_id
        end                                             as defender_team_id
    from oriented

)

select
    map_id,
    match_id,
    event_id,
    season,
    match_at,
    patch,
    map_name,
    is_excluded,
    is_in_analysis_window,
    has_round_sides,
    round_number,
    case when round_number <= 12 then 1 when round_number <= 24 then 2 else 3 end
                                                        as half,
    round_number > 24                                   as is_overtime,
    is_pistol,
    winner_team_id,
    loser_team_id,
    winner_side,
    attacker_team_id,
    defender_team_id,
    win_method,
    case attacker_team_id when team1_id then team1_bank when team2_id then team2_bank end
                                                        as attacker_bank,
    case attacker_team_id when team1_id then team1_loadout when team2_id then team2_loadout end
                                                        as attacker_loadout,
    case
        when is_pistol then 'pistol'
        else case attacker_team_id when team1_id then team1_buy_type
                                   when team2_id then team2_buy_type end
    end                                                 as attacker_buy_type,
    case defender_team_id when team1_id then team1_bank when team2_id then team2_bank end
                                                        as defender_bank,
    case defender_team_id when team1_id then team1_loadout when team2_id then team2_loadout end
                                                        as defender_loadout,
    case
        when is_pistol then 'pistol'
        else case defender_team_id when team1_id then team1_buy_type
                                   when team2_id then team2_buy_type end
    end                                                 as defender_buy_type
from sided
