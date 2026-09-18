-- D16 — teste anti-vazamento.
-- Falha se qualquer feature de mart_match_features usar dado posterior ao match_datetime.
-- Contrato: toda feature carrega `feature_computed_through`, o instante mais recente
-- observado na sua construcao.

{{ config(severity = 'error') }}

select
    match_id,
    match_datetime,
    feature_computed_through
from {{ ref('mart_match_features') }}
where feature_computed_through >= match_datetime
