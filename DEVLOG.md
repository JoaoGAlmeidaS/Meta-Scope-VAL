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

## D5 — Eventos e listagem de partidas

- **Fiz:** coletor de `/events` (tier vct e vcl × 4 regiões + sem filtro), listagem de partidas e
  gabarito de agentes por evento, gravados em Parquet com schema fechado (`ingestion/lake.py`);
  janela e aquecimento lidos do `dbt_project.yml` (`ingestion/config.py`). Coleta real: {EVENTOS}
  eventos no escopo desde 2023, {PARTIDAS} partidas concluídas.
- **Quebrou:** a cota de 30/min é da instância inteira, não do cliente: vazão real de ~6–10 req/min,
  com 429. Internacionais de 2023–2024 aparecem só na região-sede, e partida `upcoming` vem com
  `score: null` (contrato ajustado com fixture novo).
- **Decisão:** histórico desde 2023, China Evolution Series fora, lake no HF privado; partição
  `season=YYYY` com um arquivo por evento (reescrever é o upsert).

## D6 — Detalhe de partida

- **Fiz:** `ingestion/flatten.py` achata o detalhe em `raw_match`, `raw_map`, `raw_veto`,
  `raw_round` e `raw_player_map` (tag → id pela ponte, colunas `team1_*`/`team2_*` na ordem da
  partida), com `raw_reject` e o JSON bruto em `_json/`. A BO5 734308 sai nas cinco tabelas e o
  DuckDB lê com os tipos do schema.
- **Quebrou:** nada nos fixtures; ponte que não fecha num mapa agora anula os ids daquele mapa em
  vez de derrubar a partida.
- **Decisão:** evento gravado inteiro no fim; rejeição não para a coleta, mas 5 seguidas abortam
  (sinal de mudança de formato). `tabs=all` pela data da listagem contra janela + aquecimento.

## D7 — Backfill e lake

- **Fiz:** `backfill` do evento mais recente para o mais antigo, retomável (evento completo no
  lake é pulado, o resto vem do cache), `make backfill` com log em `logs/`, e `lake push|pull` no
  dataset privado do HF. {VALIDACAO}
- **Quebrou:** {D7_QUEBROU}
- **Decisão:** o backfill roda no tmux do usuário; o login do HF (`hf auth login`) é passo manual.

## D8 — Região dos times e patches

- **Fiz:** `patches.csv` com 89 patches (5.12 a 13.06) tirados do CMS oficial da Riot, e
  `event_overrides.csv` com {OVERRIDES} linhas; testes do dbt nos dois seeds (ordem dos patches,
  valores aceitos, reclassificação que muda algo).
- **Quebrou:** a regra "evento em várias regiões = internacional" falha antes de 2025 (5 eventos
  reclassificados à mão) e a VCL chinesa aparece em duas regiões.
- **Decisão:** região do time = região do evento doméstico mais recente antes da partida (vai para
  o `dim_team` no D10); qualificatórias abertas fora, marcadas como julgamento.
