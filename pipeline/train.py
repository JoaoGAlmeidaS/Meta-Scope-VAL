"""Treino e calibração — D19/D20/D21.

Protocolo (D19):
    * split **temporal**: treino ≤ 2024, validação 2025, teste 2026 — nunca aleatório
    * baseline: Elo puro
    * métricas: log loss, Brier score, curva de calibração (acurácia não conta sozinha)

Modelo (D20): regressão logística e LightGBM, calibrados com isotonic/Platt.
Se não bater o baseline, isso vira uma seção honesta do README — não um problema a esconder.

Predições (D21): todos os confrontos par a par (~150 times → ~11 mil), gravados
particionados por time para o front fazer lookup.
"""

from __future__ import annotations

TRAIN_END = "2024-12-31"
VALID_END = "2025-12-31"

# TODO(D19): carregar mart_match_features, montar o split temporal, rodar o baseline.


def main() -> None:
    raise NotImplementedError("D19")


if __name__ == "__main__":
    main()
