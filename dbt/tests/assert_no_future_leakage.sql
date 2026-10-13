-- D16 — teste anti-vazamento.
-- Falha se qualquer feature de mart_match_features usar dado posterior ao match_datetime.
-- Contrato: toda feature carrega `feature_computed_through`, o instante mais recente
-- observado na sua construcao.

-- Desligado até o D16: o mart ainda não existe e o `dbt build` do D14 roda o projeto inteiro.
{{ config(severity = 'error', enabled = false) }}

select
    match_id,
    match_datetime,
    feature_computed_through
from {{ ref('mart_match_features') }}
where feature_computed_through >= match_datetime
