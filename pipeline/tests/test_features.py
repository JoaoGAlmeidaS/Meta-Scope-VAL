"""Testes de features — o anti-vazamento é o que importa aqui (D16)."""

import pytest

pytestmark = pytest.mark.skip(reason="D15/D16")


def test_elo_soma_zero():
    """A atualização de Elo conserva a soma dos ratings."""
    raise NotImplementedError
