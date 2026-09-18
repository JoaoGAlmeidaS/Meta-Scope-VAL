"""Cliente HTTP de coleta — D4.

Responsabilidades:
    * timeout explícito em toda requisição
    * retry exponencial com jitter (tenacity), só para erros transitórios
    * rate limiter conservador — o projeto é hóspede do vlr.gg, não cliente
    * User-Agent identificável, com contato
    * cache em disco: buscar a mesma página duas vezes não toca a rede na segunda

Pronto quando: `fetch(url)` duas vezes seguidas gera exatamente uma requisição de rede.
"""

from __future__ import annotations

# TODO(D4): httpx.Client com transporte de cache (hishel) + tenacity + limiter.

USER_AGENT = "metascope-val/0.1 (+https://github.com/<user>/metascope-val)"
BASE_URL = "https://www.vlr.gg"

# Intervalo mínimo entre requisições, em segundos. Conservador de propósito.
MIN_INTERVAL_S = 1.5

# Diretório de cache em disco (fora do versionamento).
CACHE_DIR = ".cache/http"


def fetch(path: str) -> str:
    """Busca uma página do vlr.gg e devolve o HTML. Cacheia em disco."""
    raise NotImplementedError("D4")
