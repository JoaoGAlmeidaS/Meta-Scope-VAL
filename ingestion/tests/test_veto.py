"""Pegadinha 14: mapa não jogado some de `maps[]`, mas continua no veto."""

from __future__ import annotations

import pytest

BO5_WITH_VETO = [
    "match_bo5_2022_basic.json",
    "match_bo5_2026_ot_basic.json",
    "match_bo5_2026_ot_tabs_all.json",
]


def _remains(match) -> str:
    (step,) = (s for s in match.picks_bans.steps if s.action == "remains")
    assert step.team is None
    return step.map


def test_bo3_2x0_decisivo_ausente_de_maps(load_match):
    match = load_match("match_bo3_2x0_basic.json")
    assert len(match.maps) == 2
    assert _remains(match) not in {m.name for m in match.maps}


@pytest.mark.parametrize("name", BO5_WITH_VETO)
def test_bo5_decisivo_jogado_sem_picked_by(load_match, name):
    match = load_match(name)
    maps = {m.name: m for m in match.maps}
    decider = _remains(match)
    assert decider in maps
    assert maps[decider].picked_by is None


def test_veto_pode_vir_vazio(load_match):
    # 707490 (Challengers Brasil): sem veto no vlr.gg e `pickedBy` nulo em todo mapa.
    match = load_match("match_vcl_brasil_basic.json")
    assert match.picks_bans.steps == []
    assert all(m.picked_by is None for m in match.maps)
