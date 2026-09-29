"""Pegadinha 12: `/events/{id}/agents` é agregado arredondado, usado como gabarito no D13."""

from __future__ import annotations

import pytest

from ingestion.schemas import EventAgentsMap, Response


@pytest.fixture
def rows(load_json) -> list[EventAgentsMap]:
    raw = load_json("event_agents_vct_americas_s2_2026.json")
    return Response[list[EventAgentsMap]].model_validate(raw).data


def test_soma_de_played_bate_com_all(rows):
    (total,) = (r for r in rows if r.map == "All")
    assert sum(r.played for r in rows if r.map != "All") == total.played


def test_pick_rate_soma_cerca_de_500_por_mapa(rows):
    # Percentual de composições time-mapa: 5 agentes por composição, com arredondamento.
    for r in rows:
        assert 485 <= sum(a.pick_rate for a in r.agents) <= 515, r.map
