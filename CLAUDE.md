# CLAUDE.md

Meta-Scope-VAL: plataforma de análise estatística do cenário competitivo de VALORANT. Pipeline
próprio consumindo a API vlresports, warehouse em dbt, rating Elo com previsões e site estático
no GitHub Pages.

Projeto de portfólio. Prioridades: **engenharia de dados → produto → análise estatística → ML (pós-D30)**.

## Comandos

```bash
make build      # pipeline completo → dist/
make serve      # python -m http.server -d dist
make test       # pytest + dbt test
make lint       # ruff + black
uv sync         # dependências
uv run dbt deps --project-dir dbt
uv run dbt build --project-dir dbt
uv run dagster dev
```

Nunca `pip install`. Dependência nova entra por `uv add`. Rode ferramentas com `uv run`.

## Arquitetura em uma frase

API vlresports → coletor Python → Parquet no lake → dbt sobre DuckDB → Elo e análises →
JSONs pré-computados → site estático. Dagster define os assets, GitHub Actions dispara.

## Regras invioláveis

Decisões fechadas e documentadas em `docs/projeto.md`. Não sugira reabrir sem motivo novo.

- **Janela de análise: 12 meses.** Todo mart de análise filtra pela variável dbt
  `analysis_window_months`. Nunca hardcode a janela. Exceções: aquecimento do Elo e o mart de drift.
- **Coleta ampla, análise restrita.** O backfill vai de 2022 até hoje, do mais recente para o mais
  antigo; o filtro acontece no dbt.
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
- **Idempotência:** rodar duas vezes não duplica linha. Upsert por id.
- **Particionamento por split/temporada** nos assets do Dagster.
- **Dimensões vêm das partidas.** `dim_player` e `dim_team` saem de `raw_player_map` e `raw_match`.
  Nunca construa dimensão a partir de `/players` ou `/teams`: são leaderboard e ranking, não cadastros.

## Particularidades da API (detalhes em `docs/fontes.md`)

- `rounds[].side` é o lado de **quem venceu** o round.
- Time aparece como id, nome e tag. A ponte tag → id é posicional (`economy.teams[i]` ↔ `teams[i]`)
  e precisa de teste. A chave é sempre o `id`.
- Multikills e clutches por mapa podem vir zerados; não use sem verificar.
- Pistol (rounds 1 e 13) vem classificado como `eco` — exclua das análises de economia.
- Kill matrix e `performance` identificam jogador por nome, sem id.
- Force tipos no schema: `rating` pode vir inteiro, `duration` mistura formatos, `limit` vem como string.
- `teamTag` em `/players` é o time atual; jogador sem time recebe o próprio nome como tag.

## Convenções

- Python 3.12, `uv`, ruff + black via pre-commit. Ambiente em WSL Ubuntu.
- dbt: `stg_*`, `dim_*` / `fct_*`, `mart_*`. Todo model novo com teste em `schema.yml`.
- Nunca chame a API fora de `ingestion/client.py`, que concentra retry, rate limit, cache e User-Agent.
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

- `docs/projeto.md` — decisões com justificativa e cronograma dos 30 dias. Leia antes de propor
  mudança estrutural.
- `docs/fontes.md` — auditoria da API, pegadinhas e casos testados. Leia antes de mexer em `ingestion/`.
