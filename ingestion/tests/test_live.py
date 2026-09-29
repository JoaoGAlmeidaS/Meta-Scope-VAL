"""Testes contra a API real. Fora da execução padrão; rode com `uv run pytest -m live`.

Cada teste usa um cache novo em `tmp_path`, para que a primeira busca vá mesmo à rede.
"""

import pytest

from ingestion.client import ApiClient
from ingestion.schemas import MatchDetail, Response

pytestmark = pytest.mark.live


def test_partida_real_passa_no_contrato_e_a_segunda_busca_vem_do_cache(tmp_path):
    with ApiClient(cache_dir=tmp_path) as client:
        first = client.fetch("/matches/734308")
        second = client.fetch("/matches/734308")

    assert client.network_requests == 1
    assert first == second
    detail = Response[MatchDetail].model_validate(first).data
    assert detail.id == "734308"
    assert len(detail.maps) == 5
