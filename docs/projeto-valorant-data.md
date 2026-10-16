# VALORANT Data (Meta-Scope-VAL) — Documento mestre do projeto

> Este arquivo é a fonte de contexto do projeto. No repositório: `docs/projeto-valorant-data.md`.
> A auditoria detalhada da API fica em `docs/fontes.md`.
> Última atualização: 16/10/2026 · Status: **D1–D30 concluídos**: warehouse, Elo, análises com IC, notebooks, JSONs e site gerados pelo `make build` · **v1 pronta para publicar**, sem a página de previsões (`PREDICTIONS_ENABLED = False`; passo a passo no D29) · fora do código: telas do Figma (D23) e GIF (D30)
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

**Recortes no site: visão recente de 3 meses e tier (decidido em 16/10).** Nas Análises e no Meta, dois seletores: a janela (12 meses, o padrão, ou os **últimos 3 meses**) e o tier (**VCT**, **VCL** ou todos, como no Ranking). A tese da janela só troca o tier: o drift é o histórico inteiro.
*Por quê:* a visão recente mostra o momento atual de cada mapa e meta, e o VCT isola o alto nível, onde detalhes que se diluem na média podem aparecer (no primeiro build, a vantagem de quem escolhe o mapa é inconclusiva em todos os tiers e aparece só no VCT: 52,8%, IC 50,2–55,4%). O custo é amostra menor: mais inconclusivos, e recortes vazios (a VCL fica fora de temporada no fim do ano), que o site mostra como amostra insuficiente.
*Implementação:* variável dbt `recent_window_months: 3`, um recorte **dentro** da janela de análise (nunca no lugar dela; teste no `fct_match`). Os marts de análise levam `tier` e `is_in_recent_window`; `analyses.Scope` escolhe o recorte e `analyses.table` é o único ponto que filtra. O site pré-computa os seis recortes (janela × tier) em pastas próprias de `dist/data`. Notebooks, home e números de cabeçalho seguem na janela inteira com todos os tiers.

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

**Elo em Python, dentro do dbt (decidido no D15).** `fct_team_elo` é um Python model do dbt-duckdb que chama `pipeline/elo.py`: a única exceção à regra "transformação em SQL", porque o Elo é iterativo (cada partida depende do rating que a anterior deixou). Função pura, testada no pytest; o anti-vazamento é testado no dbt.

**Promoção da VCL ao VCT reancora o Elo (decidido em 16/10).** No primeiro jogo de VCT de um time que começou na VCL, o rating vira `inicial_VCT + c·(rating − inicial_VCL)`: só a fração `c` do desvio conquistado na VCL entra no VCT. Uma vez por time, antes da partida e só com o passado, como a regressão de temporada (`is_promotion` no `fct_team_elo`; o anti-vazamento sabe dela).
*Por quê:* em 2026 os melhores da VCL de cada região jogaram o Stage 2. A VCL é um pool quase fechado, e dominá-la infla o rating sem referência ao VCT: a Enterprise entrou com 1876 depois de 39–4 na VCL, acima de todo time do VCT, e o ranking a punha em 2º com 6 séries de VCT. Na busca em grade (notebook 06), `c = 0,1` com o gap VCT − VCL de 300 dá log loss 0,6630, contra 0,6635 dos parâmetros anteriores; nas séries entre quem veio da VCL e times do VCT a melhora é maior, mas com amostra ainda pequena (IC inclui zero). Descartados: K menor na VCL (piora a previsão dentro da VCL), VCL começando mais abaixo e K provisório maior (pioram as duas).
*Junto:* o ranking marca como **provisório** o time com menos de 10 séries do próprio tier na janela (`rating_provisional_series`): o número é o mesmo, mas ainda está assentando. Rebaixamento (VCT → VCL) não tem regra: ainda sem caso nos dados.

**Estatística em Python, sobre os marts (decidido no D16).** Os marts de análise (`dbt/models/analysis/`) entregam contagens no grão fino, já na janela; IC, bootstrap, Holm, logística e shrinkage ficam em `pipeline/stats.py` e `pipeline/analyses.py`, chamados pelos notebooks **e** pelo site. Um número, uma fonte.

**DuckDB como engine, não como banco.** Arquivo descartável, gerado e destruído a cada build. O `dbt-duckdb` lê os Parquet do lake direto como `sources`.
*Por quê:* o warehouse é artefato de build, não serviço. O DuckDB existe para viabilizar o dbt. O dialeto SQL é baseado no do Postgres.

**Dagster define o pipeline, GitHub Actions dispara.** Não são concorrentes. O `make` e o Actions executam os jobs do Dagster (`ingest` por temporada, `build` para o warehouse); não existe segunda descrição do pipeline em script (confirmado no D12).
*Por quê:* assets particionados por temporada dão backfill, retomada e reprocessamento cirúrgico prontos. A UI do Dagster não vai ao ar; a linhagem pública é o `dbt docs`.

**CI em dois trilhos (decidido no D14).** Todo push roda lint, pytest e o build inteiro (Dagster → dbt → testes → site) sobre um lake gerado dos fixtures do repositório, sem segredo. O trilho real (lake-pull → coleta incremental → lake-push → build → Pages) é manual ou semanal e exige `HF_TOKEN`.
*Por quê:* o dbt fica testado em todo push mesmo sem acesso ao lake, e o resultado do trilho de fixtures não muda com o relógio (`AS_OF_DATE` fixa a janela).

**O que vai para o repositório (16/10, v1).** Entra: o código (`ingestion/`, `dbt/`, `pipeline/`, `dagster_defs/`, `web/`), seeds, fixtures JSON da API, `uv.lock`, as imagens do site (`web/assets/imgs/`: logos, mapas e ícones de agente, porque o CI monta o site a partir do repositório), as figuras do README (`docs/img/`), os notebooks com outputs e a licença MIT do código. Fica fora (`.gitignore`): `data/` (o lake vai para o dataset privado do Hugging Face), `dist/` (o CI gera e publica), o warehouse `*.duckdb`, caches e logs, o protótipo `design-reference/` (conteúdo fictício) e docs pessoais (`docs/estrutura.md`, `docs/post-linkedin.md`).
*Por quê:* dado não entra no Git, e o site precisa ser reprodutível só com o repositório e o lake. Mapas e ícones são da Riot: uso de fã, sem fins comerciais, com o aviso da política "Legal Jibber Jabber" no README e no rodapé.

**Dimensões como retrato, época nos fatos (decidido no D10).** `dim_team` e `dim_player` têm uma linha por id, com nome, tag e região mais recentes; o nome e a tag da época da partida ficam nos fatos. Sem SCD tipo 2.
*Por quê:* o site e os joins querem o nome atual; a análise histórica já tem o nome da época na própria linha do fato.

**Exceção de qualidade é escrita, não tolerada (decidido no D13).** Divergência aceita contra o gabarito do vlr.gg ou nas checagens de série vai para o seed `validation_exceptions.csv`, com motivo. O teste falha em qualquer outra.

**Notebooks em matplotlib, ficam no repositório, linkados do site.**
*Por quê:* o visualizador do GitHub não executa JS. Interativo existe só no site.

**`schedule` semanal ligado no D29, guardado pela variável `PAGES_ENABLED`.** Sem a variável, o cron não dispara o build real e nada publica. `workflow_dispatch` ativo desde o início.

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
│   ├── models/marts/            dim_*, fct_* (inclui fct_team_elo, Python model)
│   ├── models/analysis/         mart_*: marts de análise na janela (e os de drift, fora dela)
│   ├── seeds/patches.csv        datas de cada patch, mantido à mão
│   ├── seeds/event_overrides.csv eventos a excluir ou reclassificar, mantido à mão
│   ├── seeds/validation_exceptions.csv divergências aceitas do D13, com motivo
│   └── tests/                   testes singulares de qualidade (D13)
├── pipeline/
│   ├── elo.py                   Elo pré-partida (chamado pelo Python model fct_team_elo)
│   ├── stats.py                 Wilson, bootstrap por cluster, Holm, logística, shrinkage, calibração
│   ├── analyses.py              uma função por pergunta, sobre os marts (notebooks e site)
│   ├── plots.py                 estilo matplotlib dos notebooks, mesma paleta do site
│   ├── site_artifacts.py        JSONs de dist/data (D22)
│   ├── build_site.py            Jinja2 → dist/ (D24)
│   └── train.py                 placeholder do modelo pós-D30
├── dagster_defs/                assets (coleta + dbt), partições por temporada, checks do lake
├── notebooks/                   matplotlib, com outputs commitados
├── web/                         templates Jinja2, CSS (tokens), tema do ECharts, JS
├── dist/                        gerado, publicado no Pages
├── .github/workflows/build.workflow.yml
├── Makefile                     make build / make serve / make test
├── DEVLOG.md                    3 linhas por dia
└── README.md
```

**Saída do site:**

```
dist/
├── index.html, rankings.html, team.html, meta.html, previsoes.html, analises.html
├── analise-{nome}.html          uma página por pergunta
├── assets/                      style.css, app.js, echarts-theme.js
├── lineage/                     dbt docs
└── data/
    ├── meta.json                versão do build, data, janelas, recortes, patches
    ├── teams/index.json         alimenta rankings e busca
    ├── teams/{id}.json          perfil do time
    ├── agents.json              ícone de cada agente
    ├── predictions/{id}.json    todos os confrontos daquele time
    ├── meta/{recorte}/index.json          fatias mapa × patch disponíveis no recorte
    ├── meta/{recorte}/{mapa}-{patch}.json composições da fatia
    └── analyses/{recorte}/{nome}.json     séries das análises
```

`{recorte}` = janela × tier: `full-all` (o padrão: 12 meses, todos os tiers), `full-vct`, `full-vcl`, `recent-all`, `recent-vct`, `recent-vcl`. Times e previsões não têm recorte.

Use `?v=` do `meta.json` nas requisições de dados para invalidar cache do navegador; CSS e JS levam o hash do próprio conteúdo.

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
*Feito:* `pipeline/elo.py` (Elo sobre a série, empate 0,5, rating inicial por tier, regressão de temporada) materializado pelo Python model `fct_team_elo`; `assert_no_future_leakage` religado sobre o encadeamento antes/depois. Busca em grade pela log loss pré-partida: K = 48, VCT 200 acima da VCL, carry 0,75; log loss 0,663 contra 0,693 da moeda em 5.772 partidas, superfície plana perto do ótimo. Topo da VCT: Enterprise, 100 Thieves, NRG, Paper Rex, LEVIATÁN (`notebooks/06_rating.ipynb`).

**D16 · Marts de análise com janela**
`mart_*` filtrados por `analysis_window_months`. Teste que falha se algum mart de análise ler partida fora da janela (exceto o de drift).
*Feito:* 15 marts em `dbt/models/analysis/`, todos com `not is_excluded` e janela pelas macros; teste genérico `inside_analysis_window` em todos menos os `mart_drift_*`. Estatística em `pipeline/stats.py` (testada no pytest), análises em `pipeline/analyses.py`, com ordem fixa por mart para o bootstrap ser reprodutível.

**D17 · Drift — a tese da janela**
Série trimestral da vantagem de lado por mapa sobre o histórico completo, com patches marcados. Mostra o jogo mudando mesmo em mapas intocados. Desde 2025 o histórico vem do lake; antes disso, de um dataset pronto importado à parte (fonte e formato a definir).
→ *Pronto quando:* o gráfico justifica sozinho a escolha de 12 meses.
*Feito:* a vantagem de lado por trimestre (n efetivo pelo efeito de desenho, homogeneidade com Holm) é **inconclusiva** nos 13 mapas com o histórico desde 2025: o efeito é pequeno demais para a amostra trimestral. A tese se sustenta pela segunda lente, acrescentada aqui: o meta de agentes de cada mapa (`mart_drift_agents_by_quarter`) se afasta do atual trimestre a trimestre — 0,14 de variação total a 3 meses, 0,33 a 12 ou mais, piso de ruído 0,06. Gráfico em `docs/img/drift-meta.png`. O drift de lado volta a ser testado com o dataset pré-2025.

**D18 · Lado e pistol**
Vantagem atacante/defensor por mapa e pistol → vitória no mapa, dentro da janela. IC por bootstrap, correção para múltiplas comparações.
*Feito:* ataque vence 51,2% (50,8–51,5%) dos rounds 1–24; Abyss, Breeze, Haven e Lotus favorecem o ataque, Ascent a defesa, sete inconclusivos (bootstrap por mapa, 1,36× mais largo que o Wilson ingênuo; Holm). Pistol: com Elo igual, 73,6% de vitória no mapa com dois pistols contra 28,0% com nenhum (logística).

**D19 · Veto e regiões**
Vantagem de quem escolhe o mapa; força relativa entre regiões em confrontos internacionais.
*Feito:* veto por desenho pareado (força dos times se cancela) — 51,5% (49,8–53,2%), inconclusivo; por mapa, contra a probabilidade de mapa derivada do Elo da série (inversão de P(BO3) = p²(3 − 2p)), nenhum mapa sobrevive a Holm. Regiões: China −0,29 (−0,41 a −0,14) abaixo do Elo em 23 séries; as outras inconclusivas (61 séries entre regiões).

**D20 · Meta de composição**
Win rate por comp com shrinkage bayesiano, por mapa e patch. Popularidade de agentes ao longo da janela.
*Feito:* desempenho acima do esperado pelo Elo, com shrinkage empírico normal–normal por mapa × versão do patch (12.x, 13.x): por patch exato a amostra não sustenta (contingência 4, meio-termo). 0 de 536 combinações se distinguem do Elo. Velocidade do meta: variação total mês a mês com piso de ruído; 11 de 12 meses acima do ruído, pico em abril/2026.

### Bloco 4 — Previsão e artefatos · D21–D22

**D21 · Previsões via Elo**
Probabilidade par a par pela fórmula do Elo. Validar calibração dentro da janela: log loss, Brier e curva de calibração.
→ *Pronto quando:* a curva de calibração está num notebook e a matriz de confrontos está em Parquet.
*Feito:* `mart_matchups` (materialização `external`, `data/derived/matchups.parquet`, 196.692 pares) e `notebooks/07_previsao_calibracao.ipynb`: log loss 0,662 (0,651–0,672), Brier 0,233; na VCT, 0,685 (0,658–0,712), indistinguível da moeda.

**D22 · Asset `site_artifacts`**
JSONs particionados conforme a seção 4, com `meta.json` informando versão, data e janela usada.
→ *Pronto quando:* `dist/data/` está completo e o maior arquivo cabe em poucas centenas de KB.
*Feito:* asset `site/site_artifacts` no job `build` (`pipeline/site_artifacts.py`): 929 arquivos, ~5 MB; o maior (`teams/index.json`) tem 86 KB, e o asset check `largest_file_under_limit` (300 KB) roda em todo build.

### Bloco 5 — Produto · D23–D28

**D23 · Design system**
Tokens do CSS existente num arquivo único. Duas telas no Figma (rankings e uma de análise). Densidade compacta.
*Feito:* `web/assets/style.css` com tokens (cor, tipo, espaço, densidade), tema escuro e claro, a mesma paleta dos notebooks (`pipeline/plots.py`). As telas vieram depois, num protótipo do Figma Make (`design-reference/`, local): o site adotou a linguagem visual dele (sidebar, Barlow Condensed + Inter, painéis com fio, KPIs, versus, lista numerada de análises) sem os padrões vetados no CLAUDE.md e sem o conteúdo fictício — cada slot sem dado real recebeu dado real (o radar virou o gráfico do drift; os KPIs, números da janela; o FAQ, a metodologia).

**D24 · Tema de gráfico e gerador**
Tema próprio do ECharts derivado dos tokens. `build_site.py` com Jinja2 gerando `dist/`.
*Feito:* `echarts-theme.js` lê os tokens do CSS em tempo de execução; `pipeline/build_site.py` (asset `site/site_pages`, `make site`) escreve o HTML com as respostas já no texto, a partir dos mesmos JSONs.

**D25 · Telas base**
Home, rankings, busca de times.
*Feito:* home com a tese e as respostas (pergunta, número com IC, veredito), rankings com filtro por tier, região e séries mínimas, busca de times sem acento e por tag.

**D26 · Perfil de time**
Histórico, win rate por mapa, forma, roster.
*Feito:* `team.html?id=`: Elo na janela, mapas com IC de Wilson, forma das 10 últimas, elenco e partidas com o que o Elo dava.

**D27 · Meta + elemento assinatura**
Tela de meta com filtros por mapa e patch. A visualização de veto é o elemento de ousadia visual; resto do site disciplinado.
*Feito:* matriz do veto mapa × passo (cada linha soma 100%: em que passo e por qual ação o mapa sai), clicável; pick rate e composições com shrinkage do recorte.

**D28 · Previsões**
Seleção de dois times, lookup client-side, probabilidade do Elo com aviso de que é estatística, não conselho de aposta. Estados vazios e de erro.
*Feito:* `previsoes.html?a=&b=`, lookup em `predictions/{id}.json`, aviso com a log loss da janela, alerta de circuitos diferentes, estados vazio e de erro.

### Bloco 6 — Entrega · D29–D30

**D29 · Publicação**
Deploy no Pages, `dbt docs` em `/lineage`, links para os notebooks, CI verde. **Ligar o `schedule` semanal.**
*Feito (preparado):* jobs `deploy` (upload-pages-artifact@v5 + deploy-pages@v5) e `schedule` semanal (segunda, 06:00 UTC) no workflow, guardados por `vars.PAGES_ENABLED`. A v1 sai sem a página de previsões (`PREDICTIONS_ENABLED = False`). Para ativar:
1. **Lake atualizado no Hugging Face:** `hf auth login` e `make lake-push`. O CI baixa o lake de lá (`make lake-pull`); o do HF anterior a 15/10 não tem as colunas de logo e ícone, e o build quebraria.
2. **`notebooks/` versionado**, com outputs: o site e o README linkam para eles no GitHub.
3. **Repositório público** (o Pages grátis exige).
4. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
5. Settings → Secrets and variables → Actions:
   - **Secrets** → `HF_TOKEN`, com permissão de escrita (o CI faz `lake-push` depois da coleta);
   - **Variables** → `PAGES_ENABLED` = `true`;
   - `HF_LAKE_REPO`, só se o dataset não for `<usuário>/meta-scope-val-lake`.
6. Actions → build → **Run workflow** em `main`: test → build (lake-pull, coleta, `make build`) → deploy.
7. O site sai em `https://joaogalmeidas.github.io/Meta-Scope-VAL/`, com a linhagem em `/lineage`. Dali em diante, o `schedule` de segunda republica sozinho; se o vlr.gg bloquear o IP do Actions, o build segue com o lake baixado, e a coleta local (`make ingest` + `make lake-push`) põe o dado em dia.

**D30 · Narrativa** 🏁
README definitivo: problema, arquitetura, decisões (seção 2), a tese da janela com o gráfico de drift, resultados com números honestos — inclusive os inconclusivos. GIF de 30s, post no LinkedIn.
*Feito:* README definitivo com a tese, os resultados com IC e as limitações; rascunho do post em `docs/post-linkedin.md`. O GIF fica para depois da publicação.

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
