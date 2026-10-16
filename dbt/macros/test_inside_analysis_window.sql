{#
  D16: teste genérico dos marts de análise. Falha em qualquer linha cuja data esteja fora da janela
  (`analysis_window_start()` até `as_of_date()`). Todo `mart_*` usa, menos o de drift, que lê o
  histórico inteiro de propósito (D17).
#}

{% test inside_analysis_window(model, column_name) %}

select *
from {{ model }}
where cast({{ column_name }} as date) < {{ analysis_window_start() }}
   or cast({{ column_name }} as date) > {{ as_of_date() }}

{% endtest %}
