"""Contrato: todo fixture real passa pelos modelos de `ingestion/schemas.py`.

Se um destes testes quebrar depois de regravar um fixture, a API mudou de formato. Corrija o
modelo conscientemente; não afrouxe o modelo para caber.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion.bridge import tag_to_team_id
from ingestion.schemas import (
    EventAgentsMap,
    EventMatch,
    EventSummary,
    MatchDetail,
    Response,
    known_source_defect,
)

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


def test_abas_so_com_tabs_all(has_economy, match):
    com_abas = has_economy
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


SEM_LADO = "match_vcl_map_without_sides_tabs_all.json"


def test_mapa_sem_historico_de_lado_entra_inteiro(load_match):
    # Pegadinha 22 (681934, Challengers Brasil): Ascent sem linha do tempo, Split com.
    maps = {m.name: m for m in load_match(SEM_LADO).maps}
    ascent, split = maps["Ascent"], maps["Split"]
    assert not ascent.has_sides and split.has_sides
    assert all(r.side is None and r.method is None for r in ascent.rounds)
    assert len(ascent.rounds) == sum(t.score for t in ascent.teams)  # vencedores continuam vindo
    assert len(ascent.players) == 10


@pytest.mark.parametrize(
    "name,path,value",
    [
        # Mapa com lado perde o lado de um round só.
        ("match_bo5_2026_ot_basic.json", ("maps", 0, "rounds", 5, "side"), None),
        # Mapa com lado perde o contador de um time só.
        ("match_bo5_2026_ot_basic.json", ("maps", 0, "teams", 1, "roundsT"), None),
        # Mapa sem lado ganha o lado de um round só.
        (SEM_LADO, ("maps", 0, "rounds", 0, "side"), "t"),
    ],
    ids=["round-sem-lado", "contador-sem-lado", "lado-avulso"],
)
def test_lado_pela_metade_quebra(load_json, name, path, value):
    raw = load_json(name)
    node = raw["data"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError, match="lado preenchido"):
        Response[MatchDetail].model_validate(raw)


SEM_METODO = "match_sides_without_method_tabs_all.json"


def test_lado_sem_metodo_entra(load_json, load_match):
    # Pegadinha 31 (748625): lado e contadores completos, `method` nulo em todo round.
    raw = load_json(SEM_METODO)["data"]["maps"]
    assert all(r["method"] is None and r["side"] for m in raw for r in m["rounds"])
    maps = load_match(SEM_METODO).maps
    assert all(m.has_sides for m in maps)
    assert all(r.method is None for m in maps for r in m.rounds)


def test_metodo_pela_metade_entra(load_json, load_match):
    # Pegadinha 31 revisada (433835, LATAM South 2025): método nulo em rounds soltos. O método não
    # entra na reconstrução de lado; só o lado é tudo ou nada.
    raw = load_json("match_method_partial_basic.json")["data"]["maps"]
    methods = [r["method"] for m in raw for r in m["rounds"]]
    assert None in methods and any(methods)
    assert all(m.has_sides for m in load_match("match_method_partial_basic.json").maps)


def test_time_sem_tag_vira_tag_vazia_e_a_ponte_fecha(load_json, load_match):
    # Pegadinha 40 (614924, Korea WDG 2026): o time de nome só em coreano não tem tag; os jogadores
    # vêm com `teamTag` vazio e os rounds que ele venceu, com `winner` nulo.
    raw = load_json("match_team_without_tag_tabs_all.json")["data"]["maps"][0]
    assert {p["teamTag"] for p in raw["players"]} == {"ACL", ""}
    assert None in {r["winner"] for r in raw["rounds"]}
    match = load_match("match_team_without_tag_tabs_all.json")
    (map_,) = match.maps
    assert {r.winner for r in map_.rounds} == {"ACL", ""}
    assert set(tag_to_team_id(match, map_).values()) == {t.id for t in match.teams}


def test_mapa_refeito_pela_ordem_do_veto(load_match):
    # Pegadinha 36 (482510): "Map 1 stats are unavailable"; o 1º mapa da série pelo veto é o Haven,
    # que a API põe por último em `maps[]`.
    maps = load_match("match_remake_note_veto_order_tabs_all.json").maps
    assert [(m.name, m.stats_incomplete) for m in maps] == [
        ("Ascent", False),
        ("Split", False),
        ("Haven", True),
    ]


def test_mapa_com_placar_e_sem_rounds_fica_sem_estatistica(load_match):
    # 459856: o Split vem 13–6, com jogadores e agentes, mas sem nenhum round.
    maps = {m.name: m for m in load_match("match_remake_map_without_rounds_tabs_all.json").maps}
    assert maps["Split"].rounds == [] and maps["Split"].stats_incomplete
    assert not maps["Icebox"].stats_incomplete


def test_loadout_nulo_na_economia_nao_derruba_a_partida(load_json):
    # Pegadinha 23 (668479: Haven com `loadout: null` nos primeiros rounds; bank e buy vêm).
    raw = load_json("match_bo5_2026_ot_tabs_all.json")
    for team in raw["data"]["maps"][0]["economy"]["rounds"][0]["teams"]:
        team["loadout"] = None
    detail = Response[MatchDetail].model_validate(raw).data
    assert detail.maps[0].economy.rounds[0].teams[0].loadout is None


def test_time_sem_pagina_no_vlr_quebra(load_json):
    # Pegadinha 24 (668491): adversário "TBD", sem id. Sem chave de time, a partida não entra.
    raw = load_json("match_bo3_2x0_basic.json")
    raw["data"]["teams"][1].update({"id": None, "name": "TBD"})
    with pytest.raises(ValidationError, match="teams.1.id"):
        Response[MatchDetail].model_validate(raw)


ABAS_VAZIAS = "match_empty_tabs_tabs_all.json"


def test_abas_vazias_viram_abas_ausentes(load_json, load_match):
    # Pegadinha 27 (748623, China Evolution Series 2026 Act 3): `tabs=all` sem dado no vlr.gg.
    raw_maps = load_json(ABAS_VAZIAS)["data"]["maps"]
    assert all(m["economy"] == {"teams": [], "rounds": []} for m in raw_maps)
    maps = load_match(ABAS_VAZIAS).maps
    assert all(m.economy is None and m.performance is None for m in maps)
    assert all(len(m.players) == 10 and m.has_sides for m in maps)


def test_economia_pela_metade_quebra(load_json):
    raw = load_json(ABAS_VAZIAS)
    full = load_json("match_bo5_2026_ot_tabs_all.json")["data"]["maps"][0]["economy"]
    raw["data"]["maps"][0]["economy"]["rounds"] = full["rounds"]  # rounds sem times
    with pytest.raises(ValidationError, match="economy.teams"):
        Response[MatchDetail].model_validate(raw)


def test_partida_orfa_de_evento_quebra(load_json):
    # Pegadinha 28 (756175): link do evento quebrado, `event.id` nulo e nome vazio. Rejeitada.
    raw = load_json("match_bo3_2x0_basic.json")
    raw["data"]["event"].update({"id": None, "name": "", "series": ":"})
    with pytest.raises(ValidationError, match="event.id"):
        Response[MatchDetail].model_validate(raw)


TAGS_MISTAS = "match_mixed_case_tags_tabs_all.json"


def test_tag_canonica_em_caixa_alta(load_json, load_match):
    # Pegadinha 29 (757797): o round diz "ARAS", o jogador diz "Aras", a economia diz "Arashi".
    raw = load_json(TAGS_MISTAS)["data"]["maps"][0]
    assert {p["teamTag"] for p in raw["players"]} == {"Aras", "BIDA"}
    assert {r["winner"] for r in raw["rounds"]} == {"ARAS", "BIDA"}
    map_ = load_match(TAGS_MISTAS).maps[0]
    assert {p.team_tag for p in map_.players} == {r.winner for r in map_.rounds} == {"ARAS", "BIDA"}
    assert [t.name for t in map_.economy.teams] == ["Arashi", "BIDA"]  # rótulo, não normalizado


NOTA_NO_VETO = "match_veto_note_tabs_all.json"


def test_nota_grudada_no_veto_e_separada(load_json, load_match):
    # Pegadinha 30 (698906): a nota editorial do vlr.gg vira `action: "note"` com o passo real
    # ("T1 ban Split") na última linha do texto.
    first, *_ = load_json(NOTA_NO_VETO)["data"]["picksBans"]["list"]
    assert first["action"] == "note" and first["map"].rstrip().endswith("T1 ban Split")
    steps = load_match(NOTA_NO_VETO).picks_bans.steps
    assert [(s.team, s.action, s.map) for s in steps][:2] == [
        ("T1", "ban", "Split"),
        ("DFM", "ban", "Breeze"),
    ]
    assert len(steps) == 7


def test_mapa_da_nota_de_lobby_remake_fica_marcado(load_match):
    # Pegadinha 36 (698906): "Map 3 stats are incomplete due to lobby remake." → o 3º mapa.
    maps = load_match(NOTA_NO_VETO).maps
    assert [(m.name, m.stats_incomplete) for m in maps] == [
        ("Sunset", False),
        ("Haven", False),
        ("Ascent", True),
    ]


def test_nota_de_estatistica_parcialmente_indisponivel_tambem_marca(load_json):
    # Variante da 724620 (VCT China Stage 2): "Map 3 stats are partially unavailable due to
    # external issues."
    raw = load_json(NOTA_NO_VETO)
    note = raw["data"]["picksBans"]["note"]
    raw["data"]["picksBans"]["note"] = note.replace(
        "Map 3 stats are incomplete due to lobby remake.",
        "Map 2 stats are partially unavailable due to external issues.",
    )
    maps = Response[MatchDetail].model_validate(raw).data.maps
    assert [m.stats_incomplete for m in maps] == [False, True, False]


def test_numeracao_da_nota_e_a_da_lista_original(load_json):
    # Mapa vazio descartado antes do mapa da nota não desloca a marcação.
    raw = load_json(NOTA_NO_VETO)
    sunset = raw["data"]["maps"][0]
    sunset["rounds"] = []
    for p in sunset["players"]:
        p["agents"] = []
    maps = Response[MatchDetail].model_validate(raw).data.maps
    assert [(m.name, m.stats_incomplete) for m in maps] == [("Haven", False), ("Ascent", True)]


def test_nota_sozinha_e_veto_vazio(load_json, load_match):
    # Pegadinha 30 (678049): sem veto no vlr.gg, a lista traz só a nota ("Map 1 stats are
    # incomplete due to lobby remake.").
    (only,) = load_json("match_veto_only_note_tabs_all.json")["data"]["picksBans"]["list"]
    assert only["action"] == "note"
    assert load_match("match_veto_only_note_tabs_all.json").picks_bans.steps == []


def test_nota_sem_passo_reconhecivel_quebra(load_json):
    raw = load_json(NOTA_NO_VETO)
    raw["data"]["picksBans"]["list"][0]["map"] = "Map 3 stats are incomplete due to lobby remake."
    with pytest.raises(ValidationError, match="action"):
        Response[MatchDetail].model_validate(raw)


SEM_DADOS = "match_map_without_data_tabs_all.json"


def test_mapa_sem_nenhum_dado_e_descartado(load_json, load_match):
    # Pegadinha 33 (669559, BO3 2–1): o Haven vem "played", 0–0, sem rounds e sem agentes.
    raw = load_json(SEM_DADOS)["data"]["maps"]
    assert [m["name"] for m in raw] == ["Lotus", "Ascent", "Haven"]
    detail = load_match(SEM_DADOS)
    assert [m.name for m in detail.maps] == ["Lotus", "Ascent"]
    assert detail.maps_without_data == 1  # o placar da série (2–1) ainda conta o Haven


def test_mapa_vazio_pela_metade_quebra(load_json):
    raw = load_json(SEM_DADOS)
    haven = raw["data"]["maps"][2]
    haven["players"][0]["agents"] = [{"name": "Omen"}]  # um agente, nenhum round
    with pytest.raises(ValidationError):
        Response[MatchDetail].model_validate(raw)


FUNDIDO = "match_merged_player_tabs_all.json"


def test_jogador_fundido_quebra(load_json):
    # Pegadinha 37 (656111): o VNSport aparece com 4 jogadores e "Bumble" com dois agentes.
    raw = load_json(FUNDIDO)
    (merged,) = (p for p in raw["data"]["maps"][0]["players"] if len(p["agents"]) > 1)
    assert [a["name"] for a in merged["agents"]] == ["Neon", "Tejo"]
    with pytest.raises(ValidationError, match="agents"):
        Response[MatchDetail].model_validate(raw)


@pytest.mark.parametrize(
    "name,edit,expected",
    [
        (FUNDIDO, None, "pegadinha 37"),
        ("match_bo3_2x0_basic.json", ("teams", 1, "id"), "pegadinha 24"),
        ("match_bo3_2x0_basic.json", ("event", "id"), "pegadinha 28"),
        ("match_bo3_2x0_basic.json", ("maps", 0, "players", 3, "id"), "pegadinha 32"),
    ],
    ids=["fundido", "tbd", "evento-orfao", "substituicao"],
)
def test_defeito_conhecido_da_fonte_e_reconhecido(load_json, name, edit, expected):
    raw = load_json(name)
    if edit:
        node = raw["data"]
        for key in edit[:-1]:
            node = node[key]
        node[edit[-1]] = None
    assert expected in known_source_defect(raw)


def test_chave_ausente_nao_e_defeito_conhecido(load_json):
    # Chave que some é formato novo: fica para o contrato, que conta para o aborto.
    raw = load_json("match_bo3_2x0_basic.json")
    del raw["data"]["teams"][1]["id"]
    assert known_source_defect(raw) is None


def test_fixture_valido_nao_tem_defeito(match_file, load_json):
    assert known_source_defect(load_json(match_file)) is None


def test_duracao_em_segundos(load_match):
    maps = {m.name: m for m in load_match("match_bo5_2026_ot_basic.json").maps}
    assert maps["Split"].duration_seconds == 42 * 60 + 6
    assert maps["Haven"].duration_seconds == 3600 + 3
