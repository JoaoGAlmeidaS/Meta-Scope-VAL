"""Features de time — D15/D16.

    * Elo ou Glicko-2, com decaimento temporal e ajuste por tier de evento (K tunado
      por backtest)
    * forma recente (janelas móveis, só com jogos anteriores)
    * head-to-head
    * força por mapa

Regra dura: nada aqui pode olhar para depois do `match_datetime` da linha. O teste
`dbt/tests/assert_no_future_leakage.sql` existe para tornar essa regra falseável.
"""

from __future__ import annotations

# TODO(D15): rating.
DEFAULT_ELO = 1500.0
K_BASE = 24.0  # tunar por backtest
TIER_MULTIPLIER = {"s": 1.0, "a": 0.85, "b": 0.7, "c": 0.55}


def elo_update(rating_a: float, rating_b: float, score_a: float, k: float = K_BASE):
    """Atualiza os ratings de um confronto. Devolve (novo_a, novo_b)."""
    raise NotImplementedError("D15")
