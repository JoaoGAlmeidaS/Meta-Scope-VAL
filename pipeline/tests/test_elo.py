"""D15: Elo pré-partida, conservação, empate, tier e temporada."""

from __future__ import annotations

from datetime import datetime

import pytest

from pipeline.elo import EloParams, expected, log_loss, run_elo


def _m(i, t1, t2, result, *, tier=1, season=2025, day=None):
    return {
        "match_id": str(i),
        "match_at": datetime(season, 1, day or i),
        "season": season,
        "tier_level": tier,
        "team1_id": t1,
        "team2_id": t2,
        "team1_result": result,
    }


def test_esperado_e_simetrico_e_meio_entre_iguais():
    assert expected(1500, 1500) == pytest.approx(0.5)
    assert expected(1600, 1400) + expected(1400, 1600) == pytest.approx(1.0)
    assert expected(1900, 1500) == pytest.approx(10 / 11)


def test_soma_dos_ratings_se_conserva_na_partida():
    rows = run_elo([_m(1, "a", "b", 1.0), _m(2, "b", "a", 1.0)])
    for i in range(0, len(rows), 2):
        a, b = rows[i], rows[i + 1]
        assert a["rating_before"] + b["rating_before"] == pytest.approx(
            a["rating_after"] + b["rating_after"]
        )


def test_rating_antes_da_partida_e_o_depois_da_anterior():
    rows = run_elo([_m(1, "a", "b", 1.0), _m(2, "a", "c", 0.0), _m(3, "b", "a", 0.5)])
    by_team: dict[str, list[dict]] = {}
    for r in rows:
        by_team.setdefault(r["team_id"], []).append(r)
    for history in by_team.values():
        for prev, cur in zip(history, history[1:], strict=False):
            assert cur["rating_before"] == pytest.approx(prev["rating_after"])


def test_ordem_de_entrada_nao_importa():
    ms = [_m(1, "a", "b", 1.0), _m(2, "b", "c", 0.0), _m(3, "c", "a", 1.0)]
    assert run_elo(ms) == run_elo(list(reversed(ms)))


def test_empate_entre_iguais_nao_mexe_e_vale_meio():
    a, b = run_elo([_m(1, "a", "b", 0.5)])
    assert (a["result"], b["result"]) == (0.5, 0.5)
    assert a["rating_after"] == pytest.approx(a["rating_before"])


def test_tier_define_rating_inicial_e_peso():
    p = EloParams()
    (vct, _), (vcl, _) = (
        run_elo([_m(1, "a", "b", 1.0, tier=1)], p),
        run_elo([_m(1, "c", "d", 1.0, tier=2)], p),
    )
    assert vct["rating_before"] == p.initial_by_tier[1]
    assert vcl["rating_before"] == p.initial_by_tier[2]
    assert vcl["k"] == pytest.approx(p.k * p.k_by_tier[2])


def test_virada_de_temporada_regride_ao_rating_inicial():
    p = EloParams(season_carry=0.5)
    rows = run_elo([_m(1, "a", "b", 1.0, season=2025), _m(2, "a", "b", 1.0, season=2026)], p)
    first_after = rows[0]["rating_after"]
    second_before = rows[2]["rating_before"]
    anchor = p.initial_by_tier[1]
    assert second_before == pytest.approx(anchor + 0.5 * (first_after - anchor))


def test_log_loss_de_moeda_e_ln2():
    rows = [{"expected_result": 0.5, "result": 1.0}, {"expected_result": 0.5, "result": 0.0}]
    assert log_loss(rows) == pytest.approx(0.6931, abs=1e-3)


# --- promoção VCL → VCT ---------------------------------------------------------------------------


def _promovido(params):
    """'a' começa na VCL e vence duas vezes; depois estreia no VCT contra 'v', que é do VCT."""
    return run_elo(
        [
            _m(1, "a", "b", 1.0, tier=2),
            _m(2, "a", "b", 1.0, tier=2),
            _m(3, "v", "w", 1.0, tier=1),
            _m(4, "a", "v", 0.0, tier=1),
            _m(5, "a", "w", 1.0, tier=1),
        ],
        params,
    )


def test_promocao_reancora_o_desvio_da_vcl():
    p = EloParams(promotion_carry=0.25)
    rows = _promovido(p)
    by = {(r["match_id"], r["team_id"]): r for r in rows}
    before_vct = by[("2", "a")]["rating_after"]
    debut = by[("4", "a")]
    expected_rating = p.initial_by_tier[1] + 0.25 * (before_vct - p.initial_by_tier[2])
    assert debut["rating_before"] == pytest.approx(expected_rating)
    assert debut["is_promotion"]
    # o adversário do VCT não é mexido pela reancoragem
    assert by[("4", "v")]["rating_before"] == pytest.approx(by[("3", "v")]["rating_after"])
    assert not by[("4", "v")]["is_promotion"]


def test_promocao_acontece_uma_vez():
    rows = _promovido(EloParams(promotion_carry=0.25))
    by = {(r["match_id"], r["team_id"]): r for r in rows}
    assert [r["match_id"] for r in rows if r["is_promotion"]] == ["4"]
    # no segundo jogo de VCT, o rating segue o encadeamento normal
    assert by[("5", "a")]["rating_before"] == pytest.approx(by[("4", "a")]["rating_after"])


def test_sem_reancoragem_o_rating_atravessa_inteiro():
    rows = _promovido(EloParams(promotion_carry=None))
    by = {(r["match_id"], r["team_id"]): r for r in rows}
    assert by[("4", "a")]["rating_before"] == pytest.approx(by[("2", "a")]["rating_after"])
    assert not any(r["is_promotion"] for r in rows)


def test_time_que_comeca_no_vct_nunca_e_promovido():
    rows = run_elo([_m(1, "a", "b", 1.0, tier=2), _m(2, "v", "b", 1.0, tier=1)])
    assert [r["team_id"] for r in rows if r["is_promotion"]] == ["b"]
