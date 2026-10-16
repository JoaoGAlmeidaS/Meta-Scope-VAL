"""Rating Elo dos times — D15.

Elo clássico sobre o resultado da **série** (vitória 1, empate 0,5 no formato "2 maps", derrota 0),
percorrido em ordem temporal. Cada linha de saída carrega o rating **antes** da partida: é o único
que pode ser usado para prever ou avaliar aquela partida (regra do projeto: Elo sempre pré-partida;
`dbt/tests/assert_no_future_leakage.sql` testa o encadeamento).

Ajustes, todos parâmetros de `EloParams`:
    * rating inicial pelo tier do primeiro evento do time: VCT começa acima da VCL (prior; os
      dois circuitos quase não se cruzam, e o Elo não teria como descobrir a diferença sozinho);
    * K multiplicável pelo tier do evento (na busca, peso igual nos dois tiers foi o melhor);
    * regressão parcial ao rating inicial na virada de temporada (elencos mudam no off-season);
    * reancoragem na promoção: no primeiro jogo de VCT de um time que começou na VCL, só uma
      fração do desvio dele ao rating inicial da VCL entra no VCT. A VCL é um pool quase fechado,
      e dominar a VCL infla o rating sem referência ao VCT: em 2026 os melhores da VCL de cada
      região foram para o Stage 2, e a Enterprise chegou com 1876 (acima de todo time do VCT)
      depois de 39–4 na VCL. O ajuste é pré-partida e só usa o passado, como a regressão de
      temporada, e vale uma vez por time. Rebaixamento (VCT → VCL) não tem regra: ainda sem caso.

Os valores padrão saíram de uma busca em grade pela log loss das probabilidades pré-partida, em
ordem temporal (`notebooks/06_rating.ipynb`): avaliação sequencial, não treino de modelo. Em
5.780 partidas (2025–2026, revisto em 16/10): K = 48, VCT começa 300 pontos acima da VCL, 75% do
desvio atravessa a temporada e 10% do desvio da VCL atravessa a promoção; log loss 0,6630 contra
0,6931 da moeda (0,6635 sem a reancoragem, com o gap de 200 de antes). A superfície é plana em
volta do ótimo: a reancoragem entre 0 e 20% dá o mesmo resultado na terceira casa.

Função pura sobre dicionários: o dbt chama pelo Python model `fct_team_elo`, e o pytest testa
direto.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EloParams:
    k: float = 48.0
    k_by_tier: Mapping[int, float] = field(default_factory=lambda: {1: 1.0, 2: 1.0})
    initial_by_tier: Mapping[int, float] = field(default_factory=lambda: {1: 1650.0, 2: 1350.0})
    season_carry: float = 0.75  # fração do desvio ao rating inicial que atravessa a temporada
    # fração do desvio ao rating inicial da VCL que atravessa a promoção ao VCT; None desliga
    promotion_carry: float | None = 0.1
    scale: float = 400.0


def expected(rating: float, opponent: float, scale: float = 400.0) -> float:
    """Probabilidade de vitória pela fórmula do Elo."""
    return 1.0 / (1.0 + 10.0 ** ((opponent - rating) / scale))


def run_elo(matches: Iterable[Mapping], params: EloParams | None = None) -> list[dict]:
    """Percorre as partidas em ordem e devolve duas linhas por partida, uma por time.

    Cada partida precisa de `match_id`, `match_at`, `season`, `tier_level`, `team1_id`,
    `team2_id` e `team1_result` (1, 0,5 ou 0). A ordem de entrada é ignorada: as partidas são
    ordenadas por (`match_at`, `match_id`), e empate de horário fica determinístico. A linha do
    primeiro jogo de VCT de um time vindo da VCL sai com `is_promotion` (o `rating_before` dela já
    é o reancorado).
    """
    p = params or EloParams()
    ordered = sorted(matches, key=lambda m: (m["match_at"], str(m["match_id"])))
    rating: dict[str, float] = {}
    anchor: dict[str, float] = {}
    pool: dict[str, int] = {}  # tier do rating inicial (âncora) do time: 1 VCT, 2 VCL
    season_of: dict[str, int] = {}
    rows: list[dict] = []

    for m in ordered:
        tier = int(m["tier_level"]) if m["tier_level"] is not None else 2
        season = int(m["season"])
        promoted = set()
        sides = ((m["team1_id"], m["team2_id"]), (m["team2_id"], m["team1_id"]))
        for team, _ in sides:
            if team not in rating:
                pool[team] = tier if tier in p.initial_by_tier else 2
                anchor[team] = p.initial_by_tier[pool[team]]
                rating[team] = anchor[team]
                season_of[team] = season
            elif season_of[team] != season:
                rating[team] = anchor[team] + p.season_carry * (rating[team] - anchor[team])
                season_of[team] = season
            if p.promotion_carry is not None and tier == 1 and pool[team] == 2:
                rating[team] = p.initial_by_tier[1] + p.promotion_carry * (
                    rating[team] - p.initial_by_tier[2]
                )
                anchor[team] = p.initial_by_tier[1]
                pool[team] = 1
                promoted.add(team)

        r1, r2 = rating[m["team1_id"]], rating[m["team2_id"]]
        e1 = expected(r1, r2, p.scale)
        s1 = float(m["team1_result"])
        k = p.k * p.k_by_tier.get(tier, 1.0)
        delta = k * (s1 - e1)
        rating[m["team1_id"]] = r1 + delta
        rating[m["team2_id"]] = r2 - delta

        for team, opp, before, opp_before, exp, result, after in (
            (m["team1_id"], m["team2_id"], r1, r2, e1, s1, r1 + delta),
            (m["team2_id"], m["team1_id"], r2, r1, 1.0 - e1, 1.0 - s1, r2 - delta),
        ):
            rows.append(
                {
                    "match_id": str(m["match_id"]),
                    "match_at": m["match_at"],
                    "season": season,
                    "team_id": team,
                    "opponent_id": opp,
                    "rating_before": before,
                    "opponent_rating_before": opp_before,
                    "expected_result": exp,
                    "result": result,
                    "rating_after": after,
                    "k": k,
                    "is_promotion": team in promoted,
                }
            )
    return rows


def log_loss(rows: Iterable[Mapping], eps: float = 1e-12) -> float:
    """Log loss das probabilidades pré-partida (uma linha por partida: a do time 1).

    Empate (0,5) entra como meio acerto de cada lado, o que é a log loss de um resultado
    fracionário.
    """
    total, n = 0.0, 0
    for r in rows:
        p = min(max(r["expected_result"], eps), 1 - eps)
        y = r["result"]
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
        n += 1
    return total / n if n else float("nan")
