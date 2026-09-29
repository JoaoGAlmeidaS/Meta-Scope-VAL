# DEVLOG

Regra diária: **um commit e três linhas** — o que fiz / o que quebrou / decisão tomada.

---

## D1 — Esqueleto

- **Fiz:** estrutura de pastas, `pyproject.toml` com `uv`, pre-commit (ruff + black),
  `Makefile` com alvos, README com as 8 perguntas de pesquisa, seção de decisões em
  `docs/projeto-valorant-data.md`.
- **Quebrou:** —
- **Decisão:** —

> *Pronto quando:* `make test` roda (mesmo sem testes) e o repo está no GitHub.

## D3 — Fixtures e testes de contrato

- **Fiz:** contrato Pydantic em `ingestion/schemas.py` (só campos consumidos, `extra="ignore"`),
  ponte tag → id por placar em `ingestion/bridge.py`, 142 testes sobre 9 fixtures reais (lado,
  ponte, veto, gabarito de agentes) com a rede bloqueada fora do marker `live`. Removi o
  resquício do scraping (`ingestion/vendor/`, `selectolax`) e alinhei docs aos nomes reais.
- **Quebrou:** nada no contrato: os 9 fixtures passaram sem afrouxar o modelo. Surpresas: a
  partida da VCL veio sem veto, e `roundsCt`/`roundsT` não contam o overtime.
- **Decisão:** ponte por placar como padrão (funciona sem abas, levanta erro se não fechar);
  `economy`/`performance` consumidos por mapa, não no nível da partida.

## D4 — Cliente de coleta

- **Fiz:** `ingestion/client.py` com httpx (timeout 30 s), tenacity (backoff em 429/502/503/504 e
  falha de transporte), rate limiter de 3–6 s que obedece `ratelimit-*` e `retry-after`, e cache
  de conteúdo em disco; 21 testes com transporte e relógio falsos, teste `live` implementado.
- **Quebrou:** API fora do ar; o teste `live` e a conferência do formato de `ratelimit-reset`
  ficaram pendentes. O teste pegou um bug: `max_age_s=0` servia cache gravado no mesmo instante.
- **Decisão:** cache próprio no lugar do hishel (validade é regra de domínio, não header HTTP);
  hishel removido das dependências.
