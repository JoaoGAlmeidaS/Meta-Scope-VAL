# CLAUDE.md

Meta-Scope-VAL: plataforma de análise estatística do cenário competitivo de VALORANT. Pipeline
próprio consumindo a API vlresports, warehouse em dbt, rating Elo com previsões e site estático
no GitHub Pages.

Projeto de portfólio. Prioridades: **engenharia de dados → produto → análise estatística → ML (pós-D30)**.

## Comandos

```bash
make build           # warehouse do zero pelo Dagster (dbt + checks) + dbt docs em dist/lineage
make build-fixtures  # o mesmo sobre o lake de fixtures (trilho de CI sem segredo)
make test            # pytest; os testes do Dagster pedem `make dbt-deps` antes
make lint            # ruff + black
make events          # índice de eventos, listagens de partidas e gabarito → data/lake
make backfill        # coleta local desde 2025, do mais recente ao mais antigo (horas: tmux)
make ingest          # coleta uma temporada pelo Dagster (SEASON=2026 por padrão: a corrente)
make lake-push       # data/lake → dataset privado no Hugging Face (requer `hf auth login`)
make lake-pull       # dataset do Hugging Face → data/lake
make seed            # dbt deps + seeds com testes
make dbt-build       # dbt build direto, sem Dagster (depuração)
make dagster-dev     # UI local do Dagster, histórico em .dagster/
make serve           # python -m http.server -d dist
uv sync              # dependências
```

Nunca `pip install`. Dependência nova entra por `uv add`. Rode ferramentas com `uv run`.

O dbt roda **de dentro de `dbt/`** (`cd dbt && uv run dbt ...`): o perfil e o caminho padrão do
lake são relativos a essa pasta. `LAKE_DIR` (absoluto) aponta o lake para o Python e para o dbt;
`AS_OF_DATE` fixa a data de referência da janela (vazio = hoje). O Makefile exporta os dois.

## Arquitetura em uma frase

API vlresports → coletor Python → Parquet no lake → dbt sobre DuckDB → Elo e análises →
JSONs pré-computados → site estático. Dagster define os assets, GitHub Actions dispara.

Lake: `data/lake/{tabela}/season=YYYY/{event_id}.parquet` (chave Hive `season`, um arquivo por
evento), JSON bruto em `data/lake/_json/`, espelhado num dataset **privado** do Hugging Face.

Dagster (`dagster_defs/`): multi-asset `lake/raw_*` particionado por temporada (a coleta) →
assets do dbt via dagster-dbt (os sources `lake.raw_*` são os mesmos assets; testes do dbt viram
asset checks). Jobs `ingest` e `build`; o `make` e o Actions chamam esses jobs, nunca scripts
paralelos. A API entra como resource (`VlrApi`), trocada pelo cliente offline nos testes.

CI em dois trilhos: todo push roda lint, pytest e `make build-fixtures` sobre o lake de fixtures
(`ingestion/fixture_lake.py`, gerado dos JSONs do repo pelo backfill de verdade); o trilho real
(lake-pull → ingest → lake-push → build) é manual e exige `HF_TOKEN`.

## Regras invioláveis

Decisões fechadas e documentadas em `docs/projeto-valorant-data.md`. Não sugira reabrir sem motivo novo.

- **Janela de análise: 12 meses.** Todo mart de análise filtra pela variável dbt
  `analysis_window_months`. Nunca hardcode a janela. Exceções: aquecimento do Elo e o mart de drift.
- **Coleta própria desde 2025, análise restrita.** O backfill vai de 2025 até hoje, do mais
  recente para o mais antigo (`HISTORY_SINCE` em `ingestion/config.py`); o filtro acontece no dbt.
  Janela e aquecimento do Elo cabem em 2025+. O histórico anterior, que só o drift (D17) usa, vem
  de um dataset pronto importado à parte, nunca de coleta na instância pública. O tier 2 chinês
  (VCL China e China Evolution Series) fica fora da coleta (`collectors.is_china_tier2`): plataformas
  de terceiros, dados faltando. Fora isso, a coleta não aplica overrides: exclusão e
  reclassificação de evento vivem no seed `event_overrides.csv`.
- **Não existe backend.** Nada de FastAPI, servidor ou banco em produção. Se algo parece exigir
  servidor, pré-compute.
- **Sem modelo treinado nos 30 dias.** Previsões usam a probabilidade do Elo. Não proponha
  LightGBM, scikit-learn ou treino antes do D30.
- **DuckDB é engine, não banco.** Não sugira Postgres.
- **Transformação é em SQL no dbt**, não em pandas.
- **Notebooks usam matplotlib.** Interativo existe só no site.
- **Dados não entram no Git.** Parquet vai para o lake; só fixtures JSON ficam no repo.

## Regras de dados

- **Elo sempre pré-partida:** o rating usado para prever ou avaliar uma partida é o de antes dela.
- **Calibração** se mede com log loss, Brier e curva. Acurácia é secundária.
- **Todo número publicado leva intervalo de confiança.** Inconclusivo é resultado válido.
- **Composição sempre com shrinkage**, por mapa e patch, controlando força do time.
- **Idempotência:** rodar duas vezes não duplica linha. Upsert por id; no lake, reescrever o
  arquivo do evento é o upsert.
- **Particionamento por temporada** (`season`) no lake e nos assets do Dagster.
- **Janela e aquecimento** (`analysis_window_months`, `elo_warmup_months`) ficam só em
  `dbt/dbt_project.yml`; o Python lê por `ingestion/config.py`. Elas também decidem o `tabs=all`.
- **Patch sai do seed `patches.csv` pela data da partida.** A API não expõe o patch; torneio que
  trava patch anterior fica mal atribuído (limitação documentada).
- **Região do time** = região do evento doméstico mais recente que ele disputou antes da partida
  (`int_team_match_regions`, ASOF JOIN). Internacional e evento excluído não contam.
- **Dimensões vêm das partidas.** `dim_player` e `dim_team` saem de `raw_player_map` e `raw_match`.
  Nunca construa dimensão a partir de `/players` ou `/teams`: são leaderboard e ranking, não cadastros.
- **Dimensão é retrato; a época fica no fato.** `dim_*` tem nome, tag e região mais recentes; o
  nome e a tag da época estão nos `fct_*`. Sem SCD.
- **Fatos cobrem todo o histórico** e carregam `is_excluded` e `is_in_analysis_window`; quem filtra
  são os marts de análise (`mart_*`). A janela vem das macros de `dbt/macros/window.sql`.
- **Lado só onde existe.** Mapa sem histórico de lado (`has_round_sides = false`) entra no placar,
  na composição e no Elo, e fica fora de qualquer análise de lado.
- **Exceção de qualidade é escrita.** Divergência aceita nos testes do D13 vai para o seed
  `validation_exceptions.csv`, com motivo; o teste falha em qualquer outra.

## Particularidades da API (detalhes em `docs/fontes.md`)

- `rounds[].side` é o lado de **quem venceu** o round.
- `roundsCt` e `roundsT` contam só os rounds 1–24; `score` inclui o overtime.
- Time aparece como id, nome e tag. A ponte tag → id é por placar (`ingestion/bridge.py`): funciona
  sem abas, que é o caso do histórico. A posicional (`economy.teams[i]` ↔ `teams[i]`) só existe com
  `tabs` e concorda com ela (testado). A chave é sempre o `id`.
- Veto pode vir vazio (partida VCL 707490), e o mapa decisivo não jogado some de `maps[]`.
- Multikills e clutches por mapa podem vir zerados; não use sem verificar.
- Pistol (rounds 1 e 13) vem classificado como `eco` — exclua das análises de economia.
- Kill matrix e `performance` identificam jogador por nome, sem id.
- Force tipos no schema: `rating` pode vir inteiro, `duration` mistura formatos, `limit` vem como string.
- `teamTag` em `/players` é o time atual; jogador sem time recebe o próprio nome como tag.
- Região do evento vem do filtro `region` de `/events`: evento em mais de uma região é internacional.
  Antes de 2025, Masters e Champions aparecem só na região-sede, e a VCL chinesa aparece em `china`
  e `pacific`; o seed de overrides corrige.
- Nome de evento nem sempre tem ano (Challengers 2023, circuito 2021–2022): a temporada vem da data
  da primeira partida listada.
- Partida `upcoming` na listagem do evento vem com `score: null`.
- A cota de 30/min é compartilhada por todos os usuários da instância: vazão real de ~6–12 req/min.
- Mapa pode vir sem histórico de lado: `side`/`method` nulos em todo round e `roundsCt`/`roundsT`
  nulos. Tudo ou nada por grupo: lado (sides + contadores) e método podem faltar separadamente,
  nunca pela metade. O vencedor de cada round continua vindo.
- Nota editorial do vlr.gg pode vir grudada no 1º passo do veto (`action: "note"`): o contrato
  recupera o passo pela última linha do texto; nota sozinha na lista é veto vazio.
- Forfeit vem com `status` "forfeited by …" e mapas "TBD": o coletor rejeita como `not_final` antes
  do contrato. Mapa `played` sem rounds e sem agentes (quase sempre W.O. de um mapa no meio da
  série) é descartado pelo contrato e contado em `raw_match.n_maps_without_data`.
- Formato "2 maps" (Challengers Spain) admite empate 1–1: `fct_match.is_draw`, sem vencedor. O Elo
  precisa tratar empate.
- O veto do vlr.gg pode vir digitado errado (mapa como pick e decider, decider duplicado): agregue
  por mapa antes de juntar.
- Showmatch vem junto das partidas do evento (`series` "Showmatch: …"): `fct_match.is_showmatch`
  liga `is_excluded`, e os fatos herdam. Nunca analise showmatch.
- Time sem tag (Korea WDG): jogadores com `teamTag` vazio e rounds com `winner` nulo; o contrato
  usa a tag vazia, e o staging a anula. O método de vitória pode faltar em rounds soltos.
- Nome de time chinês vem com razão social na partida e nome curto no mapa: resolva nome → id só
  por `bridge.team_id_by_name`, nunca por igualdade de string.
- Mapa refeito por lobby remake ("Map N stats are incomplete/unavailable" na nota do veto; N é a
  ordem da série pelo veto, não a posição em `maps[]`) e mapa sem estatística (sem rounds, ou sem
  duração e sem rating) ficam com `has_complete_stats = false`: o gabarito do vlr.gg os exclui, e
  a validação cruzada também.
- `loadout` da economia pode vir nulo em rounds soltos.
- Time sem página no vlr.gg ("TBD", id nulo) derruba a partida no contrato, de propósito. O mesmo
  vale para evento órfão, substituição no mapa (slot "A/B" sem id) e jogador fundido (dois agentes
  numa linha): o coletor rejeita como `source` (`schemas.known_source_defect`), que não conta para
  o aborto.
- O `atkWinRate` do gabarito `/events/{id}/agents` exclui o overtime.
- Nenhuma falha isolada derruba a coleta: gabarito ausente segue sem arquivo, listagem ausente pula
  o evento (3 seguidas abortam), partida sem resposta vira `unavailable` e volta na próxima execução.
- Partida apagada no vlr.gg continua listada no evento e dá 404 no detalhe (qualificatória aberta):
  vira `not_found`, definitiva, e não conta para o aborto de 5 rejeições seguidas.
- `tabs=all` pode vir com `economy`/`performance` só de listas vazias: o contrato trata como aba
  ausente. Economia pela metade continua recusada.
- A caixa da tag muda por campo ("ARAS" no round, "Aras" no jogador) e a economia pode rotular o
  time pelo nome: tag é sempre canônica em caixa alta (`Tag` em `schemas.py`); nunca compare tag
  crua.
- Não rode o dbt sobre o lake enquanto a coleta grava: as tabelas de um evento são gravadas uma a
  uma, e o build lê um estado misto. Construa sobre uma cópia (`LAKE_DIR` apontando para ela).

## Convenções

- Python 3.12, `uv`, ruff + black via pre-commit. Ambiente em WSL Ubuntu.
- dbt: `stg_*`, `int_*`, `dim_*` / `fct_*`, `mart_*`. Todo model novo com teste no
  `_*_models.yml` da pasta (`_stg_models.yml`, `_int_models.yml`, `_marts_models.yml`); regra com
  lógica não trivial ganha teste unitário do dbt (`unit_tests:`) no mesmo arquivo. Testes de
  qualidade entre tabelas ficam em `dbt/tests/assert_*.sql`.
- O lake de fixtures é o caminho para testar o dbt: caso novo da API vira fixture em
  `ingestion/tests/fixtures/` e entra em `ingestion/fixture_lake.py`.
- Em `dagster_defs/assets.py`, sem `from __future__ import annotations`: o Dagster inspeciona a
  anotação do `context` e recusa string.
- Nunca chame a API fora de `ingestion/client.py`, que concentra retry, rate limit, cache e User-Agent.
- Toda resposta da API é validada por `ingestion/schemas.py` (contrato Pydantic) antes de gravar.
- Nada grava no lake fora de `ingestion/lake.py`, que fecha o schema de cada tabela (tipos
  forçados, nunca inferidos). Coluna nova entra em `SCHEMAS` e no `_sources.yml`.
- Mudança no formato da API deve quebrar um teste de fixture, nunca uma análise.
- Commits prefixados com o dia: `D6: achata detalhe de partida em tabelas raw`. O usuário faz os
  commits manualmente: não commite sem pedido explícito.

## Front-end

- CSS próprio com custom properties.
- Tema customizado do ECharts derivado dos tokens. Nunca o tema padrão.
- Densidade compacta: tabela densa, não cartão espaçado.
- Evite padrões genéricos: rótulo em caixa alta acima de cada título, cartões idênticos com a
  mesma sombra, seta `→` em botão, fade-and-slide em cada seção.

## Ao fim de cada sessão

Três linhas no `DEVLOG.md`: o que fiz / o que quebrou / decisão tomada.

## Contexto adicional

- `docs/projeto-valorant-data.md` — decisões com justificativa e cronograma dos 30 dias. Leia antes
  de propor mudança estrutural.
- `docs/openAPI-doc.json` — especificação OpenAPI da vlresports, só como referência.
- `docs/fontes.md` — auditoria da API, pegadinhas e casos testados. Leia antes de mexer em `ingestion/`.
- `docs/estrutura.md` — guia de estudo: cada pasta e cada arquivo, o que faz e com quem conversa.
