# VALORANT Data (Meta-Scope-VAL) — Documento mestre do projeto

> Este arquivo é a fonte de contexto do projeto. No repositório: `docs/projeto-valorant-data.md`.
> A auditoria detalhada da API fica em `docs/fontes.md`.
> Última atualização: 29/09/2026 · Status: **D1 a D8 concluídos**, backfill em andamento · decisões pendentes no fim de `docs/fontes.md`
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
*Exceções:* (1) o rating de times usa alguns meses anteriores à janela só como aquecimento, sem aparecerem nos resultados; (2) a análise de drift usa o histórico completo, justamente para demonstrar a tese da janela.

**Coleta ampla, análise restrita.** O backfill cobre 2023→hoje, mesmo que a análise use 12 meses.
*Por quê:* a fonte é uma instância pública de terceiro, e a anterior saiu do ar — o que não for coletado agora pode deixar de existir. Descartar na coleta é irreversível; filtrar na análise é um `WHERE`. E a análise de drift precisa do histórico.
*Por que 2023 e não 2022 (decidido no D5):* 2023 é o início da era franqueada. Antes disso, `tier=vct` mistura Challengers do formato pré-franquia, e o drift ainda fica com mais de três anos de série.

**China Evolution Series fica fora (decidido no D5).** Times franqueados, mas fora do circuito oficial da liga; mesmo racional do offseason. É coletada e excluída no dbt pelo seed `event_overrides.csv`.

**Lake no Hugging Face Datasets, privado (decidido no D5).** `huggingface-hub` já estava na stack e o DuckDB lê o formato direto. Privado para não republicar dados do vlr.gg; o CI usa `HF_TOKEN`.

**Partição por temporada, um arquivo por evento (decidido no D5).** `data/lake/{tabela}/season=YYYY/{event_id}.parquet`. Reescrever o arquivo do evento é o upsert idempotente. Split como partição física foi descartado: os nomes de split da VCL não têm padrão.

**Escopo: só VCT (tier 1) e VCL (tier 2)**, na coleta e na análise. Game Changers, t3, collegiate e offseason ficam de fora. Tier fica como dimensão, para estratificar e ajustar o Elo.
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

**Backfill do mais recente para o mais antigo.** Primeiro a janela de 12 meses e o aquecimento do Elo; depois até 2023.
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

**Dagster define o pipeline, GitHub Actions dispara.** Não são concorrentes.
*Por quê:* assets particionados por split dão backfill, retomada e reprocessamento cirúrgico prontos. A UI do Dagster não vai ao ar; a linhagem pública é o `dbt docs`.

**Notebooks em matplotlib, ficam no repositório, linkados do site.**
*Por quê:* o visualizador do GitHub não executa JS. Interativo existe só no site.

**`schedule` desligado até o D14, ligado semanalmente depois.** `workflow_dispatch` ativo desde o início.

**Particionamento por split/temporada.** Unidade natural do domínio e dos assets do Dagster.

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
│   └── tests/fixtures/          JSON real de partidas
├── dbt/
│   ├── models/staging/          stg_*
│   ├── models/marts/            dim_*, fct_*, mart_*
│   ├── seeds/patches.csv        datas de cada patch, mantido à mão
│   ├── seeds/event_overrides.csv eventos a excluir ou reclassificar, mantido à mão
│   └── tests/
├── pipeline/
│   ├── elo.py                   rating com aquecimento pré-janela
│   ├── predictions.py           probabilidades par a par + calibração
│   └── build_site.py            Jinja2 → dist/
├── dagster_defs/                assets, partições, checks
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
*Feito:* região pelo filtro `region` da API (evento em várias regiões = internacional), temporada pelo nome ou pela data, partição `season=YYYY` com um arquivo por evento. {D5_NUMEROS}

**D6 · Detalhe de partida** ✅
Achatar o JSON nas cinco tabelas raw de `docs/fontes.md`, com tipos forçados. `tabs=all` dentro da janela, só o básico no histórico. Fechar o schema do Parquet.
→ *Pronto quando:* uma BO5 completa está em Parquet nas cinco tabelas.
*Feito:* 734308 nas cinco tabelas, lida pelo DuckDB com os tipos do schema; `raw_reject` e JSON bruto arquivado.

**D7 · Lake + início do backfill** ✅
Configurar Hugging Face Datasets (ou R2). **Disparar o backfill local do mais recente para o mais antigo:** primeiro a janela de 12 meses + aquecimento, depois até 2023. Deixar rodando à noite.
*Feito:* `make backfill` retomável e `make lake-push|lake-pull` no HF privado. {D7_VALIDACAO} O disparo do backfill completo e o login no HF ficam com o usuário.

**D8 · Região dos times e patches** ✅
Região de cada time derivada da liga VCT ou VCL que ele disputa — `/teams/{id}` traz país, não região. Montar à mão os seeds `dbt/seeds/patches.csv` (datas de cada patch) e `dbt/seeds/event_overrides.csv` (eventos a excluir ou reclassificar — o tier do vlr.gg é ruidoso). Jogadores e times **não** saem das listagens — vêm das partidas no D10. Backfill continua.
*Feito:* 89 patches do CMS oficial da Riot; overrides com exclusões (China Evolution Series, torneios de terceiros, qualificatórias abertas) e reclassificação de região. Regra de região do time em `docs/fontes.md`.

### Bloco 2 — Warehouse · D9–D14 ⭐ *núcleo do portfólio*

**D9 · dbt + DuckDB**
`dbt-duckdb`, sources nos Parquet, models de staging com tipagem e nomes padronizados.

**D10 · Dimensões**
`dim_team` e `dim_player` construídas a partir das partidas (id como chave, nome e tag da época), `dim_map`, `dim_event` (com tier), `dim_patch` a partir do seed. Criar a variável `analysis_window_months`.

**D11 · Fatos**
`fct_match`, `fct_map`, `fct_veto`, `fct_round` (com o lado de cada time reconstruído), `fct_player_map`, `fct_composition` (uma linha por time-mapa com os 5 agentes).

**D12 · Dagster** ⚠️ *ponto de corte*
Assets particionados por split, integração `dagster-dbt`.
→ *Gate:* se nada materializar até o fim do dia, corte o Dagster e siga com Actions chamando scripts.

**D13 · Qualidade**
Testes dbt + asset checks: rounds batem com o placar, lado reconstruído bate com `roundsCt`/`roundsT`, pistols fora das métricas de eco, forfeits e mapas não jogados tratados.
**Validação cruzada com o vlr.gg**, por evento, contra `/events/{id}/agents`: mapas jogados batem com `played` (completude da coleta), win rate de ataque/defesa bate com `atkWinRate`/`defWinRate` (reconstrução de lado) e pick rate de agentes bate com `pickRate` (composições), com tolerância de arredondamento.
→ *Pronto quando:* `dbt test` passa e você justifica cada exceção.

**D14 · CI e marco** 🏁
`build.workflow.yml` com `workflow_dispatch` ativo e `schedule` comentado. `dbt docs generate`.
→ *Marco:* **um comando reconstrói o projeto do zero.**

### Bloco 3 — Análise estatística · D15–D20

**D15 · Rating de times**
Elo com aquecimento pré-janela, ajuste por tier de evento. Rating calculado sempre com dado anterior à partida.
→ *Pronto quando:* o ranking dentro da janela bate com a percepção do cenário.

**D16 · Marts de análise com janela**
`mart_*` filtrados por `analysis_window_months`. Teste que falha se algum mart de análise ler partida fora da janela (exceto o de drift).

**D17 · Drift — a tese da janela**
Série trimestral da vantagem de lado por mapa sobre o histórico completo, com patches marcados. Mostra o jogo mudando mesmo em mapas intocados.
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
