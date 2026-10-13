"""Loader de fixtures e bloqueio de rede para os testes da ingestão.

Fixtures são respostas reais da API em `fixtures/`, gravadas no D2/D3. Nenhum teste fora do
marker `live` pode abrir conexão: o bloqueio abaixo transforma qualquer tentativa em erro.
"""

from __future__ import annotations

import json
import socket
from functools import cache
from pathlib import Path

import pytest

from ingestion.schemas import Map, MatchDetail, Response

FIXTURES = Path(__file__).parent / "fixtures"

MATCH_FILES = [
    "match_bo5_2022_basic.json",
    "match_bo5_2026_ot_basic.json",
    "match_bo5_2026_ot_tabs_all.json",
    "match_bo3_2x0_basic.json",
    "match_vcl_brasil_basic.json",
    "match_vcl_map_without_sides_tabs_all.json",
    "match_mixed_case_tags_tabs_all.json",
    "match_veto_note_tabs_all.json",
    "match_cn_legal_name_tabs_all.json",
    "match_team_without_tag_tabs_all.json",
]


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@cache
def _load_match(name: str) -> MatchDetail:
    # Modelos são imutáveis (frozen), então o cache é seguro entre testes.
    return Response[MatchDetail].model_validate(_load_json(name)).data


def _map_params() -> list:
    # Ids lidos do JSON cru: a coleta não depende do contrato, que é testado à parte.
    return [
        pytest.param((name, i), id=f"{Path(name).stem}-{m['name']}")
        for name in MATCH_FILES
        for i, m in enumerate(_load_json(name)["data"]["maps"])
    ]


@pytest.fixture
def load_json():
    """Fábrica: nome do arquivo → dict cru (cópia nova a cada chamada)."""
    return _load_json


@pytest.fixture
def load_match():
    """Fábrica: nome do arquivo → `MatchDetail` validado."""
    return _load_match


# Pedidos com `tabs=all`, mas o vlr.gg não tem economia nem performance (pegadinha 27).
EMPTY_TABS = {"match_cn_legal_name_tabs_all.json"}


@pytest.fixture(params=MATCH_FILES, ids=lambda n: Path(n).stem)
def match_file(request) -> str:
    """Cada fixture de detalhe de partida."""
    return request.param


@pytest.fixture
def has_economy(match_file) -> bool:
    """O fixture traz economia e performance: pedido com abas, e o vlr.gg tem o dado."""
    return match_file.endswith("_tabs_all.json") and match_file not in EMPTY_TABS


@pytest.fixture
def match(match_file) -> MatchDetail:
    return _load_match(match_file)


@pytest.fixture(params=_map_params())
def match_map(request) -> tuple[MatchDetail, Map]:
    """Cada mapa de cada fixture de partida, com a partida a que pertence."""
    name, i = request.param
    detail = _load_match(name)
    return detail, detail.maps[i]


@pytest.fixture(autouse=True)
def _sem_rede(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return

    def _bloqueia(*args, **kwargs):
        raise RuntimeError("teste tentou acessar a rede; use um fixture ou o marker `live`")

    monkeypatch.setattr(socket.socket, "connect", _bloqueia)
    monkeypatch.setattr(socket, "getaddrinfo", _bloqueia)
