"""Estatística compartilhada por notebooks e site: ICs, bootstrap, correção, shrinkage."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pipeline.stats import (
    Estimate,
    adjust,
    calibration,
    cluster_bootstrap_rate,
    mean_bootstrap,
    pistol_effect,
    shrink,
    two_sided_p,
    wilson,
)


def test_wilson_contem_a_proporcao_e_fica_em_0_1():
    est = wilson(7, 10)
    assert est.value == pytest.approx(0.7)
    assert 0 <= est.low < 0.7 < est.high <= 1
    assert wilson(0, 10).low == 0.0


def test_bootstrap_por_cluster_e_mais_largo_que_wilson_com_correlacao():
    # 40 mapas de 20 rounds, metade "todo ataque" e metade "toda defesa": correlação total dentro
    # do mapa. O Wilson sobre 800 rounds finge independência; o bootstrap por mapa não.
    succ = [20] * 20 + [0] * 20
    tot = [20] * 40
    boot = cluster_bootstrap_rate(succ, tot)
    w = wilson(sum(succ), sum(tot))
    assert boot.value == pytest.approx(0.5)
    assert (boot.high - boot.low) > 3 * (w.high - w.low)


def test_media_por_bootstrap_e_deterministica():
    a = mean_bootstrap([1, 0, 1, 1, 0])
    assert a == mean_bootstrap([1, 0, 1, 1, 0])
    assert a.value == pytest.approx(0.6)


def test_holm_nunca_diminui_p_valor():
    raw = [0.01, 0.04, 0.03, float("nan")]
    adj = adjust(raw)
    assert all(a >= r for a, r in zip(adj[:3], raw[:3], strict=True))
    assert math.isnan(adj[3])


def test_p_valor_pelo_ic():
    est = wilson(600, 1000)
    assert two_sided_p(est, 0.5) < 0.001
    assert two_sided_p(wilson(500, 1000), 0.5) > 0.9


def test_pistol_efeito_aumenta_com_pistols():
    rng = np.random.default_rng(0)
    n = 3000
    pistols = rng.integers(0, 3, n)
    diff = rng.normal(0, 100, n)
    logit = -1.0 + 1.0 * pistols + diff / 200
    won = rng.random(n) < 1 / (1 + np.exp(-logit))
    out = pistol_effect(pistols, won, diff)
    p = out["probabilities"]
    assert p[0].value < p[1].value < p[2].value
    assert out["n_maps"] == n


def test_shrinkage_puxa_mais_quem_tem_menos_jogos():
    small, big = shrink([0.3, 0.3, 0.0, -0.1], [3, 300, 50, 80])[:2]
    assert abs(small.value) < abs(big.value) <= 0.3
    assert (small.high - small.low) > (big.high - big.low)


def test_calibracao_perfeita_tem_curva_na_diagonal():
    rng = np.random.default_rng(1)
    p = rng.random(5000)
    y = (rng.random(5000) < p).astype(float)
    out = calibration(p, y)
    assert out["log_loss"].value < out["coin_log_loss"]
    for b in out["curve"]:
        assert b["observed"]["low"] - 0.05 <= b["predicted"] <= b["observed"]["high"] + 0.05


def test_texto_do_intervalo_usa_virgula_decimal():
    est = Estimate(0.5113, 0.5078, 0.5152, 100)
    assert est.text() == "0,511 (IC 95% 0,508–0,515)"
    assert est.text(percent=True) == "51,1% (IC 95% 50,8%–51,5%)"
    assert Estimate(-0.287, -0.412, -0.129, 23).text() == "-0,287 (IC 95% -0,412 a -0,129)"
