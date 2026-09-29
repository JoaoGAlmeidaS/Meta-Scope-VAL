"""Contrato: todo fixture real passa pelos modelos de `ingestion/schemas.py`.

Se um destes testes quebrar depois de regravar um fixture, a API mudou de formato. Corrija o
modelo conscientemente; não afrouxe o modelo para caber.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion.schemas import EventAgentsMap, EventMatch, EventSummary, MatchDetail, Response

EVENT_FIXTURES = [
    ("events_vct_p1.json", EventSummary),
    ("events_vcl_p1.json", EventSummary),
    ("event_matches_vct_americas_s2_2026.json", EventMatch),
    ("event_agents_vct_americas_s2_2026.json", EventAgentsMap),
]


def test_partida_carrega_no_contrato(match_file, load_json):
    detail = Response[MatchDetail].model_validate(load_json(match_file)).data
    assert detail.maps, "partida sem mapa jogado"


@pytest.mark.parametrize("name,model", EVENT_FIXTURES, ids=[n for n, _ in EVENT_FIXTURES])
def test_evento_carrega_no_contrato(name, model, load_json):
    rows = Response[list[model]].model_validate(load_json(name)).data
    assert rows


def test_mapa_jogado_tem_10_jogadores_com_um_agente(match_map):
    _, map_ = match_map
    assert map_.status == "played"
    assert len(map_.players) == 10
    assert all(len(p.agents) == 1 for p in map_.players)


def test_abas_so_com_tabs_all(match_file, match):
    com_abas = match_file.endswith("_tabs_all.json")
    for map_ in match.maps:
        assert (map_.economy is not None) is com_abas, map_.name
        assert (map_.performance is not None) is com_abas, map_.name


# --- comportamento do contrato ----------------------------------------------------------------


def _raw_match(load_json) -> dict:
    return load_json("match_bo5_2026_ot_basic.json")


def test_campo_novo_nao_quebra(load_json):
    raw = _raw_match(load_json)
    raw["data"]["campoNovo"] = {"qualquer": 1}
    raw["data"]["maps"][0]["rounds"][0]["campoNovo"] = "x"
    Response[MatchDetail].model_validate(raw)


@pytest.mark.parametrize(
    "path,value",
    [
        (("maps", 0, "rounds", 0, "side"), None),
        (("maps", 0, "rounds", 0, "side"), "attack"),
        (("maps", 0, "teams", 0, "roundsCt"), "três"),
        (("maps", 0, "players", 0, "agents"), []),
        (("teams", 0, "id"), None),
    ],
    ids=["side-nulo", "side-desconhecido", "roundsCt-texto", "sem-agente", "time-sem-id"],
)
def test_campo_consumido_alterado_quebra(load_json, path, value):
    raw = _raw_match(load_json)
    node = raw["data"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError):
        Response[MatchDetail].model_validate(raw)


def test_campo_consumido_ausente_quebra(load_json):
    raw = _raw_match(load_json)
    del raw["data"]["maps"][0]["rounds"][0]["winner"]
    with pytest.raises(ValidationError):
        Response[MatchDetail].model_validate(raw)


def test_rating_inteiro_vira_float(load_json, load_match):
    # Summit da 734313 tem jogadores com `rating: 1` inteiro no JSON cru.
    raw_players = load_json("match_bo3_2x0_basic.json")["data"]["maps"][1]["players"]
    assert any(isinstance(p["stats"]["rating"], int) for p in raw_players)
    players = load_match("match_bo3_2x0_basic.json").maps[1].players
    assert all(isinstance(p.stats.rating, float) for p in players)


def test_agentes_normalizados_entre_endpoints(load_json, load_match):
    # 734308 e 734313 são do mesmo evento do fixture de agentes (VCT Americas Stage 2 2026).
    event = (
        Response[list[EventAgentsMap]]
        .model_validate(load_json("event_agents_vct_americas_s2_2026.json"))
        .data
    )
    known = {a.name for row in event for a in row.agents}
    for name in ("match_bo5_2026_ot_basic.json", "match_bo3_2x0_basic.json"):
        picked = {a.name for m in load_match(name).maps for p in m.players for a in p.agents}
        assert picked <= known, picked - known
        assert all(a == a.lower() for a in picked)


def test_duracao_em_segundos(load_match):
    maps = {m.name: m for m in load_match("match_bo5_2026_ot_basic.json").maps}
    assert maps["Split"].duration_seconds == 42 * 60 + 6
    assert maps["Haven"].duration_seconds == 3600 + 3
