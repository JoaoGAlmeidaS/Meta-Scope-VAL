"""Pegadinha 2: o mesmo time aparece como id + nome, só nome e só tag.

A ponte por placar (`ingestion/bridge.py`) funciona na resposta básica, a única do histórico.
No fixture com `tabs=all`, ela é conferida contra a ponte posicional da economia.
"""

from __future__ import annotations

from collections import Counter

import pytest

from ingestion.bridge import BridgeError, name_keys, tag_to_team_id, tags_by_score, team_id_by_name

TABS_ALL = "match_bo5_2026_ot_tabs_all.json"


def test_ponte_por_placar_chega_aos_dois_ids(match_map):
    match, map_ = match_map
    bridge = tag_to_team_id(match, map_)
    assert len(bridge) == 2
    assert set(bridge.values()) == {t.id for t in match.teams}


def test_tags_dos_jogadores_sao_as_da_ponte(match_map):
    match, map_ = match_map
    tags = Counter(p.team_tag for p in map_.players)
    assert set(tags) == set(tag_to_team_id(match, map_))
    assert set(tags.values()) == {5}


def test_ponte_por_placar_concorda_com_posicional(load_match):
    match = load_match(TABS_ALL)
    for map_ in match.maps:
        positional = {e.name: t.id for e, t in zip(map_.economy.teams, match.teams, strict=True)}
        assert tag_to_team_id(match, map_) == positional, map_.name


def test_vencedor_da_economia_bate_com_rounds(load_match):
    for map_ in load_match(TABS_ALL).maps:
        tags = [t.name for t in map_.economy.teams]
        for rnd, eco in zip(map_.rounds, map_.economy.rounds, strict=True):
            assert rnd.number == eco.number
            winners = [tag for tag, t in zip(tags, eco.teams, strict=True) if t.winner]
            assert winners == [rnd.winner], f"{map_.name} round {rnd.number}"


# --- casos de borda da ponte ------------------------------------------------------------------


def _summit(load_match):
    # Summit da 734308: LOUD 13 × 1 100 Thieves.
    return next(m for m in load_match("match_bo5_2026_ot_basic.json").maps if m.name == "Summit")


def test_ponte_em_mapa_13_a_0_usa_tag_dos_jogadores(load_match):
    summit = _summit(load_match)
    shutout = summit.model_copy(
        update={
            "rounds": [r for r in summit.rounds if r.winner == "LOUD"],
            "teams": [
                t.model_copy(update={"score": 0}) if t.name == "100 Thieves" else t
                for t in summit.teams
            ],
        }
    )
    assert tags_by_score(shutout) == {"LOUD": "LOUD", "100T": "100 Thieves"}


def test_ponte_recusa_placar_que_nao_fecha(load_match):
    summit = _summit(load_match)
    wrong = summit.model_copy(
        update={
            "teams": [
                t.model_copy(update={"score": 2}) if t.name == "100 Thieves" else t
                for t in summit.teams
            ]
        }
    )
    with pytest.raises(BridgeError):
        tags_by_score(wrong)


# --- nome do time em mais de uma forma (pegadinha 35) -------------------------------------------

RAZAO_SOCIAL = "match_cn_legal_name_tabs_all.json"


def test_nome_com_razao_social_tem_as_tres_formas():
    assert name_keys("Wuxi Titan Esports Club (Titan Esports Club)") == {
        "wuxi titan esports club (titan esports club)",
        "wuxi titan esports club",
        "titan esports club",
    }
    assert name_keys("TYLOO") == {"tyloo"}


def test_mapa_com_nome_curto_casa_com_a_razao_social(load_json, load_match):
    # 701025 (VCT 2026 China Stage 2): partida com a razão social, mapa só com o nome curto.
    raw = load_json(RAZAO_SOCIAL)["data"]
    assert raw["teams"][1]["name"] == "Wuxi Titan Esports Club (Titan Esports Club)"
    assert raw["maps"][0]["teams"][1]["name"] == "Titan Esports Club"
    match = load_match(RAZAO_SOCIAL)
    titan = match.teams[1].id
    assert team_id_by_name(match, "Titan Esports Club") == titan
    assert team_id_by_name(match, "titan esports club") == titan
    assert team_id_by_name(match, "Outro Time") is None
    for map_ in match.maps:
        assert set(tag_to_team_id(match, map_).values()) == {t.id for t in match.teams}
