"""D5: índice de eventos, listagem de partidas e gabarito, sobre fixtures reais."""

from __future__ import annotations

from datetime import date

import pytest

from ingestion import lake
from ingestion.client import TransientError
from ingestion.collectors import (
    INTERNATIONAL,
    CollectionAborted,
    Event,
    attach_matches,
    collect_events,
    is_china_tier2,
    list_events,
    season_from_name,
)
from ingestion.fixture_lake import OfflineClient as FakeClient
from ingestion.fixture_lake import route
from ingestion.schemas import EventMatch, Response


def _page(load_json, name: str, ids: list[str] | None = None) -> dict:
    body = load_json(name)
    if ids is not None:
        body["data"] = [e for e in body["data"] if e["id"] in ids]
    return body


def _event(id_="1", name="VCT 2026: Americas Stage 2", status="completed") -> dict:
    return {"id": id_, "name": name, "status": status, "prizepool": "0", "country": "br"}


@pytest.mark.parametrize(
    "name,season",
    [
        ("VCT 2026: Americas Stage 2", 2026),
        ("VCL 26: Americas Last Chance Qualifier", 2026),
        ("Champions Tour 2024: Masters Madrid", 2024),
        ("Valorant Champions 2025", 2025),
        ("Challengers League 2024 Vietnam: Split 2", 2024),
        ("Elevate Play: Avalanche", None),
    ],
)
def test_temporada_pelo_nome(name, season):
    assert season_from_name(name) == season


def test_regiao_e_tier_pelos_filtros_da_listagem(load_json):
    vct, vcl = "events_vct_p1.json", "events_vcl_p1.json"
    client = FakeClient(
        {
            route("/events", tier="vct", page=1): _page(load_json, vct),
            route("/events", tier="vct", region="americas", page=1): _page(
                load_json, vct, ["2977", "2765"]
            ),
            route("/events", tier="vct", region="emea", page=1): _page(
                load_json, vct, ["2976", "2765"]
            ),
            route("/events", tier="vcl", page=1): _page(load_json, vcl),
        }
    )
    events = {e.id: e for e in list_events(client, since=2023)}

    assert events["2977"].region == "americas"
    assert events["2976"].region == "emea"
    assert events["2765"].region == INTERNATIONAL  # Masters London: aparece em duas regiões
    assert events["2776"].region is None  # só na listagem sem filtro
    # China Evolution Series Act 3 aparece em vct e vcl (pegadinha 15); é tier 2 chinês e fica fora.
    assert "3105" not in events
    assert not events["2977"].tier_ambiguous
    assert events["3077"].tier == "vcl"  # THE POKAL 2026


def test_evento_nos_dois_tiers_fica_ambiguo_e_vale_vct():
    # Pegadinha 15: o tier do vlr.gg é ruidoso; vct prevalece, e o seed corrige o resto.
    event = Event("1", "Algum evento 2026", "completed", None, "0", tiers={"vct", "vcl"})
    assert event.tier_ambiguous
    assert event.tier == "vct"


def _rows(rows: list[dict]) -> dict:
    return {"status": "OK", "data": rows}


def test_tier_2_chines_fica_fora_da_coleta():
    # Decisão de 05/10: VCL China e China Evolution Series saem; VCT China e internacionais ficam.
    vct = [
        _event("10", "VCT 2026: China Stage 2"),
        _event("11", "China Evolution Series: Act 1"),  # 2025: só em tier=vct
        _event("12", "Valorant Masters Toronto 2025"),
    ]
    vcl = [
        _event("20", "China National Tournament 2026 Split Alpha: Pro Division"),
        _event("21", "VCT 2025: China Ascension"),
        _event("22", "Challengers 2026: Japan Split 2"),
    ]
    client = FakeClient(
        {
            route("/events", tier="vct", page=1): _rows(vct),
            route("/events", tier="vct", region="china", page=1): _rows(vct[:2]),
            route("/events", tier="vcl", page=1): _rows(vcl),
            route("/events", tier="vcl", region="china", page=1): _rows(vcl[:2]),
            route("/events", tier="vcl", region="pacific", page=1): _rows(vcl[2:]),
        }
    )
    events = list_events(client, since=2025)
    assert sorted(e.id for e in events) == ["10", "12", "22"]
    assert not any(is_china_tier2(e) for e in events)


def test_upcoming_e_temporada_anterior_ficam_de_fora():
    client = FakeClient(
        {
            route("/events", tier="vct", page=1): {
                "status": "OK",
                "data": [
                    _event("1", status="upcoming"),
                    _event("2", status="ongoing"),
                    _event("3", name="Champions Tour 2022: Masters Reykjavík"),
                ],
            }
        }
    )
    assert [e.id for e in list_events(client, since=2023)] == ["2"]


def test_paginacao_para_na_pagina_vazia():
    client = FakeClient(
        {
            route("/events", tier="vct", page=1): {"status": "OK", "data": [_event("1")]},
            route("/events", tier="vct", page=2): {"status": "OK", "data": [_event("2")]},
        }
    )
    list_events(client, since=2023)
    assert route("/events", tier="vct", page=3) in client.calls  # a vazia encerra
    assert route("/events", tier="vct", page=4) not in client.calls


def test_paginacao_para_depois_de_duas_paginas_antigas():
    old = {"status": "OK", "data": [_event("9", name="Champions Tour 2021: Stage 3")]}
    client = FakeClient(
        {
            route("/events", tier="vcl", page=1): {"status": "OK", "data": [_event("1")]},
            route("/events", tier="vcl", page=2): old,
            route("/events", tier="vcl", page=3): old,
            route("/events", tier="vcl", page=4): old,
        }
    )
    list_events(client, since=2023)
    assert route("/events", tier="vcl", page=3) in client.calls
    assert route("/events", tier="vcl", page=4) not in client.calls


def test_listagem_de_partidas_do_evento(load_json):
    event = Event("2977", "VCT 2026: Americas Stage 2", "completed", "br", "250000")
    client = FakeClient(
        {route("/events/2977/matches"): load_json("event_matches_vct_americas_s2_2026.json")}
    )
    attach_matches(client, event)
    assert len(event.completed_matches) == 60
    assert event.season == 2026
    assert event.last_listed_on == date(2026, 9, 6)
    assert min(event.listed_dates) == date(2026, 7, 16)


def test_listagem_em_andamento_tem_placar_nulo(load_json):
    raw = load_json("event_matches_ongoing_champions_2026.json")
    matches = Response[list[EventMatch]].model_validate(raw).data
    upcoming = [m for m in matches if m.status == "upcoming"]
    assert upcoming and all(t.score is None for m in upcoming for t in m.teams)
    assert all(t.score is not None for m in matches if m.status == "completed" for t in m.teams)


def test_temporada_pela_data_quando_o_nome_nao_tem_ano():
    event = Event("3125", "Elevate Play: Avalanche", "completed", None, "")
    event.matches = [
        EventMatch.model_validate(
            {
                "id": "1",
                "status": "completed",
                "date": "Sat, August 1, 2026",
                "teams": [
                    {"name": "A", "score": 2, "winner": True},
                    {"name": "B", "score": 0, "winner": False},
                ],
            }
        )
    ]
    assert event.season == 2026


def test_data_da_listagem_invalida_vira_nula():
    m = EventMatch.model_validate(
        {
            "id": "1",
            "status": "upcoming",
            "date": "TBD",
            "teams": [{"name": "A", "score": None, "winner": False}] * 2,
        }
    )
    assert m.listed_on is None


def _collect_routes(load_json, event_ids: list[str]) -> dict:
    routes = {
        route("/events", tier="vct", page=1): _page(load_json, "events_vct_p1.json", event_ids),
    }
    for eid in event_ids:
        routes[route(f"/events/{eid}/matches")] = load_json(
            "event_matches_vct_americas_s2_2026.json"
        )
    routes[route("/events/2977/agents")] = load_json("event_agents_vct_americas_s2_2026.json")
    return routes


def test_collect_events_grava_no_lake_e_faz_upsert(load_json, tmp_path):
    collect_events(FakeClient(_collect_routes(load_json, ["2977"])), since=2023, root=tmp_path)
    collect_events(FakeClient(_collect_routes(load_json, ["2976"])), since=2023, root=tmp_path)

    events = lake.read_table(tmp_path, "raw_event").to_pylist()
    assert sorted(e["event_id"] for e in events) == ["2976", "2977"]
    assert all(e["season"] == 2026 for e in events)

    listing = lake.read_table(tmp_path, "raw_event_match")
    assert listing.num_rows == 120  # 60 partidas × 2 eventos
    agents = lake.read_table(tmp_path, "raw_event_agents").to_pylist()
    assert {a["event_id"] for a in agents} == {"2977"}  # 2976 sem gabarito: arquivo vazio
    assert (tmp_path / "raw_event_agents" / "season=2026" / "2976.parquet").exists()


def test_listagem_fora_do_contrato_pula_so_aquele_evento(load_json, tmp_path):
    routes = _collect_routes(load_json, ["2977", "2976"])
    broken = routes[route("/events/2976/matches")]
    broken["data"][0]["teams"] = broken["data"][0]["teams"][:1]  # "bye": um time só
    events = collect_events(FakeClient(routes), since=2023, root=tmp_path)
    assert [e.id for e in events] == ["2977"]
    assert [r["event_id"] for r in lake.read_table(tmp_path, "raw_event").to_pylist()] == ["2977"]


def test_gabarito_indisponivel_nao_para_a_coleta_e_volta_depois(load_json, tmp_path):
    # Caso real do D5: `/events/1309/agents` deu 502 nas 6 tentativas e derrubou a coleta.
    routes = _collect_routes(load_json, ["2977", "2976"])
    routes[route("/events/2976/agents")] = TransientError("502 em /events/2976/agents")
    events = collect_events(FakeClient(routes), since=2023, root=tmp_path)

    assert [e.id for e in events] == ["2977", "2976"]
    agents_2976 = tmp_path / "raw_event_agents" / "season=2026" / "2976.parquet"
    assert not agents_2976.exists()  # sem arquivo: a próxima execução tenta de novo

    routes[route("/events/2976/agents")] = load_json("event_agents_vct_americas_s2_2026.json")
    collect_events(FakeClient(routes), since=2023, root=tmp_path)
    assert agents_2976.exists()


def test_uma_listagem_indisponivel_pula_so_aquele_evento(load_json, tmp_path):
    routes = _collect_routes(load_json, ["2977", "2776", "2976"])
    routes[route("/events/2776/matches")] = TransientError("502 em /events/2776/matches")
    events = collect_events(FakeClient(routes), since=2023, root=tmp_path)
    assert [e.id for e in events] == ["2977", "2976"]


def test_listagens_seguidas_indisponiveis_abortam_mas_gravam_o_indice(load_json, tmp_path):
    down = ["2776", "2976", "2978"]
    routes = _collect_routes(load_json, ["2977", *down])
    for eid in down:
        routes[route(f"/events/{eid}/matches")] = TransientError(f"503 em /events/{eid}/matches")

    with pytest.raises(CollectionAborted):
        collect_events(FakeClient(routes), since=2023, root=tmp_path)
    assert [r["event_id"] for r in lake.read_table(tmp_path, "raw_event").to_pylist()] == ["2977"]


def test_collect_events_regravar_nao_duplica(load_json, tmp_path):
    for _ in range(2):
        collect_events(FakeClient(_collect_routes(load_json, ["2977"])), since=2023, root=tmp_path)
    assert lake.read_table(tmp_path, "raw_event").num_rows == 1
    assert lake.read_table(tmp_path, "raw_event_match").num_rows == 60
