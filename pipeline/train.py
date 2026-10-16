"""Modelo treinado — depois do D30 (seção 9 do documento mestre). Nada aqui roda no build.

Nos 30 dias a previsão é a fórmula do Elo (`pipeline/elo.py`, calibração em
`notebooks/07_previsao_calibracao.ipynb`). O modelo treinado entra só se bater esse baseline.

Protocolo combinado para quando entrar:
    * split temporal dentro do histórico coletado (2025+): treino, validação e teste em blocos
      consecutivos, nunca aleatório; o teste é o fim da janela de análise;
    * features estritamente pré-partida, do warehouse: Elo antes da partida (`fct_team_elo`),
      forma recente, mapa e lado (`mart_side_by_map`), pistol, região do time na época;
    * baseline: a probabilidade do Elo de `mart_elo_calibration` (log loss 0,661 na janela de
      out/2025 a out/2026, contra 0,693 da moeda);
    * modelos: regressão logística e LightGBM (já nas dependências), calibrados (isotônica
      ou Platt);
    * métrica: log loss, Brier e curva de calibração; acurácia não conta sozinha;
    * se não bater o baseline, vira uma seção honesta do README, não um problema a esconder.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("pós-D30: a previsão nos 30 dias é o Elo (pipeline/elo.py)")


if __name__ == "__main__":
    main()
