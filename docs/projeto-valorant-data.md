# VALORANT Data (Meta-Scope-VAL) — Documento mestre do projeto

> Este arquivo é a fonte de contexto do projeto. No repositório: `docs/projeto-valorant-data.md`.
> A auditoria detalhada da API fica em `docs/fontes.md`.
> Última atualização: 07/10/2026 · Status: **Blocos 0 a 2 concluídos e fechados (D1–D14)**: coleta 2025+ completa (7.019 partidas no lake e no HF), `make build` verde sobre o lake real · **Bloco 3 liberado** · decisões pendentes no fim de `docs/fontes.md`
> Repositório: github.com/JoaoGAlmeidaS/Meta-Scope-VAL

---

## 1. O que é

Plataforma de análise estatística do cenário competitivo de VALORANT, com pipeline de dados próprio, análises estatísticas e previsão de resultados. Dados do vlr.gg via API vlresports. Escopo: tier 1 (VCT) e tier 2 (VCL).

**Prioridades, em ordem:** 1) Engenharia de dados · 2) Produto usável · 3) Análise estatística · 4) ML (pós-D30)

**Prazo:** 30 dias, metas diárias, independente de horas trabalhadas por dia.

**Público-alvo do portfólio:** recrutadores e gerentes técnicos de vagas de dados. O repositório importa tanto quanto o site.

---

## 2. Decisões tomadas e o porquê

Estas decisões já foram debatidas e fechadas. Não reabrir sem motivo novo.

### Estratégia de análise

**Janela de análise: últimos 12 meses.** Toda análise publicada usa só partidas dentro da janela.
*Por quê:* nerfs, reworks e agentes novos mudam o ritmo de jogo e a vantagem de cada lado mesmo em mapas que não mudaram (a Ascent é o exemplo); somam-se rotação de pool e reworks de mapa. Dado mais antigo distorce o resultado atual. 12 meses já é uma estimativa generosa.
*Implementação:* variável dbt `analysis_window_months: 12`, lida por todos os models de análise. Nunca hardcoded.
*Exceções:* (1) o rating de times usa alguns meses anteriores à janela só como aquecimento, sem aparecerem nos resultados; (2) a análise de drift usa o histórico completo — o coletado desde 2025 mais o anterior importado de um dataset pronto —, justamente para demonstrar a tese da janela.

**Coleta própria desde 2025, análise restrita.** O backfill cobre 2025→hoje, mesmo que a análise use 12 meses.
*Por quê (revisto em 05/10):* janela de análise e aquecimento do Elo cabem em 2025+, e a instância pública rende ~13 requisições/min — 2023–2024 seriam mais ~9.300 partidas (~12 h) só para o drift. A coleta própria existe pela experiência de engenharia, não pelo volume: o histórico anterior a 2025, que só o drift (D17) usa, vem de um dataset pronto importado à parte.
*Antes (D5):* a regra era 2023→hoje, "coleta ampla" — o que não fosse coletado da instância pública poderia deixar de existir. O argumento vale menos quando existe dataset pronto para o período antigo.

**China Evolution Series fica fora (decidido no D5).** Times franqueados, mas fora do circuito oficial da liga; mesmo racional do offseason. É coletada e excluída no dbt pelo seed `event_overrides.csv`.

**Lake no Hugging Face Datasets, privado (decidido no D5).** `huggingface-hub` já estava na stack e o DuckDB lê o formato direto. Privado para não republicar dados do vlr.gg; o CI usa `HF_TOKEN`.

**Partição por temporada, um arquivo por evento (decidido no D5).** `data/lake/{tabela}/season=YYYY/{event_id}.parquet`. Reescrever o arquivo do evento é o upsert idempotente. Split como partição física foi descartado: os nomes de split da VCL não têm padrão.

**Escopo: só VCT (tier 1) e VCL (tier 2)**, na coleta e na análise. Game Changers, t3, collegiate e offseason ficam de fora. Tier fica como dimensão, para estratificar e ajustar o Elo. **Exceção (05/10): o tier 2 chinês** — VCL China e China Evolution Series — fica fora da coleta: disputado em plataformas de terceiros, chega com dados faltando (abas vazias, lado sem método, mapas sem dado) e vale pouco além do volume. O VCT China (tier 1) fica.
*Por quê:* offseason tem times testando formações e agentes fora do padrão, e os demais circuitos têm níveis e pools de jogadores que distorcem o meta competitivo. A VCL dá o volume que 12 meses de VCT sozinho não daria. Mesmo assim as amostras por mapa e lado são pequenas: todo número publicado leva intervalo de confiança, e conclusão sem significância é reportada como inconclusiva.

**Estatísticas agregadas do vlr.gg são gabarito, não fonte.** `/events/{id}/agents` (pick rate e win rate de ataque/defesa por mapa) entra só nos testes de validação cruzada do D13.
*Por quê:* vem por evento, arredondado para inteiro, sem contagem de rounds e sem metodologia documentada — não fatia por janela, patch ou força do time, nem permite intervalo de confiança. Mas é um cálculo independente sobre os mesmos dados brutos, o que o torna um verificador ideal.

**Previsões via Elo nos 30 dias; modelo treinado fica para depois.** A fórmula do Elo já produz a probabilidade de A vencer B, sem treino.
*Por quê:* a janela de 12 meses deixa pouco dado para treinar um modelo. O Elo entrega uma primeira versão honesta da tela de previsões, e vira o baseline que o futuro modelo precisa superar.

### Fonte de dados

**API vlresports** (`https://vlr.orlandomm.net/api/v1`), instância pública. O endpoint de detalhe de partida entrega veto, rounds com lado e método, agentes por jogador por mapa, stats e economia round a round.
*Por quê:* auditada no D2 com uma BO5 de 2022 — composição de agentes presente em todos os mapas. O repositório é open source (Orloxx23/vlresports), então auto-hospedar é o plano B se a instância cair.

**Backfill histórico roda local, uma vez.** O resultado sobe em Parquet para o lake. O CI faz só carga incremental.
*Por quê:* não martelar a instância pública a partir de IPs do GitHub Actions. Se o CI for bloqueado, o projeto continua funcionando.

**Backfill pela rota de eventos.** `/events?tier=vct` e `tier=vcl` → `/events/{id}/matches` → `/matches/{id}`.
*Por quê:* tier e região chegam junto com o evento, a partição por split é natural, e o filtro de escopo acontece na origem.

**Abas do detalhe só na janela.** `tabs=all` (performance e economia) para a janela de 12 meses e o aquecimento; histórico mais antigo só com a resposta básica.
*Por quê:* cada aba é uma requisição extra ao vlr.gg. A resposta básica já traz rounds com lado, veto e agentes — tudo que as análises e o drift usam.

**Backfill do mais recente para o mais antigo.** Primeiro a janela de 12 meses e o aquecimento do Elo; depois até o início de 2025.
*Por quê:* a vazão da instância pública não é controlável. Se ela cair no meio, sobra o que as análises usam.

**Jogadores e times vêm das partidas, não das listagens.** `/players` e `/teams` são leaderboard e ranking, não cadastros. `dim_player` e `dim_team` saem de `raw_player_map` e `raw_match`, com o time da época.
*Por quê:* completude por construção — todo jogador de uma análise está na dimensão. Endpoints por id só enriquecem (região do time).

### Arquitetura

**Arquitetura estática, sem backend.** O site é HTML + CSS + JS lendo JSON pré-computado. Não existe API viva nem banco em produção.
*Por quê:* Fly.io acabou com o free tier; Render hiberna em 15 min e o Postgres grátis expira em 90 dias. Estático no GitHub Pages fica de pé indefinidamente, custo zero, sem cold start.

**GitHub Pages como hospedagem.** Limites: 1 GB de site e repositório (recomendado), 100 GB/mês de banda (soft), deploy com timeout de 10 min (rígido). Orçamento estimado do site: ~15 MB.

**Previsões pré-computadas em lote.** Todos os confrontos par a par, particionados em um JSON por time. O front faz lookup, não cálculo.

**DuckDB como engine, não como banco.** Arquivo descartável, gerado e destruído a cada build. O `dbt-duckdb` lê os Parquet do lake direto como `sources`.
*Por quê:* o warehouse é artefato de build, não serviço. O DuckDB existe para viabilizar o dbt. O dialeto SQL é baseado no do Postgres.

**Dagster define o pipeline, GitHub Actions dispara.** Não são concorrentes. O `make` e o Actions executam os jobs do Dagster (`ingest` por temporada, `build` para o warehouse); não existe segunda descrição do pipeline em script (confirmado no D12).
*Por quê:* assets particionados por temporada dão backfill, retomada e reprocessamento cirúrgico prontos. A UI do Dagster não vai ao ar; a linhagem pública é o `dbt docs`.

**CI em dois trilhos (decidido no D14).** Todo push roda lint, pytest e o build inteiro (Dagster → dbt → testes) sobre um lake gerado dos fixtures do repositório, sem segredo. O trilho real (lake-pull → coleta incremental → lake-push → build) é manual até o D29 e exige `HF_TOKEN`.
*Por quê:* o dbt fica testado em todo push mesmo sem acesso ao lake, e o resultado do trilho de fixtures não muda com o relógio (`AS_OF_DATE` fixa a janela).

**Dimensões como retrato, época nos fatos (decidido no D10).** `dim_team` e `dim_player` têm uma linha por id, com nome, tag e região mais recentes; o nome e a tag da época da partida ficam nos fatos. Sem SCD tipo 2.
*Por quê:* o site e os joins querem o nome atual; a análise histórica já tem o nome da época na própria linha do fato.

**Exceção de qualidade é escrita, não tolerada (decidido no D13).** Divergência aceita contra o gabarito do vlr.gg ou nas checagens de série vai para o seed `validation_exceptions.csv`, com motivo. O teste falha em qualquer outra.

**Notebooks em matplotlib, ficam no repositório, linkados do site.**
*Por quê:* o visualizador do GitHub não executa JS. Interativo existe só no site.

**`schedule` desligado até a publicação (D29), ligado semanalmente depois.** `workflow_dispatch` ativo desde o início.

**Particionamento por temporada.** Unidade natural do domínio, do lake e dos assets do Dagster.

---

## 3. Stack

| Camada | Escolha |
|---|---|
| Ambiente | Python 3.12 + `uv` + `make`, em WSL Ubuntu (repo dentro do FS Linux) |
| Coleta | `httpx` + `tenacity` consumindo a API vlresports |
| Lake | Parquet no Hugging Face Datasets (privado) |
| Engine | DuckDB (arquivo efêmero) |
| Transformação | dbt-core + `dbt-duckdb` |
| Orquestração | Dagster (assets particionados) |
| Gatilho | GitHub Actions |
| Análise | pandas, scipy, statsmodels, matplotlib |
| Rating e previsão | Elo próprio em Python |
| Geração do site | Jinja2 |
| Front | CSS próprio + ECharts com tema customizado |
| Hospedagem | GitHub Pages |
| ML (pós-D30) | scikit-learn + LightGBM |

---

## 4. Estrutura do repositório

```
├── docs/
│   ├── projeto-valorant-data.md este documento
│   ├── fontes.md                auditoria da API
│   └── openAPI-doc.json         especificação OpenAPI da vlresports (referência)
├── ingestion/
│   ├── client.py                httpx, retry, rate limit, cache
│   ├── schemas.py               contrato Pydantic: só os campos consumidos
│   ├── bridge.py                ponte tag → id de time por placar
│   ├── config.py                janela e aquecimento lidos do dbt_project.yml
│   ├── flatten.py               detalhe de partida → linhas das tabelas raw
│   ├── lake.py                  schema do Parquet, escrita por evento, push/pull no HF
│   ├── collectors.py            eventos, detalhe e backfill (CLI)
│   ├── fixture_lake.py          lake gerado dos fixtures (CI sem segredo) + cliente offline
│   └── tests/fixtures/          JSON real de partidas
├── dbt/
│   ├── macros/window.sql        janela de análise e aquecimento (nunca hardcoded)
│   ├── models/staging/          stg_*
│   ├── models/intermediate/     int_*: visão por time, região na época, completude, validação
│   ├── models/marts/            dim_*, fct_*, mart_*
│   ├── seeds/patches.csv        datas de cada patch, mantido à mão
│   ├── seeds/event_overrides.csv eventos a excluir ou reclassificar, mantido à mão
│   ├── seeds/validation_exceptions.csv divergências aceitas do D13, com motivo
│   └── tests/                   testes singulares de qualidade (D13)
├── pipeline/
│   ├── elo.py                   rating com aquecimento pré-janela
│   ├── predictions.py           probabilidades par a par + calibração
│   └── build_site.py            Jinja2 → dist/
├── dagster_defs/                assets (coleta + dbt), partições por temporada, checks do lake
├── notebooks/                   matplotlib, com outputs commitados
├── web/                         templates Jinja2, CSS, JS
├── dist/                        gerado, publicado no Pages
├── .github/workflows/build.workflow.yml
├── Makefile                     make build / make serve / make test
├── DEVLOG.md                    3 linhas por dia
└── README.md
```

**Saída do site:**

```
dist/
├── index.html
├── assets/                      style.css, app.js, echarts-theme.js
├── lineage/                     dbt docs
└── data/
    ├── meta.json                versão do build, data, janela, patches
    ├── teams/index.json         alimenta a busca
    ├── teams/{id}.json          perfil do time
    ├── predictions/{id}.json    todos os confrontos daquele time
    ├── meta/{mapa}-{patch}.json composições do recorte
    └── analyses/{nome}.json     séries das análises
```

Use `?v=` do `meta.json` nas requisições para invalidar cache do navegador.

---

## 5. Fonte de dados

Auditoria completa em **`docs/fontes.md`**: endpoints, tabelas raw planejadas, pegadinhas da API e casos de teste com status.

Resumo do que mais importa: `rounds[].side` é o lado de quem venceu; o time aparece como id, nome e tag, com ponte tag → id posicional; pistol vem classificado como eco; endpoints de listagem são recortes, não cadastros; abas `performance` e `economy` do detalhe são opcionais e custam uma requisição extra cada; o rate limit declarado é 30/min, mas o vlr.gg devolve 502/503 bem abaixo disso; o tier do vlr.gg é ruidoso e precisa de seed de correção.

---

## 6. Cronograma

**Regra diária:** um commit (prefixado com o dia, ex. `D3: ...`) e três linhas no `DEVLOG.md` (o que fiz / o que quebrou / decisão tomada).

### Bloco 0 — Fundação e validação da fonte · D1–D4

**D1 · Esqueleto** ✅
Repo, `uv`, pre-commit, estrutura de pastas, `Makefile`, README com as perguntas de pesquisa, decisões na seção 2 de `docs/projeto-valorant-data.md`.

**D2 · Auditoria da fonte** ✅
Gate aprovado: composição de agentes por mapa presente em 2022 e 2026. Rate limit de 30/min declarado, com 502/503 do vlr.gg abaixo disso; ritmo seguro de ~1 requisição a cada 3–6 s. Backfill estimado em ~1h40 por mil partidas. 16 pegadinhas e os casos testados em `docs/fontes.md`.

**D3 · Fixtures e testes de contrato** ✅
JSONs reais em `ingestion/tests/fixtures/` cobrindo os casos do D2, mais um detalhe de partida da VCL (único caso não testado no D2). Contrato em Pydantic com só os campos consumidos, reutilizado pelos coletores; a especificação OpenAPI fica em `docs/` como referência. Testes da reconstrução de lado por round — inclusive no overtime (734308) — e da ponte tag → id.
→ *Pronto quando:* uma mudança no formato da API quebra um teste, não uma análise.

**D4 · Cliente de coleta** ✅
`client.py`: httpx com timeout generoso (respostas levam 3–5 s), rate limiter de ~1 requisição a cada 3–6 s, retry com backoff exponencial em 429/502/503/504, leitura dos headers `ratelimit-*`, User-Agent identificável, cache em disco.
→ *Pronto quando:* buscar a mesma partida duas vezes não toca a rede na segunda.

### Bloco 1 — Ingestão e lake · D5–D8

**D5 · Eventos e listagem de partidas** ✅
Coletor de `/events?tier=vct` e `tier=vcl` (com tier e região) e de `/events/{id}/matches`. Guardar também `/events/{id}/agents`, o gabarito do D13. Definir o esquema de partição por split/temporada.
*Feito:* região pelo filtro `region` da API (evento em várias regiões = internacional), temporada pelo nome ou pela data, partição `season=YYYY` com um arquivo por evento. 548 eventos candidatos vct+vcl desde 2023; a primeira coleta caiu em 120 (gabarito com 502 persistente) e foi endurecida no D9. Coleta completa em 05/10, com a API de volta: 326 eventos e 16.889 partidas desde 2023; com o escopo reduzido a 2025+ no mesmo dia, 167 eventos e 7.617 partidas; sem o tier 2 chinês, **154 eventos e ~7.329 partidas**, gabarito em 321 (o 1309 segue com 502; 4 torneios chineses sem agregado no vlr.gg).

**D6 · Detalhe de partida** ✅
Achatar o JSON nas cinco tabelas raw de `docs/fontes.md`, com tipos forçados. `tabs=all` dentro da janela, só o básico no histórico. Fechar o schema do Parquet.
→ *Pronto quando:* uma BO5 completa está em Parquet nas cinco tabelas.
*Feito:* 734308 nas cinco tabelas, lida pelo DuckDB com os tipos do schema; `raw_reject` e JSON bruto arquivado.

**D7 · Lake + início do backfill** ✅
Configurar Hugging Face Datasets (ou R2). **Disparar o backfill local do mais recente para o mais antigo:** primeiro a janela de 12 meses + aquecimento, depois até o início de 2025. Deixar rodando à noite.
*Feito:* `make backfill` retomável e `make lake-push|lake-pull` no HF privado. Validação real com dois eventos: 2977 (60 partidas, zero rejeições) e 2962 (66 partidas, casos novos da fonte, pegadinhas 22–24). Backfill completo disparado em 05/10 na sessão tmux `metascope-backfill`, ~13 req/min; no mesmo dia o escopo da coleta própria foi reduzido a 2025+ e sem o tier 2 chinês (154 eventos, ~7.329 partidas), e o que saiu do escopo foi removido do lake e do HF. A coleta completa revelou as pegadinhas 26–37 (`docs/fontes.md`), todas com fixture e teste. Lake no HF privado (`meta-scope-val-lake`) criado com o primeiro push.

**D8 · Região dos times e patches** ✅
Região de cada time derivada da liga VCT ou VCL que ele disputa — `/teams/{id}` traz país, não região. Montar à mão os seeds `dbt/seeds/patches.csv` (datas de cada patch) e `dbt/seeds/event_overrides.csv` (eventos a excluir ou reclassificar — o tier do vlr.gg é ruidoso). Jogadores e times **não** saem das listagens — vêm das partidas no D10. Backfill continua.
*Feito:* 89 patches do CMS oficial da Riot; overrides com exclusões (China Evolution Series, torneios de terceiros, qualificatórias abertas) e reclassificação de região. Regra de região do time em `docs/fontes.md`.

### Bloco 2 — Warehouse · D9–D14 ⭐ *núcleo do portfólio*

**D9 · dbt + DuckDB** ✅
`dbt-duckdb`, sources nos Parquet, models de staging com tipagem e nomes padronizados.
*Feito:* sources por `LAKE_DIR`, nove `stg_*` deduplicados por chave, DuckDB em UTC, lake de fixtures gerado dos JSONs do repositório pelo backfill de verdade. A coleta do D5 foi endurecida (gabarito opcional, índice gravado mesmo na queda, partida indisponível volta para a fila).

**D10 · Dimensões** ✅
`dim_team` e `dim_player` construídas a partir das partidas (id como chave, nome e tag da época), `dim_map`, `dim_event` (com tier), `dim_patch` a partir do seed. Criar a variável `analysis_window_months`.
*Feito:* dimensões como retrato (mais recente) com a época nos fatos; `dim_event` com overrides; região do time na época por ASOF JOIN; macros de janela com `as_of_date`.

**D11 · Fatos** ✅
`fct_match`, `fct_map`, `fct_veto`, `fct_round` (com o lado de cada time reconstruído), `fct_player_map`, `fct_composition` (uma linha por time-mapa com os 5 agentes).
*Feito:* os seis fatos, com flags de janela e de exclusão; atacante e defensor por round, overtime incluído; pistol separado do eco na própria tabela.

**D12 · Dagster** ⚠️ *ponto de corte* ✅
Assets particionados por split, integração `dagster-dbt`.
→ *Gate:* se nada materializar até o fim do dia, corte o Dagster e siga com Actions chamando scripts.
*Feito:* gate cumprido. Coleta como multi-asset particionado por temporada, dbt via `dagster-dbt` (testes viram asset checks), checks do lake, jobs `ingest` e `build`, API como resource.

**D13 · Qualidade** ✅
Testes dbt + asset checks: rounds batem com o placar, lado reconstruído bate com `roundsCt`/`roundsT`, pistols fora das métricas de eco, forfeits e mapas não jogados tratados.
**Validação cruzada com o vlr.gg**, por evento, contra `/events/{id}/agents`: mapas jogados batem com `played` (completude da coleta), win rate de ataque/defesa bate com `atkWinRate`/`defWinRate` (reconstrução de lado) e pick rate de agentes bate com `pickRate` (composições), com tolerância de arredondamento.
→ *Pronto quando:* `dbt test` passa e você justifica cada exceção.
*Feito:* no evento real 2977, 9/9 mapas, 261/261 pick rates e 8/8 vitórias no ataque idênticos ao gabarito (o vlr.gg exclui o overtime do `atkWinRate`). Seed `validation_exceptions` vazio: nenhuma exceção precisou de justificativa. No lake completo 2025+ (07/10): `make build` verde, com 47 exceções escritas em cinco motivos (VCT China 2978 e 2499 com mapas a mais que o gabarito; showmatch de tag repetida no Japan Finals; mapa sem rounds sem ponte; gabarito inconsistente com mapa refeito no 2380). Showmatches saem da análise (`is_showmatch`), o mapa sem estatística sai da leitura `complete` da validação, e as qualificatórias nacionais do SEA foram excluídas por julgamento (pegadinhas 26–41 em `docs/fontes.md`).

**D14 · CI e marco** 🏁 ✅
`build.workflow.yml` com `workflow_dispatch` ativo e `schedule` comentado. `dbt docs generate`.
→ *Marco:* **um comando reconstrói o projeto do zero.**
*Feito:* `make build` (lake real) e `make build-fixtures` (CI) reconstroem o warehouse do zero pelo Dagster e geram o dbt docs estático em `dist/lineage`. CI em dois trilhos: fixtures em todo push, lake real manual.

### Bloco 3 — Análise estatística · D15–D20

**D15 · Rating de times**
Elo com aquecimento pré-janela, ajuste por tier de evento. Rating calculado sempre com dado anterior à partida.
→ *Pronto quando:* o ranking dentro da janela bate com a percepção do cenário.

**D16 · Marts de análise com janela**
`mart_*` filtrados por `analysis_window_months`. Teste que falha se algum mart de análise ler partida fora da janela (exceto o de drift).

**D17 · Drift — a tese da janela**
Série trimestral da vantagem de lado por mapa sobre o histórico completo, com patches marcados. Mostra o jogo mudando mesmo em mapas intocados. Desde 2025 o histórico vem do lake; antes disso, de um dataset pronto importado à parte (fonte e formato a definir).
→ *Pronto quando:* o gráfico justifica sozinho a escolha de 12 meses.

**D18 · Lado e pistol**
Vantagem atacante/defensor por mapa e pistol → vitória no mapa, dentro da janela. IC por bootstrap, correção para múltiplas comparações.

**D19 · Veto e regiões**
Vantagem de quem escolhe o mapa; força relativa entre regiões em confrontos internacionais.

**D20 · Meta de composição**
Win rate por comp com shrinkage bayesiano, por mapa e patch. Popularidade de agentes ao longo da janela.

### Bloco 4 — Previsão e artefatos · D21–D22

**D21 · Previsões via Elo**
Probabilidade par a par pela fórmula do Elo. Validar calibração dentro da janela: log loss, Brier e curva de calibração.
→ *Pronto quando:* a curva de calibração está num notebook e a matriz de confrontos está em Parquet.

**D22 · Asset `site_artifacts`**
JSONs particionados conforme a seção 4, com `meta.json` informando versão, data e janela usada.
→ *Pronto quando:* `dist/data/` está completo e o maior arquivo cabe em poucas centenas de KB.

### Bloco 5 — Produto · D23–D28

**D23 · Design system**
Tokens do CSS existente num arquivo único. Duas telas no Figma (rankings e uma de análise). Densidade compacta.

**D24 · Tema de gráfico e gerador**
Tema próprio do ECharts derivado dos tokens. `build_site.py` com Jinja2 gerando `dist/`.

**D25 · Telas base**
Home, rankings, busca de times.

**D26 · Perfil de time**
Histórico, win rate por mapa, forma, roster.

**D27 · Meta + elemento assinatura**
Tela de meta com filtros por mapa e patch. A visualização de veto é o elemento de ousadia visual; resto do site disciplinado.

**D28 · Previsões**
Seleção de dois times, lookup client-side, probabilidade do Elo com aviso de que é estatística, não conselho de aposta. Estados vazios e de erro.

### Bloco 6 — Entrega · D29–D30

**D29 · Publicação**
Deploy no Pages, `dbt docs` em `/lineage`, links para os notebooks, CI verde. **Ligar o `schedule` semanal.**

**D30 · Narrativa** 🏁
README definitivo: problema, arquitetura, decisões (seção 2), a tese da janela com o gráfico de drift, resultados com números honestos — inclusive os inconclusivos. GIF de 30s, post no LinkedIn.

---

## 7. Contingência

Se atrasar 2 dias ou mais, corte nesta ordem. **Nunca corte o Bloco 2.**

1. **D19** → fica só a vantagem de veto; força regional sai.
2. **D12 (Dagster)** → Actions chamando scripts. O `dbt docs` mantém a linhagem pública.
3. **D23 (Figma)** → direto no código a partir do CSS existente.
4. **D20** → composição estratificada só por mapa, sem patch, se a amostra não sustentar.

Reduzir escopo e registrar a decisão no DEVLOG é sinal de senioridade.

---

## 8. Armadilhas

1. **Dado fora da janela** — contamina win rates atuais. Todo mart de análise passa pela variável de janela.
2. **Amostra pequena** — janela curta exige IC em todo número e shrinkage em composições. Inconclusivo é resultado válido.
3. **Tier fora do escopo** — só VCT e VCL entram. O filtro acontece na coleta e é testado.
4. **Rating com dado futuro** — o Elo usado para prever uma partida é sempre o de antes dela.
5. **Acurácia como métrica** — calibração se mede com log loss, Brier e curva.
6. **Win rate bruto de composição** — comps fortes são jogadas por times fortes. Controle por mapa, patch e força do time.
7. **Pistol como eco** — excluir rounds 1 e 13 das análises de economia.
8. **Ponte tag → id posicional** — testada, nunca presumida.
9. **Formato da API mudar em silêncio** — é por isso que os fixtures do D3 não são opcionais.
10. **Instância pública cair** — coleta ampla agora, do mais recente para o mais antigo, auto-hospedagem como plano B.
11. **Listagem tratada como cadastro** — `/players` e `/teams` são recortes. Dimensões vêm das partidas.
12. **Agregado do vlr.gg usado como dado** — é arredondado e não fatia por janela nem patch. Serve só de gabarito.

---

## 9. Ideias para depois do D30

- Modelo treinado (regressão logística + LightGBM) com o Elo como baseline — lidando honestamente com o pouco volume da janela.
- Inferência no navegador via ONNX (`onnxruntime-web`), mantendo tudo estático.
- Notebooks convertidos para dentro do site com `nbconvert --no-input`.
- Auto-hospedar a vlresports para não depender da instância pública.
