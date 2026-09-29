# MetaScope VAL

Plataforma de análise estatística do cenário competitivo de VALORANT: pipeline de
dados próprio (API vlresports, com dados do vlr.gg), warehouse com dbt, análises estatísticas e uma
camada preditiva calibrada. Site estático, sem backend, publicado no GitHub Pages.

> Status: **D8 — ingestão e lake** (backfill em andamento). Documento mestre do projeto:
> `docs/projeto-valorant-data.md`.

---

## As 8 perguntas que o projeto responde

1. **Lados** — qual o tamanho real da vantagem de ataque/defesa em cada mapa, e ela
   se move entre patches?
2. **Pistol** — ganhar a pistol round aumenta em quanto a probabilidade de vencer o mapa,
   controlando por força dos times?
3. **Veto** — quem escolhe o mapa vence mais nele? Quanto vale o pick no veto?
4. **Meta de composição** — quais composições de 5 agentes superam o esperado por mapa e
   patch, depois de corrigir pelo fato de que times fortes jogam comps "fortes"?
5. **Regiões** — qual a força relativa entre Americas, EMEA, Pacific e China quando se
   encontram em eventos internacionais?
6. **Rating** — um Elo/Glicko-2 com decaimento e ajuste por tier de evento prevê melhor
   que win rate bruto?
7. **Modelo** — um modelo com features estritamente pré-jogo bate o baseline de Elo puro
   em log loss e Brier score?
8. **Velocidade do meta** — quão rápido a distribuição de agentes se reorganiza depois
   de cada patch?

Cada pergunta tem um notebook em `notebooks/` (matplotlib, outputs commitados) e uma
seção no site.

---

## Arquitetura

```
API vlresports ──> ingestion/ ──> Parquet (lake) ──> dbt + DuckDB ──> marts
                                                          │
                                                          ├──> pipeline/features.py ──> train.py
                                                          └──> pipeline/build_site.py ──> dist/
                                                                                           │
                                                                      GitHub Actions ──> GitHub Pages
```

Decisões de arquitetura e trade-offs: **`docs/projeto-valorant-data.md`**. Auditoria da API:
**`docs/fontes.md`**.

## Stack

| Camada | Escolha |
|---|---|
| Ambiente | Python 3.12 + `uv` + `make` |
| Coleta | `httpx` + `tenacity` consumindo a API vlresports, contrato em Pydantic |
| Lake | Parquet no Hugging Face Datasets (privado), partição por temporada |
| Engine | DuckDB (arquivo efêmero) |
| Transformação | dbt-core + `dbt-duckdb` |
| Orquestração | Dagster (assets particionados) |
| Gatilho | GitHub Actions |
| Análise | pandas, scipy, statsmodels, matplotlib |
| ML | scikit-learn + LightGBM |
| Geração do site | Jinja2 |
| Front | CSS próprio + ECharts com tema customizado |
| Hospedagem | GitHub Pages |

## Começando

```bash
uv sync                # ambiente
uv run pre-commit install
make test              # pytest
make build             # pipeline completo -> dist/
make serve             # serve dist/ em localhost:8000
```

Alvos disponíveis: `make help`.

## Estrutura

```
ingestion/     cliente da API, contrato Pydantic, coletores e testes sobre fixtures reais
dbt/           staging + marts, o núcleo avaliável do projeto
pipeline/      features, treino, geração do site
dagster_defs/  assets particionados por split, checks
notebooks/     análises em matplotlib, outputs commitados
web/           templates Jinja2, CSS, JS
dist/          gerado; é o que vai ao ar
docs/          decisões, auditoria da API e especificação OpenAPI
```

## Créditos

Dados do [vlr.gg](https://www.vlr.gg), obtidos pela API open source
[vlresports](https://github.com/Orloxx23/vlresports), de Orloxx23, pela instância pública
`https://vlr.orlandomm.net/api/v1`.

## Aviso

As probabilidades publicadas vêm de um modelo estatístico com fins de portfólio.
Não são recomendação de aposta.

## Licença

A definir.
