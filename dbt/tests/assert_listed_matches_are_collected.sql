-- D13: completude da coleta. Em todo evento que já passou pelo backfill, cada partida concluída
-- da listagem está gravada ou rejeitada com motivo. Evento ainda não coletado não entra: o
-- backfill anda do mais recente para o mais antigo, e o lake fica parcial por dias.
-- Rejeição `unavailable` conta como pendente (a próxima coleta tenta de novo), não como falta.

select event_id, listed_matches, collected_matches, rejected_matches, missing_matches
from {{ ref('int_event_completeness') }}
where has_details
  and missing_matches > 0
