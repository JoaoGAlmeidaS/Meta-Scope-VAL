# CLAUDE.md

Meta-Scope-VAL: plataforma de análise estatística do cenário competitivo de VALORANT. Pipeline
próprio consumindo a API vlresports, warehouse em dbt, rating Elo com previsões e site estático
no GitHub Pages.

Projeto de portfólio. Prioridades: **engenharia de dados → produto → análise estatística → ML (pós-D30)**.

## Comandos

```bash
make build      # pipeline completo → dist/
make serve      # python -m http.server -d dist
make test       # pytest (dbt test fica em make dbt-test)
make lint       # ruff + black
make events     # índice de eventos, listagens de partidas e gabarito → data/lake
make backfill   # coleta local desde 2023, do mais recente ao mais antigo (horas: rode no tmux)
make ingest     # carga incremental da temporada corrente
make lake-push  # data/lake → dataset privado no Hugging Face (requer `hf auth login`)
make lake-pull  # dataset do Hugging Face → data/lake
make seed       # dbt deps + seeds (patches, overrides de evento) com testes
uv sync         # dependências
uv run dbt deps --project-dir dbt
uv run dbt build --project-dir dbt
uv run dagster dev
```

Nunca `pip install`. Dependência nova entra por `uv add`. Rode ferramentas com `uv run`.

## Arquitetura em uma frase

API vlresports → coletor Python → Parquet no lake → dbt sobre DuckDB → Elo e análises →
JSONs pré-computados → site estático. Dagster define os assets, GitHub Actions dispara.

Lake: `data/lake/{tabela}/season=YYYY/{event_id}.parquet` (chave Hive `season`, um arquivo por
evento), JSON bruto em `data/lake/_json/`, espelhado num dataset **privado** do Hugging Face.

## Regras invioláveis

Decisões fechadas e documentadas em `docs/projeto-valorant-data.md`. Não sugira reabrir sem motivo novo.

- **Janela de análise: 12 meses.** Todo mart de análise filtra pela variável dbt
  `analysis_window_months`. Nunca hardcode a janela. Exceções: aquecimento do Elo e o mart de drift.
- **Coleta ampla, análise restrita.** O backfill vai de 2023 (era franqueada) até hoje, do mais
  recente para o mais antigo; o filtro acontece no dbt. A coleta não aplica overrides: exclusão e
  reclassificação de evento vivem no seed `event_overrides.csv` (China Evolution Series fica fora).
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
- **Região do time** = região do evento doméstico mais recente que ele disputou antes da partida.
- **Dimensões vêm das partidas.** `dim_player` e `dim_team` saem de `raw_player_map` e `raw_match`.
  Nunca construa dimensão a partir de `/players` ou `/teams`: são leaderboard e ranking, não cadastros.

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
- A cota de 30/min é compartilhada por todos os usuários da instância: vazão real de ~6–10 req/min.

## Convenções

- Python 3.12, `uv`, ruff + black via pre-commit. Ambiente em WSL Ubuntu.
- dbt: `stg_*`, `dim_*` / `fct_*`, `mart_*`. Todo model novo com teste no `_*_models.yml` da
  pasta (`_stg_models.yml`, `_marts_models.yml`).
- Nunca chame a API fora de `ingestion/client.py`, que concentra retry, rate limit, cache e User-Agent.
- Toda resposta da API é validada por `ingestion/schemas.py` (contrato Pydantic) antes de gravar.
- Nada grava no lake fora de `ingestion/lake.py`, que fecha o schema de cada tabela (tipos
  forçados, nunca inferidos). Coluna nova entra em `SCHEMAS` e no `_sources.yml`.
- Mudança no formato da API deve quebrar um teste de fixture, nunca uma análise.
- Commits prefixados com o dia: `D6: achata detalhe de partida em tabelas raw`.

## Front-end

- CSS próprio com custom properties. Sem Tailwind.
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
