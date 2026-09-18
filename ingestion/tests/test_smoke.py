"""Teste de fumaça — garante que `make test` roda desde o D1."""


def test_pacote_importa():
    import ingestion

    assert ingestion is not None
