"""Partições — D12.

A unidade é a **temporada** (`season`), a mesma chave Hive do lake (`ingestion/lake.py`): é como o
calendário do VCT se organiza e é o que torna o backfill uma operação única, com retomada
automática. Split como partição física foi descartado no D5: os nomes de split da VCL não têm
padrão.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dagster import StaticPartitionsDefinition

from ingestion.config import HISTORY_SINCE

# Da primeira temporada coletada até a corrente: a partição do ano novo aparece sozinha.
SEASONS = [str(year) for year in range(HISTORY_SINCE, datetime.now(UTC).year + 1)]
season_partitions = StaticPartitionsDefinition(SEASONS)
