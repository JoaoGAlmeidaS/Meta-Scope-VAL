# DEVLOG

Regra diária: **um commit e três linhas** — o que fiz / o que quebrou / decisão tomada.

---

## D1 — Esqueleto

- **Fiz:** estrutura de pastas, `pyproject.toml` com `uv`, pre-commit (ruff + black),
  `Makefile` com alvos, README com as 8 perguntas de pesquisa, seção de decisões em
  `docs/projeto-valorant-data.md`.
- **Quebrou:** —
- **Decisão:** —

> *Pronto quando:* `make test` roda (mesmo sem testes) e o repo está no GitHub.

## D3 — Fixtures e testes de contrato

- **Fiz:** contrato Pydantic em `ingestion/schemas.py` (só campos consumidos, `extra="ignore"`),
  ponte tag → id por placar em `ingestion/bridge.py`, 142 testes sobre 9 fixtures reais (lado,
  ponte, veto, gabarito de agentes) com a rede bloqueada fora do marker `live`. Removi o
  resquício do scraping (`ingestion/vendor/`, `selectolax`) e alinhei docs aos nomes reais.
- **Quebrou:** nada no contrato: os 9 fixtures passaram sem afrouxar o modelo. Surpresas: a
  partida da VCL veio sem veto, e `roundsCt`/`roundsT` não contam o overtime.
- **Decisão:** ponte por placar como padrão (funciona sem abas, levanta erro se não fechar);
  `economy`/`performance` consumidos por mapa, não no nível da partida.

## D4 — Cliente de coleta

- **Fiz:** `ingestion/client.py` com httpx (timeout 30 s), tenacity (backoff em 429/502/503/504 e
  falha de transporte), rate limiter de 3–6 s que obedece `ratelimit-*` e `retry-after`, e cache
  de conteúdo em disco; 21 testes com transporte e relógio falsos, teste `live` implementado.
- **Quebrou:** API fora do ar; o teste `live` e a conferência do formato de `ratelimit-reset`
  ficaram pendentes. O teste pegou um bug: `max_age_s=0` servia cache gravado no mesmo instante.
- **Decisão:** cache próprio no lugar do hishel (validade é regra de domínio, não header HTTP);
  hishel removido das dependências.

## D5 — Eventos e listagem de partidas

- **Fiz:** coletor de `/events` (tier vct e vcl × 4 regiões + sem filtro), listagem de partidas e
  gabarito de agentes por evento, gravados em Parquet com schema fechado (`ingestion/lake.py`);
  janela e aquecimento lidos do `dbt_project.yml` (`ingestion/config.py`). Coleta real: 548
  eventos candidatos vct+vcl desde 2023; a primeira passada gravou 120 antes de cair (ver D9).
- **Quebrou:** a cota de 30/min é da instância inteira, não do cliente: vazão real de ~6–10 req/min,
  com 429. Internacionais de 2023–2024 aparecem só na região-sede, e partida `upcoming` vem com
  `score: null` (contrato ajustado com fixture novo).
- **Decisão:** histórico desde 2023, China Evolution Series fora, lake no HF privado; partição
  `season=YYYY` com um arquivo por evento (reescrever é o upsert).

## D6 — Detalhe de partida

- **Fiz:** `ingestion/flatten.py` achata o detalhe em `raw_match`, `raw_map`, `raw_veto`,
  `raw_round` e `raw_player_map` (tag → id pela ponte, colunas `team1_*`/`team2_*` na ordem da
  partida), com `raw_reject` e o JSON bruto em `_json/`. A BO5 734308 sai nas cinco tabelas e o
  DuckDB lê com os tipos do schema.
- **Quebrou:** nada nos fixtures; ponte que não fecha num mapa agora anula os ids daquele mapa em
  vez de derrubar a partida.
- **Decisão:** evento gravado inteiro no fim; rejeição não para a coleta, mas 5 seguidas abortam
  (sinal de mudança de formato). `tabs=all` pela data da listagem contra janela + aquecimento.

## D7 — Backfill e lake

- **Fiz:** `backfill` do evento mais recente para o mais antigo, retomável (evento completo no
  lake é pulado, o resto vem do cache), `make backfill` com log em `logs/`, e `lake push|pull` no
  dataset privado do HF. Validação real (feita no D9): 2977 com 60 partidas em 5 min, zero
  rejeições; 2962 (Challengers Brasil) com 66, das quais 10 caíram no contrato.
- **Quebrou:** a coleta de eventos morreu num 502 persistente do gabarito de um único evento
  (`/events/1309/agents`), e o índice `raw_event` só era gravado no fim. Corrigido no D9.
- **Decisão:** o backfill roda no tmux do usuário; o login do HF (`hf auth login`) é passo manual.

## D8 — Região dos times e patches

- **Fiz:** `patches.csv` com 89 patches (5.12 a 13.06) tirados do CMS oficial da Riot, e
  `event_overrides.csv` com 33 linhas; testes do dbt nos dois seeds (ordem dos patches,
  valores aceitos, reclassificação que muda algo).
- **Quebrou:** a regra "evento em várias regiões = internacional" falha antes de 2025 (5 eventos
  reclassificados à mão) e a VCL chinesa aparece em duas regiões.
- **Decisão:** região do time = região do evento doméstico mais recente antes da partida (vai para
  o `dim_team` no D10); qualificatórias abertas fora, marcadas como julgamento.

## D9 — dbt + DuckDB

- **Fiz:** sources no lake por `LAKE_DIR` (Hive por temporada, `union_by_name`), nove `stg_*` com
  tipos e nomes padronizados e deduplicação por chave, DuckDB em UTC; lake de fixtures
  (`ingestion/fixture_lake.py`) passando pelo backfill de verdade com um cliente offline.
- **Quebrou:** a coleta de eventos do D5 (gabarito opcional derrubava tudo; índice perdido na
  queda). Agora gabarito falho não para nada, 3 listagens seguidas sem resposta abortam, o índice
  é gravado mesmo na queda e partida `unavailable` volta para a fila na execução seguinte.
- **Decisão:** CI em dois trilhos (fixtures sem segredo em todo push; lake real só com
  `HF_TOKEN`); o dbt sempre roda de dentro de `dbt/`.

## D10 — Dimensões

- **Fiz:** `dim_event` (overrides aplicados), `dim_team`, `dim_player`, `dim_map`, `dim_patch`,
  macros de janela (`as_of_date`, `analysis_window_start`, `elo_warmup_start`) e a região do time
  na época por ASOF JOIN (`int_team_match_regions`), com teste unitário de time que muda de região.
- **Quebrou:** nada; os times de 2022 do fixture ficam sem região (só jogaram internacional), como
  manda a regra.
- **Decisão:** dimensão é retrato (nome, tag e região mais recentes); o nome e a tag da época
  ficam nos fatos, sem SCD. `AS_OF_DATE` fixa a janela no CI.

## D11 — Fatos

- **Fiz:** `fct_match`, `fct_map`, `fct_veto`, `fct_round`, `fct_player_map` e `fct_composition`,
  com flags de janela e de exclusão em vez de filtro. O lado de cada time sai do lado do vencedor
  round a round, overtime incluído; pistol vira `pistol` na economia.
- **Quebrou:** um `case ... else` punha o perdedor no ataque quando o lado vinha nulo; pego pelo
  caso da pegadinha 22 e coberto no teste unitário do `fct_round`.
- **Decisão:** fatos cobrem todo o histórico coletado; janela e exclusão são filtro dos marts de
  análise (D16), e o drift (D17) lê tudo.

## D12 — Dagster

- **Fiz:** multi-asset `lake/raw_*` particionado por temporada, dbt via dagster-dbt (os testes do
  dbt viram asset checks, os sources viram os assets da coleta), checks próprios do lake, jobs
  `ingest` e `build`, e a API como resource (`VlrApi`), trocada pelo cliente offline nos testes.
- **Quebrou:** `from __future__ import annotations` transforma a anotação do `context` em string e
  o Dagster recusa; tirado só de `assets.py`.
- **Decisão:** gate do D12 cumprido: o job `build` materializou tudo (`RUN_SUCCESS`); o Dagster
  fica. `make` e o Actions chamam o Dagster.

## D13 — Qualidade

- **Fiz:** testes de rounds × placar, lado × `roundsCt`/`roundsT`, troca no intervalo, pistol
  fora do eco, completude da coleta, pick sem jogo, mapas × placar da série; validação cruzada
  com o gabarito do vlr.gg e o seed `validation_exceptions`. No evento real 2977: 9/9 mapas
  jogados, 261/261 pick rates e 8/8 vitórias no ataque idênticos ao gabarito.
- **Quebrou:** 10 de 66 partidas do Challengers Brasil caíram no contrato: mapas sem histórico de
  lado (pegadinha 22), `loadout` nulo na economia (23) e um adversário "TBD" sem id (24).
- **Decisão:** mapa sem lado entra (tudo ou nada, contrato estrito), `loadout` nulo aceito, time
  sem id continua rejeitado. O `atkWinRate` do vlr.gg exclui o overtime, e a validação também.

## D14 — CI e marco

- **Fiz:** workflow com o trilho de fixtures em todo push (lint, pytest, `make build-fixtures`) e o
  trilho real manual (lake-pull → ingest → lake-push → build); `make build` reconstrói o warehouse
  do zero pelo Dagster e publica o dbt docs estático em `dist/lineage`.
- **Quebrou:** nada no marco: `make clean` → lint → 276 testes → `make build-fixtures` verde.
- **Decisão:** deploy no Pages e `schedule` ficam comentados até o D29; o CI guarda `dist/` como
  artefato. Coleta do CI é só incremental e pode falhar sem derrubar o build.

## Pendências do Bloco 1 — coleta completa e lake real (05/10)

- **Fiz:** índice completo com a API de volta (o índice tinha 2), backfill disparado no tmux, primeiro
  push do lake no HF e o primeiro `make build` verde sobre o lake real (33 eventos de 2026), com 12
  pegadinhas novas (26–37). Escopo da coleta reduzido a 2025+ e sem o tier 2 chinês (154 eventos,
  ~7.329 partidas).
- **Quebrou:** a coleta abortou duas vezes (404 em partida apagada, abas vazias) e o build achou
  ponte quebrada por caixa de tag e por razão social chinesa, mapas de lobby remake fora do gabarito
  e jogador fundido; um build sobre o lake vivo leu um evento pela metade.
- **Decisão:** defeito conhecido da fonte vira rejeição `source`, que não aborta; validação aceita
  as duas leituras do mapa refeito e só valida eventos em escopo; jogador fundido rejeita a partida;
  VCT China 2978 com exceções escritas; build sempre sobre cópia do lake. Coleta própria só desde
  2025: o pré-2025 do drift vem de dataset pronto; metadados de 2023–2024 removidos do lake e do HF.
  VCL China e China Evolution Series fora da coleta (`is_china_tier2`), também removidos.

## Coleta 2025+ concluída (06/10)

- **Fiz:** backfill desde 2025 terminou às 03h30 (7.329 listadas: 7.004 gravadas, 325 rejeitadas
  com motivo, 0 faltando) e o lake está idêntico no HF. O build no lake completo achou e corrigi:
  formato "2 maps" com empate (38), veto digitado errado duplicando mapa (39) e W.O. de mapa no meio
  da série, agora contado em `raw_match.n_maps_without_data` (33); lake regravado do cache.
- **Quebrou:** a validação cruzada ainda diverge em 9 eventos (variantes da nota de lobby remake e
  "Map N" fora da posição; China; Japan Finals) e 17 partidas caíram no contrato por formatos novos.
- **Decisão:** placar da série e pick sem jogo descontam os mapas de W.O.; empate só em mapas fixos;
  pendências da validação registradas em `docs/fontes.md` para a próxima sessão.

## Fechamento do Bloco 2 (07/10)

- **Fiz:** `make build` verde sobre o lake completo 2025+ (7.019 partidas; HF idêntico). Showmatches
  fora da análise (41), time sem tag recuperado (40), método por round (31), mapa refeito pela ordem
  do veto e mapa sem estatística fora da validação (36); qualificatórias do SEA excluídas por
  julgamento; 47 exceções escritas, cada uma com motivo.
- **Quebrou:** o gabarito do vlr.gg é inconsistente (ora conta o mapa refeito, ora não; conta o
  showmatch no Japan Finals e não no VCT) e a China segue com mapas a mais sem explicação.
- **Decisão:** validação aceita a leitura que bate e escreve o resto como exceção; showmatch liga
  `is_excluded`. Bloco 3 liberado depois do commit e do 1º CI verde no GitHub.

## Bloco 3 — Análise estatística (13/10)

- **Fiz:** CI verde de novo (ruff do pre-commit e do `uv` divergiam sobre `dbt`: hooks locais via
  `uv run`). Elo em `pipeline/elo.py` como Python model `fct_team_elo`, com o anti-vazamento
  religado; 15 marts em `dbt/models/analysis/` com o teste `inside_analysis_window`;
  `pipeline/stats.py` e `pipeline/analyses.py`; 9 notebooks executados, um por pergunta.
- **Quebrou:** a vantagem de lado por trimestre é inconclusiva nos 13 mapas, então o gráfico do D17
  não justificava a janela sozinho. O bootstrap dava IC diferente a cada leitura porque o DuckDB
  devolve as linhas em ordem não determinística.
- **Decisão:** a tese da janela passa a ter duas lentes. O meta de agentes por mapa vai de 0,14 a
  0,33 de distância (piso de ruído 0,06) e sustenta a janela; o drift de lado fica inconclusivo e
  volta com o pré-2025. Ordem fixa por mart (`ORDER`, com teste). A composição usa a versão maior
  do patch (por patch exato a amostra não sustenta). O Elo prevê a série, e a análise por mapa
  inverte P(BO3).

## Bloco 4 — Previsão e artefatos (13/10)

- **Fiz:** `mart_matchups` em Parquet (196.692 pares); calibração com log loss 0,662 contra 0,693
  da moeda. Asset `site/site_artifacts`: 929 JSONs, o maior com 86 KB, e o check de 300 KB em todo
  build.
- **Quebrou:** sobre o lake de fixtures, as análises caíam com amostra mínima (quadros vazios sem
  coluna, patch nulo, logística sem convergir), e o JSON arredondado a 4 casas dava 51,1% onde o
  notebook dizia 51,2%.
- **Decisão:** as análises devolvem quadros vazios com colunas, e a logística só roda com 100 mapas
  ou mais (o site mostra "amostra insuficiente"). O JSON guarda 6 casas, e só o texto arredonda.

## Blocos 5 e 6 — Site e entrega (13/10)

- **Fiz:** design system em `style.css` (tokens, tema escuro e claro), tema do ECharts lido dos
  tokens, `build_site.py` (asset `site/site_pages`). Páginas: home, rankings, perfil, meta com a
  matriz do veto, previsões e uma página por análise, conferidas no Chrome headless sem erro no
  console. Deploy e schedule semanal guardados por `PAGES_ENABLED`, README definitivo e rascunho do
  post.
- **Quebrou:** a primeira matriz do veto só repetia a ação de cada passo. O navegador servia JS
  velho com o mesmo `?v=` dos dados. A barra de IC era colorida pelo IC cru, contradizendo o
  veredito com Holm.
- **Decisão:** na matriz do veto, cada linha soma 100% (em que passo e por qual ação o mapa sai). O
  asset leva o hash do conteúdo, e o JSON, a versão do build. A cor segue o veredito. O Pages fica
  preparado, e o usuário ativa; ficam de fora o Figma e o GIF.

## Interface no visual do Figma Make (14/10)

- **Fiz:** o site adotou o protótipo de `design-reference/`: sidebar e topbar, Barlow Condensed +
  Inter, painéis com fio, KPIs, versus nas previsões, análises em grade numerada, badges por região
  e sparkline do Elo no ranking (`trend` em `teams/index.json`). Funcionalidades iguais; nas páginas
  de análise só o visual mudou. Conferido no Chrome headless em escuro, claro e 600 px, sem erro no
  console, e no lake de fixtures (estados vazios).
- **Quebrou:** o seletor dos rótulos de KPI pegava os spans de dentro (forma e IC); o corte
  diagonal do hero comia o eixo do gráfico; o destaque flutuante cobria o eixo.
- **Decisão:** do Figma fica a linguagem visual; os vetados do CLAUDE.md continuam vetados e o
  conteúdo fictício não entra (radar → drift, KPIs da janela, FAQ de metodologia). A marca
  continua MetaScope VAL. `--accent` (marca) separado dos tokens de dado, então notebooks e
  `docs/img` não mudam. Depois voltou uma animação: só a entrada sutil da página (0,3 s), desligada
  com `prefers-reduced-motion`; por seção continua vetado.

## Cores das regiões (14/10)

- **Fiz:** regiões em laranja (americas), amarelo (emea), azul (pacific) e vermelho (china), no CSS
  (os dois temas), no `plots.py` e no notebook 04; a china saiu do ciclo padrão do ECharts.
- **Quebrou:** laranja, amarelo e vermelho se confundem para daltônicos e, no tema escuro, um
  amarelo vivo estoura a banda de luminosidade dos outros; as iniciais do badge da china sumiam no
  fundo escuro.
- **Decisão:** tons validados com a skill dataviz, separados pela luminosidade (vermelho escuro,
  laranja médio, amarelo claro): mostarda e laranja queimado no escuro. Os WARN restantes (contraste,
  ΔE 7,8 no escuro) valem porque o nome da região está sempre ao lado; o texto do badge mistura a
  cor da região com a do texto.

## Previsões em desenvolvimento e imagens (15/10)

- **Fiz:** Previsões viraram "em desenvolvimento" (flag `PREDICTIONS_ENABLED` no `build_site.py`;
  versus, JS e JSONs preservados), FAQ 04 passou a explicar o rating, a análise 07 virou
  "Calibração do Elo", a Linhagem saiu da sidebar (fica no rodapé) e logo/favicon em
  `web/assets/imgs/` entram sozinhos pelo nome.
- **Quebrou:** a pasta `web/assets/imgs/` derrubava o `make site` (o hash do cache lia cada item
  de `web/assets` como arquivo); a sidebar espremia a marca em janela baixa.
- **Decisão:** hash recursivo por caminho relativo (imagens também ganham `?v=`); a página de
  previsões sai de um template à parte para religar com uma linha; marca e rodapé da sidebar com
  `flex: none`, e quem rola é a nav.

## Logo do site por tema e logos dos times (15/10)

- **Fiz:** logo do site em duas versões (`logoE` escuro, `logoC` claro), também como favicon por
  tema; logos dos times pela API: `teams[].img` no contrato → `raw_match.team*_img` → `dim_team.logo_url`
  → JSON do site, com override manual em `web/assets/imgs/teams/{id}`. Lake regravado do cache
  (`backfill --force`: 155 eventos, 7.090 partidas, só as 4 rejeições de contrato conhecidas);
  342 de 497 times da janela com logo.
- **Quebrou:** ~21% das aparições trazem o placeholder genérico do vlr.gg (pegadinha 42), e logos
  pretos sumiam no tema escuro.
- **Decisão:** placeholder vira nulo no contrato e o badge cai nas iniciais; logos carregados do
  CDN do vlr.gg, com contorno do tema (`--logo-halo`); o lake no HF só ganha a coluna com o
  `make lake-push` do usuário.

## Ícones dos agentes (15/10)

- **Fiz:** `players[].agents[].img` no contrato → `raw_player_map.agent_img` → `dim_agent` (novo,
  com teste) → `data/agents.json`; ícone nas linhas de agente do meta, nas composições, no elenco
  e nos rótulos do heatmap de pick rate. Lake regravado do cache de novo (mesmos 7.090 / 4).
  `make agent-icons` baixou 29 ícones para `web/assets/imgs/agentsV/`.
- **Quebrou:** o `www.vlr.gg` responde 403 a imagem com Referer de outro site (o owcdn.net dos
  logos de time não bloqueia); a análise de composições tinha um painel de gráfico vazio.
- **Decisão:** ícones de agente servidos de cópia local, baixada uma vez e nunca sobrescrita
  (arquivo do usuário vence); nada de contornar o bloqueio. Agente sem ícone (o id
  `b444168c-…`, 404 até no vlr.gg) fica com as iniciais. Painel de gráfico só onde há gráfico.

## Meta: banner do mapa e time que mais usou (15/10)

- **Fiz:** banner com a foto do mapa (`imgs/maps/`, posta pelo usuário) e o nome no centro entre
  os filtros e os KPIs; ícone do agente no KPI "Agente mais escolhido"; coluna "Time que mais usou"
  nas composições (`analyses.top_users`, com teste), com logo e link para o perfil.
- **Quebrou:** as imagens vieram como `Haven.webp` e a busca era em minúsculas (o Pages diferencia
  maiúsculas); com a coluna nova, a tabela passava da largura do painel.
- **Decisão:** a busca de imagem casa sem diferenciar maiúsculas e devolve o nome real do arquivo;
  composições quebram em duas linhas e a contagem do time vai embaixo do nome. Sem foto (Summit),
  o banner fica com o nome sobre o brilho do acento.

## Recortes: visão de 3 meses e tier nas Análises e no Meta (16/10)

- **Fiz:** seletores de janela (12 meses | 3 meses) e tier (VCT | VCL | Todos) nas oito análises e
  no Meta; a tese da janela só troca o tier. Var `recent_window_months: 3`, `is_in_recent_window`
  no `fct_match` (dentro da janela, testado), `tier` e visão recente nos marts de análise;
  `analyses.Scope` e `table(…, scope)` como único filtro; seis recortes pré-computados em
  `dist/data/{analyses,meta}/{recorte}/`; uma resposta por recorte no HTML.
- **Quebrou:** nada no padrão: `full-all` saiu idêntico aos JSONs anteriores (mesmo `as_of`). Os
  agregados (popularidade, veto por passo, drift) precisaram somar contagens entre tiers antes da
  taxa; a VCL não tem partida desde julho, então VCL × 3 meses fica quase vazio (amostra
  insuficiente, Meta sem fatia).
- **Decisão:** a visão recente é recorte dentro da janela, nunca substituta; recorte que o mart não
  tem é erro, não filtro ignorado; o recorte acompanha a navegação pela sessão (`sessionStorage`)
  e pela URL (`?w=recent&tier=vct`). Primeiro achado: a vantagem de quem escolhe o mapa só aparece
  no VCT (52,8%, IC 50,2–55,4%). Depois: a análise do veto apareceu sem o seletor no navegador —
  o `http.server` não manda `Cache-Control` e o HTML velho ficava em cache; o `make serve` passou
  a usar `pipeline/serve.py`, com `no-cache` (revalida e responde 304 quando não mudou).

## Elo: promoção da VCL e o Project Blender (16/10)

- **Fiz:** Project Blender 2026 excluído pelo seed (torneio aberto que o vlr.gg lista como VCT) e
  teste de aviso para o próximo caso; reancoragem do Elo na estreia no VCT de quem veio da VCL
  (`promotion_carry`, `is_promotion` no `fct_team_elo`, anti-vazamento ciente); busca em grade do
  notebook 06 com o parâmetro novo; selo "provisório" no ranking (< 10 séries do próprio tier).
- **Quebrou:** a Enterprise aparecia em 2º com 6 séries de VCT (entrou no Stage 2 com 1876 depois de
  39–4 na VCL), e CGN, BONK e Misa viravam "VCT" pelo Blender, que punha 64 times amadores no Elo
  com o rating inicial do VCT. O teste novo acusava falso positivo no lake de fixtures (eventos de
  2–4 times): passou a exigir 8 times ou mais.
- **Decisão:** K 48, VCT 300 acima da VCL (era 200), carry 0,75 e promoção 0,10, o ótimo da grade:
  log loss 0,6630 (era 0,6635); na calibração, 0,6609 no total e 0,6830 no VCT (eram 0,6633 e
  0,6893). Enterprise em 13º, provisória; topo da home sem provisórios. Rebaixamento sem regra
  até aparecer caso.
  Depois: a tabela do ranking cortava (já passava do painel pelos nomes longos, e a linha "N de
  VCT" na coluna Séries a alargou). O selo fica ao lado do nome, mas a célula do nome tem largura
  máxima (maior a partir de 1366 px) e o nome cede espaço em reticências; três cabeçalhos
  encurtaram (Pico, No circuito, Última, texto inteiro no title). Cabe a partir de 1280 px.

## v1 pronta para o GitHub Pages (16/10)

- **Fiz:** `.gitignore` revisto (lixo do Windows `*:Zone.Identifier`, `dbt/.user.yml`, `.claude/`,
  `*.rar`; saiu a linha morta `!dist/.gitkeep`), licença MIT do código, aviso da Riot (README e
  rodapé), README e documento mestre com a v1 sem previsões, o que vai para o repositório e o
  passo a passo do D29 na ordem real.
- **Quebrou:** nada; achados da varredura: dois arquivos de lixo versionados (saem com
  `git rm --cached`), link do README para o `docs/estrutura.md`, que é local, e o lake do HF sem as
  colunas de logo e ícone (o `make lake-push` vem antes do primeiro deploy).
- **Decisão:** imagens do site (`web/assets/imgs/`) e figuras do README (`docs/img/`) entram no
  repositório, porque o CI monta o site dele; `docs/estrutura.md` fica local; licença MIT só para o
  código (dados do vlr.gg e imagens da Riot fora).
  Depois: o primeiro push quebrou o CI em 2 s (`astral-sh/setup-uv@v10` não existe: desde a v8
  a action não publica tag de major, por segurança); fixada a versão inteira, `@v10.3.0`.
