"""Cliente HTTP da API vlresports — D4.

Único ponto do projeto que chama a API. Responsabilidades:
    * timeout generoso em toda requisição (o detalhe de partida leva 3–5 s; o 502 chega em ~6 s)
    * retry exponencial com jitter (tenacity) em 429/502/503/504 e em falha de transporte
    * rate limiter conservador: 3–6 s entre o início de duas requisições, e pausa até o reset
      quando os headers `ratelimit-*` ou `retry-after` mandam esperar. A instância é pública e
      compartilhada, e o vlr.gg a estrangula abaixo do limite declarado (docs/fontes.md)
    * User-Agent identificável, com contato
    * cache de conteúdo em disco: buscar a mesma partida duas vezes não toca a rede na segunda

O cache não segue cabeçalhos HTTP: quem decide a validade é o coletor, pelo domínio. Partida
finalizada não muda (`max_age_s=None`, para sempre); listagem de evento em andamento muda
(`max_age_s` finito). Só respostas 200 com `status == "OK"` entram no cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from collections.abc import Callable
from functools import cache
from pathlib import Path
from urllib.parse import urlencode

import httpx
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)

USER_AGENT = "metascope-val/0.1 (+https://github.com/JoaoGAlmeidaS/Meta-Scope-VAL)"
BASE_URL = "https://vlr.orlandomm.net/api/v1"

# Intervalo entre o início de duas requisições: mínimo + jitter uniforme (3–6 s).
MIN_INTERVAL_S = 3.0
MAX_JITTER_S = 3.0

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_ATTEMPTS = 6
TRANSIENT_STATUS = frozenset({429, 502, 503, 504})

# Diretório de cache em disco (fora do versionamento: `.cache/` está no .gitignore).
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "api"


class ApiError(RuntimeError):
    """Resposta definitiva de erro: não adianta repetir (404, corpo sem `status: OK`...)."""


class TransientError(RuntimeError):
    """Erro que costuma passar sozinho; o retry tenta de novo."""


class RateLimiter:
    """Espaça requisições e respeita as pausas pedidas pelo servidor. Relógio injetável."""

    def __init__(
        self,
        min_interval_s: float,
        max_jitter_s: float,
        clock: Callable[[], float],
        sleep: Callable[[float], None],
        rng: random.Random,
    ) -> None:
        self._min = min_interval_s
        self._jitter = max_jitter_s
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self._next_at = float("-inf")

    def wait(self) -> None:
        delay = self._next_at - self._clock()
        if delay > 0:
            self._sleep(delay)
        self._next_at = self._clock() + self._min + self._rng.uniform(0, self._jitter)

    def pause_for(self, seconds: float) -> None:
        """Garante que a próxima requisição só sai daqui a `seconds`."""
        self._next_at = max(self._next_at, self._clock() + seconds)


class ContentCache:
    """Um arquivo JSON por requisição, com o horário da coleta. Escrita atômica."""

    def __init__(self, root: Path, clock: Callable[[], float]) -> None:
        self._root = root
        self._clock = clock

    def _file(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self._root / digest[:2] / f"{digest}.json"

    def get(self, key: str, max_age_s: float | None) -> dict | None:
        path = self._file(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            fetched_at, body = entry["fetched_at"], entry["body"]
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, KeyError, TypeError):
            log.warning("cache corrompido, descartado: %s", path)
            return None
        if max_age_s is not None and self._clock() - fetched_at >= max_age_s:
            return None
        return body

    def put(self, key: str, body: dict) -> None:
        path = self._file(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        entry = {"key": key, "fetched_at": self._clock(), "body": body}
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def _header_seconds(headers: httpx.Headers, name: str) -> float | None:
    try:
        return float(headers[name])
    except (KeyError, ValueError):
        return None


class ApiClient:
    """Cliente da vlresports. Transporte, relógio e sono são injetáveis para teste."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        cache_dir: Path = CACHE_DIR,
        transport: httpx.BaseTransport | None = None,
        min_interval_s: float = MIN_INTERVAL_S,
        max_jitter_s: float = MAX_JITTER_S,
        max_attempts: int = MAX_ATTEMPTS,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
            transport=transport,
        )
        self._cache = ContentCache(cache_dir, wall_clock)
        self._limiter = RateLimiter(
            min_interval_s, max_jitter_s, clock, sleep, rng or random.Random()
        )
        self._retrying = Retrying(
            retry=retry_if_exception_type((TransientError, httpx.TransportError)),
            wait=wait_exponential_jitter(initial=5, max=120, jitter=5),
            stop=stop_after_attempt(max_attempts),
            sleep=sleep,
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        self.network_requests = 0

    def fetch(
        self, path: str, params: dict | None = None, *, max_age_s: float | None = None
    ) -> dict:
        """JSON de um endpoint. `max_age_s=None`: cache vale para sempre; `0`: sempre a rede."""
        query = urlencode(sorted((params or {}).items()))
        key = f"{path}?{query}" if query else path

        cached = self._cache.get(key, max_age_s)
        if cached is not None:
            return cached

        body = self._retrying(self._request, path, params)
        self._cache.put(key, body)
        return body

    def _request(self, path: str, params: dict | None) -> dict:
        self._limiter.wait()
        self.network_requests += 1
        response = self._http.get(path, params=params)
        self._obey_rate_headers(response)

        if response.status_code in TRANSIENT_STATUS:
            raise TransientError(f"{response.status_code} em {path}")
        if response.status_code != 200:
            raise ApiError(f"{response.status_code} em {path}: {response.text[:200]}")
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise ApiError(f"resposta não é JSON em {path}") from exc
        if not isinstance(body, dict) or body.get("status") != "OK":
            raise ApiError(f"status diferente de OK em {path}: {str(body)[:200]}")
        return body

    def _obey_rate_headers(self, response: httpx.Response) -> None:
        retry_after = _header_seconds(response.headers, "retry-after")
        if retry_after is not None:
            self._limiter.pause_for(retry_after)
        remaining = _header_seconds(response.headers, "ratelimit-remaining")
        reset = _header_seconds(response.headers, "ratelimit-reset")
        if remaining is not None and reset is not None and remaining <= 1:
            log.info("cota da janela esgotando; pausa de %.0f s", reset)
            self._limiter.pause_for(reset)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@cache
def _default_client() -> ApiClient:
    return ApiClient()


def fetch(path: str, params: dict | None = None, *, max_age_s: float | None = None) -> dict:
    """Atalho para o cliente padrão do processo."""
    return _default_client().fetch(path, params, max_age_s=max_age_s)
