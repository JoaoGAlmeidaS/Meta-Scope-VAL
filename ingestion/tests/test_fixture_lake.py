"""Lake de fixtures (D14): o trilho de CI sem segredo roda o dbt sobre ele."""

from __future__ import annotations

from ingestion import lake
from ingestion.fixture_lake import build


def test_lake_de_fixtures_tem_os_casos_de_teste(tmp_path):
    root = build(tmp_path / "lake")

    events = {r["event_id"]: r for r in lake.read_table(root, "raw_event").to_pylist()}
    assert {e: (r["season"], r["tier"], r["region"]) for e, r in events.items()} == {
        "2977": (2026, "vct", "americas"),
        "2962": (2026, "vcl", "americas"),
        "1015": (2022, "vct", "international"),
        "3125": (2026, "vcl", "americas"),
    }
    matches = lake.read_table(root, "raw_match").to_pylist()
    assert sorted(m["match_id"] for m in matches) == [
        "130691",
        "681934",
        "707490",
        "734308",
        "734313",
        "757797",
    ]
    maps = lake.read_table(root, "raw_map").to_pylist()
    assert [m["map_name"] for m in maps if not m["has_round_sides"]] == ["Ascent"]  # 681934
    # Dentro do corte das abas só vem com abas o que tem fixture com abas; 2022 vem sem.
    assert {m["match_id"]: m["has_tabs"] for m in matches}["130691"] is False
    rejects = lake.read_table(root, "raw_reject").to_pylist()
    assert [(r["match_id"], r["reason"]) for r in rejects] == [("734307", "not_found")]
    # Pegadinha 29: tag de caixa mista não deixa jogador sem time nem round sem economia.
    players = lake.read_table(root, "raw_player_map").to_pylist()
    assert all(p["team_id"] for p in players)
    rounds = [
        r for r in lake.read_table(root, "raw_round").to_pylist() if r["match_id"] == "757797"
    ]
    assert rounds and all(r["team1_buy"] and r["team2_buy"] for r in rounds)


def test_reconstruir_nao_acumula(tmp_path):
    root = tmp_path / "lake"
    build(root)
    build(root)
    assert lake.read_table(root, "raw_match").num_rows == 6
