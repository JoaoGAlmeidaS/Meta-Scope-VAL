# CLAUDE.md

Plataforma de análise estatística do cenário competitivo de VALORANT. Pipeline próprio de dados
do vlr.gg, warehouse em dbt, modelo preditivo e site estático publicado no GitHub Pages.

Projeto de portfólio. Prioridades, em ordem: **engenharia de dados → produto → ML → estatística**.

## Comandos

```bash
make build      # pipeline completo → dist/
make serve      # python -m http.server -d dist
make test       # pytest + dbt test
make lint       # ruff + black
uv sync         # dependências
dbt build --project-dir dbt      # transformação (DuckDB efêmero)
dagster dev                      # UI local em localhost:3000
```

Nunca use `pip install` direto. Dependência nova entra pelo `uv add`.

## Arquitetura em uma frase

vlr.gg → coletor Python → Parquet no lake → dbt sobre DuckDB → features → modelo →
JSONs pré-computados → site estático. Dagster define os assets, GitHub Actions dispara.

## Regras invioláveis

Estas decisões estão fechadas e documentadas em `docs/decisoes.md`. Não sugira reabrir sem
motivo técnico novo.

- **Não existe backend.** Nada de FastAPI, servidor, banco em produção ou endpoint. O site é
  HTML + CSS + JS lendo JSON estático. Se algo parece exigir servidor, pré-compute.
- **DuckDB é engine, não banco.** O arquivo `.duckdb` é artefato de build, descartado ao final.
  Não sugira Postgres.
- **Transformação é em SQL no dbt**, não em pandas. pandas só para features, treino e geração
  de artefatos.
- **Notebooks usam matplotlib.** Plotly e ECharts não renderizam no visualizador do GitHub.
  Interativo existe só no site.
- **Dados não entram no Git.** Parquet vai para o lake. Só fixtures de teste ficam no repo.

## Regras de dados

- **Anti-vazamento:** toda feature de `mart_match_features` precisa ser computável antes do
  `match_datetime`. Existe um teste que falha se isso for violado — não o contorne.
- **Split temporal sempre.** Nunca `train_test_split` aleatório em dados de partida.
- **Métricas:** log loss, Brier e curva de calibração. Acurácia é secundária e enganosa aqui.
- **Particionamento por split/temporada** em todos os assets do Dagster.
- **Idempotência:** rodar duas vezes não pode duplicar linha. Upsert por id.
- **Win rate de composição sempre com shrinkage** e controlado por mapa, patch e força do time.

## Convenções

- Python 3.12, `uv`, ruff + black via pre-commit.
- dbt: `stg_*` (staging), `dim_*` / `fct_*` (dimensional), `mart_*` (consumo).
  Todo model novo precisa de teste em `schema.yml`.
- Coleta: nunca chame o vlr.gg fora do `ingestion/client.py`, que concentra retry, rate limit,
  cache e User-Agent. Requisição direta com httpx no meio de outro módulo é bug.
- Parsers em `ingestion/vendor/` são código de terceiro. Ao corrigir, mantenha o crédito e
  registre a mudança no `DEVLOG.md`.
- Toda mudança de layout do vlr.gg deve quebrar um teste de fixture, nunca uma análise.

## Front-end

- CSS próprio com custom properties. Sem Tailwind.
- Tema customizado do ECharts derivado dos tokens. Nunca o tema padrão.
- Densidade compacta: é site de dados de esports, tabela densa, não cartão espaçado.
- Evite os padrões genéricos: rótulo em caixa alta acima de cada título, cartões arredondados
  idênticos com a mesma sombra, seta `→` no texto de botão, fade-and-slide em cada seção.

## Ao fim de cada sessão

Três linhas no `DEVLOG.md`: o que fiz / o que quebrou / decisão tomada.

## Contexto adicional

- `docs/decisoes.md` — decisões de arquitetura com a justificativa. Leia antes de propor
  mudança estrutural.
- `docs/cronograma.md` — os 30 dias, com os pontos de corte.
