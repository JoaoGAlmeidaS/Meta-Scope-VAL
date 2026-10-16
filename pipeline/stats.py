"""Estatística das análises (D17–D21), compartilhada pelos notebooks e pelo site.

Regra do projeto: todo número publicado leva intervalo de confiança, e inconclusivo é resultado
válido. Os marts de análise (dbt/models/analysis) entregam as contagens no grão fino; aqui saem as
estimativas, os ICs e as correções. Notebook e site chamam as mesmas funções, então mostram os
mesmos números.

    wilson                  IC de uma proporção (Wilson), para contagens independentes
    cluster_bootstrap_rate  razão de somas com bootstrap por cluster (rounds do mesmo mapa não são
                            independentes: reamostra mapas, não rounds)
    mean_bootstrap          média com IC por bootstrap (ex.: resultado − esperado pelo Elo)
    adjust                  correção para múltiplas comparações (Holm por padrão)
    pistol_effect           regressão logística vitória no mapa ~ pistols + diferença de Elo
    shrink                  shrinkage empírico (normal–normal) de um desempenho acima do esperado
    calibration             log loss, Brier e curva de calibração com IC
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as st

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Estimate:
    value: float
    low: float
    high: float
    n: int

    def excludes(self, x: float) -> bool:
        """O IC exclui `x`? (ex.: 0,5 para "existe vantagem de lado")."""
        return self.low > x or self.high < x

    def text(self, digits: int = 3, percent: bool = False) -> str:
        """'0,511 (IC 95% 0,508–0,515)'; com `percent`, '51,1% (IC 95% 50,8%–51,5%)'.

        Com limite negativo, o separador vira " a ": '-0,287 (IC 95% -0,412 a -0,129)'.
        """
        scale, places, unit = (100, max(digits - 2, 0), "%") if percent else (1, digits, "")

        def show(x: float) -> str:
            return fmt(x * scale, places) + unit

        sep = " a " if self.low < 0 else "–"  # "-0,41–-0,13" ficaria ilegível
        return f"{show(self.value)} (IC 95% {show(self.low)}{sep}{show(self.high)})"

    def as_dict(self, digits: int = 6) -> dict:
        return {
            "value": round(self.value, digits),
            "low": round(self.low, digits),
            "high": round(self.high, digits),
            "n": self.n,
        }


def fmt(x: float, digits: int = 3) -> str:
    """Número com vírgula decimal, para o texto dos notebooks e do site."""
    return f"{x:.{digits}f}".replace(".", ",")


def wilson(successes: float, n: int, z: float = Z95) -> Estimate:
    """IC de Wilson para uma proporção."""
    if n == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return Estimate(p, max(0.0, center - half), min(1.0, center + half), n)


def cluster_bootstrap_rate(
    successes: Sequence[float],
    totals: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 7,
    alpha: float = 0.05,
) -> Estimate:
    """Razão sum(successes) / sum(totals) com IC percentil por bootstrap de clusters.

    Cada posição é um cluster (um mapa): reamostrar mapas preserva a correlação entre os rounds
    de um mesmo mapa, que o Wilson sobre rounds ignoraria (IC estreito demais).
    """
    s = np.asarray(successes, dtype=float)
    t = np.asarray(totals, dtype=float)
    if len(s) == 0 or t.sum() == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    boots = s[idx].sum(axis=1) / t[idx].sum(axis=1)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return Estimate(float(s.sum() / t.sum()), float(lo), float(hi), len(s))


def mean_bootstrap(
    values: Sequence[float], *, n_boot: int = 2000, seed: int = 7, alpha: float = 0.05
) -> Estimate:
    """Média com IC percentil por bootstrap."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    rng = np.random.default_rng(seed)
    boots = v[rng.integers(0, len(v), size=(n_boot, len(v)))].mean(axis=1)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return Estimate(float(v.mean()), float(lo), float(hi), len(v))


def two_sided_p(est: Estimate, null: float) -> float:
    """p-valor aproximado a partir do IC 95% (erro-padrão = largura / (2 × 1,96))."""
    se = (est.high - est.low) / (2 * Z95)
    if not se or math.isnan(se):
        return float("nan")
    return float(2 * st.norm.sf(abs(est.value - null) / se))


def adjust(pvalues: Sequence[float], method: str = "holm") -> list[float]:
    """p-valores corrigidos para múltiplas comparações (Holm por padrão)."""
    from statsmodels.stats.multitest import multipletests

    p = np.asarray(pvalues, dtype=float)
    ok = ~np.isnan(p)
    out = np.full_like(p, np.nan)
    if ok.any():
        out[ok] = multipletests(p[ok], method=method)[1]
    return out.tolist()


def pistol_effect(
    pistols_won: Sequence[int], won_map: Sequence[bool], rating_diff: Sequence[float]
):
    """Regressão logística vitória no mapa ~ C(pistols vencidos) + diferença de Elo / 100.

    Uma linha por mapa (do ponto de vista de um dos times: as duas linhas de um mapa são espelho).
    Devolve a probabilidade prevista de vencer o mapa com 0, 1 e 2 pistols para times de mesmo
    Elo, com IC 95%, e a razão de chances de cada pistol a mais.
    """
    import pandas as pd
    import statsmodels.formula.api as smf

    df = pd.DataFrame(
        {
            "won": np.asarray(won_map, dtype=float),
            "pistols": np.asarray(pistols_won, dtype=int),
            "diff": np.asarray(rating_diff, dtype=float) / 100.0,
        }
    )
    fit = smf.logit("won ~ C(pistols) + diff", data=df).fit(disp=False)
    grid = pd.DataFrame({"pistols": [0, 1, 2], "diff": [0.0, 0.0, 0.0]})
    pred = fit.get_prediction(grid).summary_frame(alpha=0.05)
    probs = {
        int(k): Estimate(float(r["predicted"]), float(r["ci_lower"]), float(r["ci_upper"]), len(df))
        for k, (_, r) in zip(grid["pistols"], pred.iterrows(), strict=True)
    }
    conf = fit.conf_int()
    odds = {
        name: Estimate(
            float(np.exp(fit.params[name])),
            float(np.exp(conf.loc[name, 0])),
            float(np.exp(conf.loc[name, 1])),
            len(df),
        )
        for name in fit.params.index
        if name != "Intercept"
    }
    return {"probabilities": probs, "odds_ratios": odds, "n_maps": len(df)}


def shrink(excess: Sequence[float], n: Sequence[int], *, sigma2: float = 0.25) -> list[Estimate]:
    """Shrinkage empírico normal–normal de um desempenho acima do esperado.

    `excess` é, por grupo (ex.: composição × mapa), a média de (resultado − esperado pelo Elo) e
    `n` o número de observações. A variância verdadeira entre grupos (tau²) sai por método dos
    momentos; cada grupo é puxado para zero na proporção da sua incerteza (grupo com poucos jogos
    quase não se mexe do zero). `sigma2` é a variância de um resultado binário (0,25 no máximo).
    """
    x = np.asarray(excess, dtype=float)
    m = np.asarray(n, dtype=float)
    if len(x) == 0:
        return []
    sampling = sigma2 / m
    tau2 = max(float(np.average(x**2, weights=m) - np.average(sampling, weights=m)), 1e-6)
    weight = tau2 / (tau2 + sampling)
    post_mean = weight * x
    post_sd = np.sqrt(weight * sampling)
    return [
        Estimate(float(mu), float(mu - Z95 * sd), float(mu + Z95 * sd), int(k))
        for mu, sd, k in zip(post_mean, post_sd, m, strict=True)
    ]


def calibration(
    probabilities: Sequence[float],
    outcomes: Sequence[float],
    *,
    bins: int = 10,
    n_boot: int = 2000,
    seed: int = 7,
) -> dict:
    """Log loss e Brier com IC por bootstrap, e a curva de calibração por faixa de probabilidade.

    Resultado fracionário (empate 0,5) entra como meio acerto. Cada faixa da curva traz a
    probabilidade média prevista e a frequência observada com IC de Wilson.
    """
    p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
    y = np.asarray(outcomes, dtype=float)
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    brier = (p - y) ** 2
    curve = []
    edges = np.linspace(0, 1, bins + 1)
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        k = int(mask.sum())
        if k == 0:
            continue
        obs = wilson(float(y[mask].sum()), k)
        curve.append({"predicted": float(p[mask].mean()), "observed": obs.as_dict(), "n": k})
    return {
        "log_loss": mean_bootstrap(ll, n_boot=n_boot, seed=seed),
        "brier": mean_bootstrap(brier, n_boot=n_boot, seed=seed),
        "coin_log_loss": math.log(2),
        "coin_brier": 0.25,
        "curve": curve,
        "n": len(p),
    }
