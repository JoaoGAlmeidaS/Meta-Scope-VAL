"""D6: detalhe de partida → cinco tabelas raw, sobre os fixtures reais.

Pronto quando: uma BO5 completa está em Parquet nas cinco tabelas (ver também `test_lake.py`).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import pytest

from ingestion import lake
from ingestion.flatten import flatten_match

NOW = datetime(2026, 9, 29, tzinfo=UTC)
BO5 = "match_bo5_2026_ot_basic.json"
BO5_TABS = "match_bo5_2026_ot_tabs_all.json"


def _flat(load_match, name: str) -> dict[str, list[dict]]:
    return flatten_match(
        load_match(name), has_tabs=name.endswith("_tabs_all.json"), collected_at=NOW
    )


@pytest.fixture
def flat(match_file, load_match):
    return _flat(load_match, match_file)


def test_toda_tabela_passa_no_schema_do_lake(flat):
    for name, rows in flat.items():
        lake.to_table(name, rows)


@pytest.mark.parametrize(
    "name,maps,veto",
    [
        ("match_bo5_2022_basic.json", 5, 7),
        (BO5, 5, 7),
        (BO5_TABS, 5, 7),
        ("match_bo3_2x0_basic.json", 2, 7),
        ("match_vcl_brasil_basic.json", 3, 0),
    ],
)
def test_contagens_por_fixture(load_match, name, maps, veto):
    flat = _flat(load_match, name)
    detail = load_match(name)
    assert len(flat["raw_match"]) == 1
    assert len(flat["raw_map"]) == maps
    assert len(flat["raw_veto"]) == veto
    assert len(flat["raw_player_map"]) == 10 * maps
    assert len(flat["raw_round"]) == sum(len(m.rounds) for m in detail.maps)


def test_bo5_com_overtime(load_match):
    flat = _flat(load_match, BO5)
    rounds = Counter(r["map_id"] for r in flat["raw_round"])
    maps = {m["map_name"]: m for m in flat["raw_map"]}
    assert rounds[maps["Ascent"]["map_id"]] == 26
    assert rounds[maps["Haven"]["map_id"]] == 26
    assert [m["map_order"] for m in flat["raw_map"]] == [1, 2, 3, 4, 5]


def test_ponte_resolve_todos_os_ids(flat):
    assert all(m["bridge_ok"] for m in flat["raw_map"])
    assert all(r["winner_team_id"] for r in flat["raw_round"])
    assert all(p["team_id"] for p in flat["raw_player_map"])
    assert all(v["team_id"] for v in flat["raw_veto"] if v["action"] != "remains")


def test_colunas_de_time_seguem_a_ordem_da_partida(match, flat):
    t1, t2 = match.teams
    (row,) = flat["raw_match"]
    assert (row["team1_id"], row["team2_id"]) == (t1.id, t2.id)
    wins = Counter((r["map_id"], r["winner_team_id"]) for r in flat["raw_round"])
    for m in flat["raw_map"]:
        assert m["team1_score"] == wins[(m["map_id"], t1.id)]
        assert m["team2_score"] == wins[(m["map_id"], t2.id)]
    maps_won = Counter(
        t1.id if m["team1_score"] > m["team2_score"] else t2.id for m in flat["raw_map"]
    )
    assert (maps_won[t1.id], maps_won[t2.id]) == (t1.score, t2.score)


def test_economia_so_com_tabs(has_economy, flat):
    with_tabs = has_economy
    for r in flat["raw_round"]:
        assert (r.get("team1_buy") is not None) is with_tabs
        assert (r.get("team2_bank") is not None) is with_tabs


def test_economia_alinhada_ao_vencedor(load_match):
    # A economia não diz quem venceu pela tag; o alinhamento tag → id tem que concordar.
    detail = load_match(BO5_TABS)
    flat = _flat(load_match, BO5_TABS)
    by_round = {(r["map_id"], r["round_number"]): r for r in flat["raw_round"]}
    t1 = detail.teams[0].id
    for map_ in detail.maps:
        tags = [t.name for t in map_.economy.teams]
        for eco in map_.economy.rounds:
            row = by_round[(map_.id, eco.number)]
            winner_slot = "team1" if row["winner_team_id"] == t1 else "team2"
            winner_tag = next(tag for tag, t in zip(tags, eco.teams, strict=True) if t.winner)
            assert row["winner_tag"] == winner_tag
            assert row[f"{winner_slot}_buy"] in {"eco", "semi-eco", "semi-buy", "full-buy"}


def test_veto_vazio_e_mapa_sem_pick(load_match):
    flat = _flat(load_match, "match_vcl_brasil_basic.json")
    assert flat["raw_veto"] == []
    assert all(m["picked_by_team_id"] is None for m in flat["raw_map"])


def test_pick_resolvido_para_id(load_match):
    detail = load_match(BO5)
    flat = _flat(load_match, BO5)
    ids = {t.id for t in detail.teams}
    picked = [m for m in flat["raw_map"] if m["picked_by_name"]]
    assert len(picked) == 4  # o decisivo não tem `pickedBy`
    assert all(m["picked_by_team_id"] in ids for m in picked)


def test_timestamp_utc_bate_com_utc_date(match):
    assert match.timestamp == parsedate_to_datetime(match.utc_date)
    assert match.timestamp.tzinfo is not None


def test_agente_minusculo_e_rating_float(flat):
    for p in flat["raw_player_map"]:
        assert p["agent"] == p["agent"].lower()
        assert p["rating"] is None or isinstance(p["rating"], float)


def test_ponte_que_nao_fecha_anula_ids_do_mapa(load_match):
    detail = load_match(BO5)
    summit = next(m for m in detail.maps if m.name == "Summit")
    broken = summit.model_copy(
        update={"teams": [t.model_copy(update={"score": 2}) for t in summit.teams]}
    )
    maps = [broken if m.name == "Summit" else m for m in detail.maps]
    flat = flatten_match(detail.model_copy(update={"maps": maps}), has_tabs=False, collected_at=NOW)
    row = next(m for m in flat["raw_map"] if m["map_name"] == "Summit")
    assert row["bridge_ok"] is False
    rounds = [r for r in flat["raw_round"] if r["map_id"] == row["map_id"]]
    assert rounds and all(r["winner_team_id"] is None for r in rounds)
    lake.to_table("raw_round", flat["raw_round"])  # nulo permitido, gravável


def test_mapa_de_lobby_remake_marcado_no_lake(load_match):
    # Pegadinha 36: o mapa entra no lake, marcado para ficar fora da validação cruzada.
    flat = _flat(load_match, "match_veto_note_tabs_all.json")
    assert {m["map_name"]: m["has_complete_stats"] for m in flat["raw_map"]} == {
        "Sunset": True,
        "Haven": True,
        "Ascent": False,
    }


def test_mapa_sem_dado_fica_contado_na_partida(load_match):
    # Pegadinha 33: o mapa descartado some de `raw_map`, mas a partida guarda quantos foram, para o
    # teste de placar da série no dbt.
    flat = _flat(load_match, "match_map_without_data_tabs_all.json")
    (match,) = flat["raw_match"]
    assert (match["n_maps"], match["n_maps_without_data"]) == (2, 1)
    assert all(m["n_maps_without_data"] == 0 for m in _flat(load_match, BO5)["raw_match"])
