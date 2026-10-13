"""Pegadinha 1: `rounds[].side` é o lado de quem venceu o round.

É o que permite reconstruir o lado de cada time em cada round. Overtime (rounds 25+):
`roundsCt`/`roundsT` contam só o tempo regulamentar; `score` inclui o overtime.
"""

from __future__ import annotations

import pytest

from ingestion.bridge import tags_by_score

REGULATION = 24
HALVES = {"1º tempo": range(1, 13), "2º tempo": range(13, REGULATION + 1)}

OVERTIME_MAPS = [
    ("match_bo5_2026_ot_basic.json", "Ascent"),
    ("match_bo5_2026_ot_basic.json", "Haven"),
    ("match_bo5_2026_ot_tabs_all.json", "Ascent"),
    ("match_bo5_2026_ot_tabs_all.json", "Haven"),
    ("match_vcl_brasil_basic.json", "Lotus"),
]


def _com_lado(map_):
    if not map_.has_sides:
        pytest.skip("mapa sem histórico de lado (pegadinha 22)")


def test_lado_do_vencedor_soma_rounds_ct_e_rounds_t(match_map):
    _, map_ = match_map
    _com_lado(map_)
    teams = {t.name: t for t in map_.teams}
    for tag, name in tags_by_score(map_).items():
        won = [r for r in map_.rounds if r.winner == tag and r.number <= REGULATION]
        assert sum(r.side == "ct" for r in won) == teams[name].rounds_ct, tag
        assert sum(r.side == "t" for r in won) == teams[name].rounds_t, tag


def test_lado_constante_no_tempo_e_invertido_no_intervalo(match_map):
    _, map_ = match_map
    _com_lado(map_)
    tags = tags_by_score(map_)
    sides = {
        (half, tag): {r.side for r in map_.rounds if r.winner == tag and r.number in rounds}
        for half, rounds in HALVES.items()
        for tag in tags
    }
    for key, seen in sides.items():
        assert len(seen) <= 1, f"{key}: lados {seen} no mesmo tempo"
    for tag in tags:
        first, second = sides[("1º tempo", tag)], sides[("2º tempo", tag)]
        if first and second:
            assert first != second, f"{tag} não trocou de lado no intervalo"
    for half in HALVES:
        a, b = (sides[(half, tag)] for tag in tags)
        if a and b:
            assert a != b, f"{half}: os dois times venceram do mesmo lado"


def test_fixtures_cobrem_overtime(load_match):
    found = {
        (name, m.name)
        for name in {n for n, _ in OVERTIME_MAPS}
        for m in load_match(name).maps
        if len(m.rounds) > REGULATION
    }
    assert found == set(OVERTIME_MAPS)


@pytest.mark.parametrize("name,map_name", OVERTIME_MAPS, ids=[f"{n}-{m}" for n, m in OVERTIME_MAPS])
def test_rounds_ct_t_excluem_overtime(load_match, name, map_name):
    map_ = next(m for m in load_match(name).maps if m.name == map_name)
    teams = {t.name: t for t in map_.teams}
    for tag, team_name in tags_by_score(map_).items():
        team = teams[team_name]
        regulation = sum(r.winner == tag and r.number <= REGULATION for r in map_.rounds)
        overtime = sum(r.winner == tag and r.number > REGULATION for r in map_.rounds)
        assert team.rounds_ct + team.rounds_t == regulation
        assert team.score == regulation + overtime
    # Os dois times chegam empatados em 12 ao fim do regulamentar.
    assert all(t.rounds_ct + t.rounds_t == 12 for t in map_.teams)
