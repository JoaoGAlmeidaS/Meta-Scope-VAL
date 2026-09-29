"""Cliente da API (D4) contra um transporte falso: sem rede e sem dormir de verdade.

Pronto quando: buscar a mesma partida duas vezes não toca a rede na segunda.
"""

from __future__ import annotations

import random
from collections.abc import Callable

import httpx
import pytest

from ingestion.client import USER_AGENT, ApiClient, ApiError, TransientError
from ingestion.schemas import MatchDetail, Response

MATCH_PATH = "/matches/734308"


class FakeClock:
    """Relógio que só anda quando alguém dorme (ou o teste avança)."""

    def __init__(self) -> None:
        self.now = 1_800_000_000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeApi:
    """Transporte roteirizado: cada chamada consome a próxima resposta da fila."""

    def __init__(self, *responses: httpx.Response | Callable[[httpx.Request], httpx.Response]):
        self._queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        nxt = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return nxt(request) if callable(nxt) else nxt


def ok(body: dict | None = None, **headers: str) -> httpx.Response:
    return httpx.Response(200, json=body or {"status": "OK", "data": {}}, headers=headers)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_client(tmp_path, clock):
    clients = []

    def _make(api: FakeApi, **kwargs) -> ApiClient:
        client = ApiClient(
            cache_dir=tmp_path / "cache",
            transport=httpx.MockTransport(api),
            clock=clock,
            wall_clock=clock,
            sleep=clock.sleep,
            rng=random.Random(0),
            **kwargs,
        )
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()


# --- cache ------------------------------------------------------------------------------------


def test_mesma_partida_duas_vezes_uma_requisicao(make_client, load_json):
    api = FakeApi(ok(load_json("match_bo5_2026_ot_basic.json")))
    client = make_client(api)

    first = client.fetch(MATCH_PATH)
    second = client.fetch(MATCH_PATH)

    assert len(api.requests) == 1
    assert client.network_requests == 1
    assert first == second
    Response[MatchDetail].model_validate(second)


def test_cache_persiste_entre_clientes(make_client):
    api = FakeApi(ok())
    make_client(api).fetch(MATCH_PATH)
    make_client(api).fetch(MATCH_PATH)
    assert len(api.requests) == 1


def test_chave_do_cache_inclui_params_sem_depender_da_ordem(make_client):
    api = FakeApi(ok())
    client = make_client(api)
    client.fetch("/events", {"tier": "vct", "page": 1})
    client.fetch("/events", {"page": 1, "tier": "vct"})
    client.fetch("/events", {"tier": "vcl", "page": 1})
    assert len(api.requests) == 2


def test_max_age_expira_o_cache(make_client, clock):
    api = FakeApi(ok())
    client = make_client(api)
    client.fetch("/events/2977/matches", max_age_s=3600)
    clock.now += 3599
    client.fetch("/events/2977/matches", max_age_s=3600)
    assert len(api.requests) == 1
    clock.now += 2
    client.fetch("/events/2977/matches", max_age_s=3600)
    assert len(api.requests) == 2


def test_max_age_zero_sempre_vai_a_rede(make_client):
    api = FakeApi(ok())
    client = make_client(api)
    client.fetch(MATCH_PATH)
    client.fetch(MATCH_PATH, max_age_s=0)
    assert len(api.requests) == 2


def test_cache_corrompido_vira_miss(make_client, tmp_path):
    api = FakeApi(ok())
    client = make_client(api)
    client.fetch(MATCH_PATH)
    (entry,) = (tmp_path / "cache").rglob("*.json")
    entry.write_text("{corrompido", encoding="utf-8")
    assert client.fetch(MATCH_PATH) == {"status": "OK", "data": {}}
    assert len(api.requests) == 2


def test_erro_nao_entra_no_cache(make_client, tmp_path):
    api = FakeApi(httpx.Response(404, text="not found"))
    client = make_client(api)
    with pytest.raises(ApiError):
        client.fetch(MATCH_PATH)
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_corpo_sem_status_ok_e_erro_definitivo(make_client):
    api = FakeApi(ok({"status": "error", "message": "match not found"}))
    with pytest.raises(ApiError):
        make_client(api).fetch(MATCH_PATH)
    assert len(api.requests) == 1


# --- retry ------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_erro_transitorio_tenta_de_novo(make_client, clock, status):
    api = FakeApi(httpx.Response(status), ok())
    body = make_client(api).fetch(MATCH_PATH)
    assert body["status"] == "OK"
    assert len(api.requests) == 2
    assert clock.sleeps, "retry sem espera"


def test_falha_de_transporte_tenta_de_novo(make_client):
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento demais", request=request)

    api = FakeApi(timeout, ok())
    assert make_client(api).fetch(MATCH_PATH)["status"] == "OK"
    assert len(api.requests) == 2


def test_desiste_depois_do_limite_de_tentativas(make_client):
    api = FakeApi(httpx.Response(503))
    with pytest.raises(TransientError):
        make_client(api, max_attempts=3).fetch(MATCH_PATH)
    assert len(api.requests) == 3


def test_erro_definitivo_nao_repete(make_client):
    api = FakeApi(httpx.Response(404))
    with pytest.raises(ApiError):
        make_client(api).fetch(MATCH_PATH)
    assert len(api.requests) == 1


def test_backoff_cresce_entre_tentativas(make_client, clock):
    api = FakeApi(httpx.Response(503), httpx.Response(503), httpx.Response(503), ok())
    make_client(api, min_interval_s=0, max_jitter_s=0).fetch(MATCH_PATH)
    assert len(clock.sleeps) == 3
    # Exponencial a partir de 5 s, com até 5 s de jitter: 5–10, 10–15, 20–25.
    for sleep, base in zip(clock.sleeps, [5, 10, 20], strict=True):
        assert base <= sleep <= base + 5


# --- rate limit -------------------------------------------------------------------------------


def _timed_ok(clock: FakeClock) -> tuple[Callable[[httpx.Request], httpx.Response], list[float]]:
    """Resposta OK que anota o instante de cada requisição."""
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock.now)
        return ok()

    return handler, times


def test_espacamento_de_3_a_6_s_entre_requisicoes(make_client, clock):
    handler, times = _timed_ok(clock)
    client = make_client(FakeApi(handler))
    for i in range(10):
        client.fetch(f"/matches/{i}")
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    assert all(3.0 <= g <= 6.0 for g in gaps), gaps


def test_cache_hit_nao_espera(make_client, clock):
    client = make_client(FakeApi(ok()))
    client.fetch(MATCH_PATH)
    waited = len(clock.sleeps)
    client.fetch(MATCH_PATH)
    assert len(clock.sleeps) == waited


def test_cota_esgotada_pausa_ate_o_reset(make_client, clock):
    handler, times = _timed_ok(clock)
    api = FakeApi(ok(**{"ratelimit-remaining": "0", "ratelimit-reset": "42"}), handler)
    client = make_client(api)
    start = clock.now
    client.fetch("/matches/1")
    client.fetch("/matches/2")
    assert times[0] - start >= 42


def test_retry_after_do_429_e_respeitado(make_client, clock):
    handler, times = _timed_ok(clock)
    api = FakeApi(httpx.Response(429, headers={"retry-after": "90"}), handler)
    start = clock.now
    make_client(api).fetch(MATCH_PATH)
    assert times[0] - start >= 90


# --- identificação ----------------------------------------------------------------------------


def test_user_agent_e_timeout(make_client):
    api = FakeApi(ok())
    make_client(api).fetch(MATCH_PATH, {"tabs": "all"})
    (request,) = api.requests
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.url.path.endswith(MATCH_PATH)
    assert request.url.params["tabs"] == "all"
    assert request.extensions["timeout"]["read"] >= 30
