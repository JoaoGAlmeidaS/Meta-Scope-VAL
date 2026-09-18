"""Testes dos parsers contra HTML real — D3.

Cada campo extraído tem um teste. O objetivo é que uma mudança de layout do vlr.gg quebre
um teste, não uma análise três semanas depois.

Fixtures: `ingestion/tests/fixtures/*.html` (5–10 partidas reais, incluindo uma BO5, um
forfeit e um mapa incompleto).
"""

import pytest

pytestmark = pytest.mark.skip(reason="D3: aguardando fixtures e parsers auditados")


def test_extrai_composicao_por_mapa():
    """GATE do D2/D3: 5 agentes por time em cada mapa."""
    raise NotImplementedError


def test_extrai_veto():
    """Ordem do veto: ban/pick/decider, com o time responsável."""
    raise NotImplementedError


def test_extrai_rounds():
    """Placar round a round, com lado e resultado da pistol."""
    raise NotImplementedError
