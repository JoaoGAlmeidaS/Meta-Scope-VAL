"""Pegadinha 2: o mesmo time aparece como id + nome, só nome e só tag.

A ponte por placar (`ingestion/bridge.py`) funciona na resposta básica, a única do histórico.
No fixture com `tabs=all`, ela é conferida contra a ponte posicional da economia.
"""

from __future__ import annotations

from collections import Counter

import pytest

from ingestion.bridge import BridgeError, tag_to_team_id, tags_by_score

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
