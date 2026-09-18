"""Coletores: HTML → dict → Parquet.

    * D5 — listagem de partidas, paginada por split/temporada (define a partição)
    * D6 — detalhe de partida: mapas, veto, placar, rounds, agentes por jogador
    * D8 — entidades de apoio: times, jogadores, eventos, rankings regionais

CLI:
    python -m ingestion.collectors --incremental
    python -m ingestion.collectors --backfill --since 2022
"""

from __future__ import annotations

import argparse

# TODO(D5/D6/D8): implementar os coletores e o writer de Parquet particionado.

PARTITION_KEY = "split"  # ex.: "2026-americas-stage1"


def collect_match_list(split: str) -> list[dict]:
    """Lista as partidas de um split. Paginado."""
    raise NotImplementedError("D5")


def collect_match_detail(match_id: str) -> dict:
    """Detalhe completo de uma partida, incluindo composição por mapa."""
    raise NotImplementedError("D6")


def write_parquet(rows: list[dict], dataset: str, split: str) -> None:
    """Grava as linhas no lake em Parquet, particionado por split."""
    raise NotImplementedError("D6")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incremental", action="store_true", help="só o split corrente")
    parser.add_argument("--backfill", action="store_true", help="histórico completo (local)")
    parser.add_argument("--since", type=int, default=2022)
    args = parser.parse_args()
    raise NotImplementedError(f"D5+: {args}")


if __name__ == "__main__":
    main()
