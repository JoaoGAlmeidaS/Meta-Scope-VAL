{#
  Janela de análise (D10). Regra inviolável: nenhum model escreve a janela à mão; todos passam
  por estas macros, que leem `analysis_window_months` e `elo_warmup_months` do dbt_project.yml.

  `as_of_date()`: var `as_of_date`, senão a env `AS_OF_DATE`, senão hoje (UTC, pelo perfil).
#}

{% macro as_of_date() -%}
  {%- set value = var('as_of_date', none) or env_var('AS_OF_DATE', '') -%}
  {%- if value -%} date '{{ value }}' {%- else -%} current_date {%- endif -%}
{%- endmacro %}

{% macro analysis_window_start() -%}
  cast({{ as_of_date() }} - interval {{ var('analysis_window_months') }} month as date)
{%- endmacro %}

{% macro elo_warmup_start() -%}
  cast({{ as_of_date() }}
       - interval {{ var('analysis_window_months') + var('elo_warmup_months') }} month as date)
{%- endmacro %}
