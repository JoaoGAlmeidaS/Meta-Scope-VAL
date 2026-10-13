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
  janela e aquecimento lidos do `dbt_project.yml` (`ingestion/config.py`). Coleta real: 548
  eventos candidatos vct+vcl desde 2023; a primeira passada gravou 120 antes de cair (ver D9).
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
  dataset privado do HF. Validação real (feita no D9): 2977 com 60 partidas em 5 min, zero
  rejeições; 2962 (Challengers Brasil) com 66, das quais 10 caíram no contrato.
- **Quebrou:** a coleta de eventos morreu num 502 persistente do gabarito de um único evento
  (`/events/1309/agents`), e o índice `raw_event` só era gravado no fim. Corrigido no D9.
- **Decisão:** o backfill roda no tmux do usuário; o login do HF (`hf auth login`) é passo manual.

## D8 — Região dos times e patches

- **Fiz:** `patches.csv` com 89 patches (5.12 a 13.06) tirados do CMS oficial da Riot, e
  `event_overrides.csv` com 33 linhas; testes do dbt nos dois seeds (ordem dos patches,
  valores aceitos, reclassificação que muda algo).
- **Quebrou:** a regra "evento em várias regiões = internacional" falha antes de 2025 (5 eventos
  reclassificados à mão) e a VCL chinesa aparece em duas regiões.
- **Decisão:** região do time = região do evento doméstico mais recente antes da partida (vai para
  o `dim_team` no D10); qualificatórias abertas fora, marcadas como julgamento.

## D9 — dbt + DuckDB

- **Fiz:** sources no lake por `LAKE_DIR` (Hive por temporada, `union_by_name`), nove `stg_*` com
  tipos e nomes padronizados e deduplicação por chave, DuckDB em UTC; lake de fixtures
  (`ingestion/fixture_lake.py`) passando pelo backfill de verdade com um cliente offline.
- **Quebrou:** a coleta de eventos do D5 (gabarito opcional derrubava tudo; índice perdido na
  queda). Agora gabarito falho não para nada, 3 listagens seguidas sem resposta abortam, o índice
  é gravado mesmo na queda e partida `unavailable` volta para a fila na execução seguinte.
- **Decisão:** CI em dois trilhos (fixtures sem segredo em todo push; lake real só com
  `HF_TOKEN`); o dbt sempre roda de dentro de `dbt/`.

## D10 — Dimensões

- **Fiz:** `dim_event` (overrides aplicados), `dim_team`, `dim_player`, `dim_map`, `dim_patch`,
  macros de janela (`as_of_date`, `analysis_window_start`, `elo_warmup_start`) e a região do time
  na época por ASOF JOIN (`int_team_match_regions`), com teste unitário de time que muda de região.
- **Quebrou:** nada; os times de 2022 do fixture ficam sem região (só jogaram internacional), como
  manda a regra.
- **Decisão:** dimensão é retrato (nome, tag e região mais recentes); o nome e a tag da época
  ficam nos fatos, sem SCD. `AS_OF_DATE` fixa a janela no CI.

## D11 — Fatos

- **Fiz:** `fct_match`, `fct_map`, `fct_veto`, `fct_round`, `fct_player_map` e `fct_composition`,
  com flags de janela e de exclusão em vez de filtro. O lado de cada time sai do lado do vencedor
  round a round, overtime incluído; pistol vira `pistol` na economia.
- **Quebrou:** um `case ... else` punha o perdedor no ataque quando o lado vinha nulo; pego pelo
  caso da pegadinha 22 e coberto no teste unitário do `fct_round`.
- **Decisão:** fatos cobrem todo o histórico coletado; janela e exclusão são filtro dos marts de
  análise (D16), e o drift (D17) lê tudo.

## D12 — Dagster

- **Fiz:** multi-asset `lake/raw_*` particionado por temporada, dbt via dagster-dbt (os testes do
  dbt viram asset checks, os sources viram os assets da coleta), checks próprios do lake, jobs
  `ingest` e `build`, e a API como resource (`VlrApi`), trocada pelo cliente offline nos testes.
- **Quebrou:** `from __future__ import annotations` transforma a anotação do `context` em string e
  o Dagster recusa; tirado só de `assets.py`.
- **Decisão:** gate do D12 cumprido: o job `build` materializou tudo (`RUN_SUCCESS`); o Dagster
  fica. `make` e o Actions chamam o Dagster.

## D13 — Qualidade

- **Fiz:** testes de rounds × placar, lado × `roundsCt`/`roundsT`, troca no intervalo, pistol
  fora do eco, completude da coleta, pick sem jogo, mapas × placar da série; validação cruzada
  com o gabarito do vlr.gg e o seed `validation_exceptions`. No evento real 2977: 9/9 mapas
  jogados, 261/261 pick rates e 8/8 vitórias no ataque idênticos ao gabarito.
- **Quebrou:** 10 de 66 partidas do Challengers Brasil caíram no contrato: mapas sem histórico de
  lado (pegadinha 22), `loadout` nulo na economia (23) e um adversário "TBD" sem id (24).
- **Decisão:** mapa sem lado entra (tudo ou nada, contrato estrito), `loadout` nulo aceito, time
  sem id continua rejeitado. O `atkWinRate` do vlr.gg exclui o overtime, e a validação também.

## D14 — CI e marco

- **Fiz:** workflow com o trilho de fixtures em todo push (lint, pytest, `make build-fixtures`) e o
  trilho real manual (lake-pull → ingest → lake-push → build); `make build` reconstrói o warehouse
  do zero pelo Dagster e publica o dbt docs estático em `dist/lineage`.
- **Quebrou:** nada no marco: `make clean` → lint → 276 testes → `make build-fixtures` verde.
- **Decisão:** deploy no Pages e `schedule` ficam comentados até o D29; o CI guarda `dist/` como
  artefato. Coleta do CI é só incremental e pode falhar sem derrubar o build.

## Pendências do Bloco 1 — coleta completa e lake real (05/10)

- **Fiz:** índice completo com a API de volta (o índice tinha 2), backfill disparado no tmux, primeiro
  push do lake no HF e o primeiro `make build` verde sobre o lake real (33 eventos de 2026), com 12
  pegadinhas novas (26–37). Escopo da coleta reduzido a 2025+ e sem o tier 2 chinês (154 eventos,
  ~7.329 partidas).
- **Quebrou:** a coleta abortou duas vezes (404 em partida apagada, abas vazias) e o build achou
  ponte quebrada por caixa de tag e por razão social chinesa, mapas de lobby remake fora do gabarito
  e jogador fundido; um build sobre o lake vivo leu um evento pela metade.
- **Decisão:** defeito conhecido da fonte vira rejeição `source`, que não aborta; validação aceita
  as duas leituras do mapa refeito e só valida eventos em escopo; jogador fundido rejeita a partida;
  VCT China 2978 com exceções escritas; build sempre sobre cópia do lake. Coleta própria só desde
  2025: o pré-2025 do drift vem de dataset pronto; metadados de 2023–2024 removidos do lake e do HF.
  VCL China e China Evolution Series fora da coleta (`is_china_tier2`), também removidos.

## Coleta 2025+ concluída (06/10)

- **Fiz:** backfill desde 2025 terminou às 03h30 (7.329 listadas: 7.004 gravadas, 325 rejeitadas
  com motivo, 0 faltando) e o lake está idêntico no HF. O build no lake completo achou e corrigi:
  formato "2 maps" com empate (38), veto digitado errado duplicando mapa (39) e W.O. de mapa no meio
  da série, agora contado em `raw_match.n_maps_without_data` (33); lake regravado do cache.
- **Quebrou:** a validação cruzada ainda diverge em 9 eventos (variantes da nota de lobby remake e
  "Map N" fora da posição; China; Japan Finals) e 17 partidas caíram no contrato por formatos novos.
- **Decisão:** placar da série e pick sem jogo descontam os mapas de W.O.; empate só em mapas fixos;
  pendências da validação registradas em `docs/fontes.md` para a próxima sessão.

## Fechamento do Bloco 2 (07/10)

- **Fiz:** `make build` verde sobre o lake completo 2025+ (7.019 partidas; HF idêntico). Showmatches
  fora da análise (41), time sem tag recuperado (40), método por round (31), mapa refeito pela ordem
  do veto e mapa sem estatística fora da validação (36); qualificatórias do SEA excluídas por
  julgamento; 47 exceções escritas, cada uma com motivo.
- **Quebrou:** o gabarito do vlr.gg é inconsistente (ora conta o mapa refeito, ora não; conta o
  showmatch no Japan Finals e não no VCT) e a China segue com mapas a mais sem explicação.
- **Decisão:** validação aceita a leitura que bate e escreve o resto como exceção; showmatch liga
  `is_excluded`. Bloco 3 liberado depois do commit e do 1º CI verde no GitHub.
