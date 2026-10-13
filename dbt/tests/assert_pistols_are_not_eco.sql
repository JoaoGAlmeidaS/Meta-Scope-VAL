-- D13: pistol (rounds 1 e 13) nunca entra como eco (pegadinha 4), e só pistol é `pistol`.
-- A API classifica o pistol como `eco`; o fct_round corrige, e este teste impede a regressão.

select map_id, round_number, attacker_buy_type, defender_buy_type
from {{ ref('fct_round') }}
where (is_pistol and has_round_sides and attacker_team_id is not null
       and (attacker_buy_type <> 'pistol' or defender_buy_type <> 'pistol'))
   or (not is_pistol and (attacker_buy_type = 'pistol' or defender_buy_type = 'pistol'))
