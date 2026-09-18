# Decisões tomadas e o porquê

> Copiado da seção 2 do documento mestre do projeto. Estas decisões já foram debatidas e
> fechadas. Não reabrir sem motivo novo.

**Arquitetura estática, sem backend.** O site é HTML + CSS + JS lendo JSON pré-computado.
Não existe API viva nem banco em produção.
*Por quê:* Fly.io acabou com o free tier; Render hiberna em 15 min e o Postgres grátis
expira em 90 dias — o recrutador abriria o link e veria tela branca. Estático no GitHub
Pages fica de pé indefinidamente, custo zero, sem cold start.

**GitHub Pages como hospedagem.** Limites: 1 GB de site e de repositório (recomendado),
100 GB/mês de banda (soft), deploy com timeout de 10 min (rígido). Orçamento estimado do
site: ~15 MB. Folga enorme.

**Predições pré-computadas em lote.** ~150 times → ~11 mil confrontos, particionados em um
JSON por time. O front faz lookup, não inferência.
*Por quê:* o espaço de entrada é finito. Predição paramétrica ao vivo fica para depois via
ONNX no navegador (não via servidor).

**DuckDB como engine, não como banco.** Arquivo descartável, gerado e destruído a cada
build. O `dbt-duckdb` lê os Parquet do lake direto como `sources`, sem etapa de carga.
*Por quê:* o warehouse aqui é artefato de build, não serviço. O DuckDB existe para
viabilizar o dbt — que é a camada realmente avaliável. O dialeto SQL é baseado no do
Postgres, então a curva é de horas.

**Dagster define o pipeline, GitHub Actions dispara.** Não são concorrentes.
*Por quê:* assets particionados por split dão backfill como operação única, retomada
automática e reprocessamento cirúrgico — tudo que seria escrito à mão, pior. A UI do
Dagster não vai ao ar (precisa de servidor); a linhagem pública é o `dbt docs`.

**Parsers importados como módulo, não como API auto-hospedada.** A API original saiu do ar;
o valor está nos parsers, não na casca FastAPI.
*Por quê:* rodar um serviço HTTP para chamar a si mesmo é peso morto. E a camada de
ingestão própria (retry, rate limit, cache) vale mais no portfólio do que "consumi uma API".

**Backfill histórico roda local, uma vez.** O resultado sobe em Parquet para o lake. O CI
faz só carga incremental.
*Por quê:* IPs do GitHub Actions são tratados com mais rigor por Cloudflare. Se o CI for
bloqueado, o projeto continua funcionando.

**Notebooks em matplotlib, ficam no repositório, linkados do site.**
*Por quê:* o visualizador do GitHub não executa JS, então Plotly/ECharts apareceria vazio.
Interativo fica só no site. Mandar o visitante ao repositório direciona para a prioridade
nº 1.

**`schedule` desligado até o D14, ligado semanalmente depois.** `workflow_dispatch` ativo
desde o início.
*Por quê:* rodar manual enquanto o pipeline está instável, automático quando estabilizar.
Semanal é honesto com a cadência do calendário competitivo.

**Particionamento por split/temporada.** Unidade natural do domínio e dos assets do Dagster.

---

## Armadilhas conhecidas

1. **Vazamento de dados** — features só com informação pré-jogo. 95% de acurácia significa
   que você vazou.
2. **Split aleatório** — sempre temporal.
3. **Acurácia como métrica única** — use log loss e Brier.
4. **Só tier 1** — inclua Challengers, ligas regionais e Game Changers para ter volume, com
   feature de tier.
5. **Win rate bruto de composição** — comps fortes são jogadas por times fortes. Controle
   por mapa, patch e força do time.
6. **Ignorar patches** — dimensão desde o D10, não remendo depois.
7. **Parser silenciosamente quebrado** — é por isso que os fixtures do D3 não são opcionais.
8. **Bloqueio do CI pelo vlr.gg** — backfill local, incremental no CI, e o projeto sobrevive
   se bloquear.
