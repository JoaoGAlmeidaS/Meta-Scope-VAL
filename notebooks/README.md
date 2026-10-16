# notebooks/

**matplotlib, outputs commitados.** O visualizador do GitHub não executa JS, então Plotly ou
ECharts apareceriam vazios aqui. Interativo fica só no site; estes notebooks são para quem
abre o repositório.

Cada notebook lê o warehouse do `make build` (`dbt/metascope.duckdb`, marts de
`dbt/models/analysis/`) e chama as funções de `pipeline/analyses.py` — as mesmas que geram os
JSONs do site, então o número do notebook é o número do site. Estatística em `pipeline/stats.py`,
estilo dos gráficos em `pipeline/plots.py`.

```bash
make build       # warehouse
make notebooks   # executa todos e grava os outputs no próprio arquivo
```

| Notebook | Pergunta | Dia |
|---|---|---|
| `00_tese_da_janela_drift.ipynb` | o jogo muda o bastante para justificar a janela de 12 meses? | D17 |
| `01_lados_por_mapa.ipynb` | algum mapa favorece ataque ou defesa? | D18 |
| `02_pistol.ipynb` | quanto o pistol decide o mapa, com Elo igual? | D18 |
| `03_veto.ipynb` | escolher o mapa dá vantagem? | D19 |
| `04_regioes.ipynb` | alguma região rende acima ou abaixo do Elo nos internacionais? | D19 |
| `05_meta_composicao.ipynb` | alguma composição vence mais do que a força de quem a joga explica? | D20 |
| `06_rating.ipynb` | busca dos parâmetros do Elo e ranking na janela | D15 |
| `07_previsao_calibracao.ipynb` | a probabilidade do Elo é calibrada? (log loss, Brier, curva) | D21 |
| `08_velocidade_do_meta.ipynb` | quão rápido o meta de agentes se reorganiza? | D20 |

Regras: todo número com IC 95%; correção de Holm quando há várias comparações; bootstrap por mapa
quando a unidade é o round; shrinkage nas composições; "inconclusivo" é resultado. Os gráficos que o
README usa são exportados para `docs/img/`.
