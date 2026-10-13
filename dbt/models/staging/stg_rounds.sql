-- Rounds, uma linha por (map_id, round_number). `winner_side` é o lado de quem venceu
-- (pegadinha 1), padronizado para attack/defense; nulo, com o método, em mapa sem histórico de
-- lado (pegadinha 22). A economia vem nula sem `tabs=all`.
-- O tipo de compra fica como a API manda: pistol ainda aparece como `eco` aqui (pegadinha 4);
-- a correção é do fct_round.

with source as (

    select * from {{ source('lake', 'raw_round') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (partition by map_id, round_number order by season desc) = 1

)

select
    cast(match_id as varchar)                                       as match_id,
    cast(map_id as varchar)                                         as map_id,
    cast(round_number as integer)                                   as round_number,
    nullif(cast(winner_tag as varchar), '')                         as winner_tag,  -- pegadinha 40
    cast(winner_team_id as varchar)                                 as winner_team_id,
    case winner_side when 'ct' then 'defense' when 't' then 'attack' end
                                                                    as winner_side,
    case method
        when 'elim' then 'elimination'
        when 'boom' then 'detonation'
        when 'defuse' then 'defuse'
        when 'time' then 'time'
    end                                                             as win_method,
    cast(team1_bank as integer)                                     as team1_bank,
    cast(team1_loadout as integer)                                  as team1_loadout,
    cast(team1_buy as varchar)                                      as team1_buy_type,
    cast(team2_bank as integer)                                     as team2_bank,
    cast(team2_loadout as integer)                                  as team2_loadout,
    cast(team2_buy as varchar)                                      as team2_buy_type

from deduped
