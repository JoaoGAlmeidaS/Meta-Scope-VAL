"""Partições — D12.

A unidade é a **temporada** (`season`), a mesma chave Hive do lake (`ingestion/lake.py`): é como o
calendário do VCT se organiza e é o que torna o backfill uma operação única, com retomada
automática. Split como partição física foi descartado no D5: os nomes de split da VCL não têm
padrão.
"""

from __future__ import annotations

# TODO(D12): StaticPartitionsDefinition por temporada.
SEASONS = ["2023", "2024", "2025", "2026"]
