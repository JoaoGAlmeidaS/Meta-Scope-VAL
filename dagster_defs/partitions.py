"""Partições — D12.

A unidade natural do domínio é o **split/temporada**: é como o vlr.gg organiza o calendário
e é o que torna o backfill uma operação única, com retomada automática.
"""

from __future__ import annotations

# TODO(D12): StaticPartitionsDefinition ou DynamicPartitionsDefinition por split.
SPLITS_SEED = [
    "2022-s1",
    "2023-s1",
    "2024-s1",
    "2025-s1",
    "2026-s1",
]
