"""D6/D7: do índice de eventos ao Parquet, com cliente falso servindo os fixtures reais."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from ingestion import lake
from ingestion.collectors import MAX_CONSECUTIVE_REJECTS, CollectionAborted, backfill
from ingestion.tests.conftest import FakeClient, route

TODAY = date(2026, 9, 29)  # corte das abas: 2025-03-29


def _listing(load_json, ids: list[str]) -> dict:
    body = load_json("event_matches_vct_americas_s2_2026.json")
    body["data"] = [m for m in body["data"] if m["id"] in ids]
    return body


def _vcl_listing() -> dict:
    return {
        "status": "OK",
        "data": [
            {
                "id": "707490",
                "status": "completed",
                "date": "Thu, July 16, 2026",
                "teams": [
                    {"name": "A", "score": 3, "winner": True},
                    {"name": "B", "score": 0, "winner": False},
                ],
            }
        ],
    }


def _events(load_json) -> dict:
    vct = load_json("events_vct_p1.json")
    vct["data"] = [e for e in vct["data"] if e["id"] == "2977"]
    vcl = load_json("events_vcl_p1.json")
    vcl["data"] = [e for e in vcl["data"] if e["id"] == "2962"]
    return {
        route("/events", tier="vct", page=1): vct,
        route("/events", tier="vcl", page=1): vcl,
    }


@pytest.fixture
def routes(load_json) -> dict:
    basic_bo5 = load_json("match_bo5_2026_ot_basic.json")
    bo3 = load_json("match_bo3_2x0_basic.json")
    vcl = load_json("match_vcl_brasil_basic.json")
    return {
        **_events(load_json),
        # VCL listada primeiro no dicionário: a ordem da coleta tem que vir da data, não daqui.
        route("/events/2962/matches"): _vcl_listing(),
        route("/events/2977/matches"): _listing(load_json, ["734308", "734313", "734307"]),
        route("/events/2977/agents"): load_json("event_agents_vct_americas_s2_2026.json"),
        route("/matches/734308", tabs="all"): load_json("match_bo5_2026_ot_tabs_all.json"),
        route("/matches/734308"): basic_bo5,
        route("/matches/734313", tabs="all"): bo3,
        route("/matches/734313"): bo3,
        route("/matches/707490", tabs="all"): vcl,
        route("/matches/707490"): vcl,
        # 734307 sem rota: 404 → rejeitada.
    }


def _detail_calls(client: FakeClient) -> list[tuple[str, tuple]]:
    return [c for c in client.calls if c[0].startswith("/matches/")]


def _count(root, name: str) -> int:
    glob = (root / name / "**" / "*.parquet").as_posix()
    return duckdb.sql(
        f"select count(*) from read_parquet('{glob}', hive_partitioning=true)"
    ).fetchone()[0]


def test_backfill_do_mais_recente_para_o_mais_antigo(routes, tmp_path):
    client = FakeClient(routes)
    stats = backfill(client, since=2023, root=tmp_path, today=TODAY)

    order = [path for path, _ in _detail_calls(client)]
    assert order.index("/matches/707490") > max(
        order.index(p) for p in ("/matches/734308", "/matches/734313")
    )
    assert stats.matches == 3
    assert stats.rejects == {"api": 1}
    assert _count(tmp_path, "raw_match") == 3
    assert _count(tmp_path, "raw_map") == 5 + 2 + 3
    assert _count(tmp_path, "raw_reject") == 1
    assert _count(tmp_path, "raw_event") == 2  # arquivo único, sem partição: o glob do dbt lê


def test_abas_so_dentro_da_janela(routes, tmp_path):
    client = FakeClient(routes)
    backfill(client, since=2023, root=tmp_path, today=TODAY)
    assert all(dict(p) == {"tabs": "all"} for _, p in _detail_calls(client))

    later = FakeClient(routes)  # dois anos depois, julho/2026 saiu da janela + aquecimento
    backfill(later, since=2023, root=tmp_path / "later", today=date(2028, 9, 29))
    assert all(p == () for _, p in _detail_calls(later))
    has_tabs = duckdb.sql(
        "select bool_or(has_tabs) from read_parquet("
        f"'{(tmp_path / 'later' / 'raw_match' / '**' / '*.parquet').as_posix()}')"
    ).fetchone()[0]
    assert has_tabs is False


def test_segunda_execucao_pula_evento_completo(routes, tmp_path):
    backfill(FakeClient(routes), since=2023, root=tmp_path, today=TODAY)
    again = FakeClient(routes)
    stats = backfill(again, since=2023, root=tmp_path, today=TODAY)
    assert _detail_calls(again) == []
    assert stats.events_skipped == 2
    assert _count(tmp_path, "raw_match") == 3


def test_force_regrava_sem_duplicar(routes, tmp_path):
    backfill(FakeClient(routes), since=2023, root=tmp_path, today=TODAY)
    rounds = _count(tmp_path, "raw_round")
    again = FakeClient(routes)
    backfill(again, since=2023, root=tmp_path, today=TODAY, force=True)
    assert _detail_calls(again)
    assert _count(tmp_path, "raw_round") == rounds
    assert _count(tmp_path, "raw_match") == 3


def test_um_evento_so(routes, tmp_path):
    client = FakeClient(routes)
    backfill(client, since=2023, root=tmp_path, today=TODAY, only_event="2962")
    assert [p for p, _ in _detail_calls(client)] == ["/matches/707490"]


def test_partida_nao_finalizada_e_rejeitada_sem_contar_para_o_aborto(routes, tmp_path):
    routes[route("/matches/707490", tabs="all")]["data"]["status"] = "live"
    stats = backfill(FakeClient(routes), since=2023, root=tmp_path, today=TODAY)
    assert stats.rejects == {"api": 1, "not_final": 1}


def test_rejeicoes_seguidas_abortam_sem_gravar_o_evento(routes, load_json, tmp_path):
    ids = [str(700000 + i) for i in range(MAX_CONSECUTIVE_REJECTS)]
    listing = _vcl_listing()
    listing["data"] = [dict(listing["data"][0], id=i) for i in ids]
    routes[route("/events/2962/matches")] = listing
    broken = load_json("match_vcl_brasil_basic.json")
    del broken["data"]["maps"][0]["rounds"][0]["side"]  # formato mudou
    for i in ids:
        routes[route(f"/matches/{i}", tabs="all")] = broken

    with pytest.raises(CollectionAborted):
        backfill(FakeClient(routes), since=2023, root=tmp_path, today=TODAY)
    assert not (tmp_path / "raw_match" / "season=2026" / "2962.parquet").exists()
    assert lake.collected_match_ids(tmp_path, 2026, "2977") is not None  # o anterior ficou
