# Fontes de dados — auditoria da API vlresports

> Entregável do D2, atualizado no D3–D8. **Status: concluído** (29/09/2026).
> Decisões pendentes no fim deste arquivo.

---

## Fonte e escopo

| Item | Valor |
|---|---|
| Instância | `https://vlr.orlandomm.net/api/v1` — pública, servidor Express mantido por terceiro, sem CDN de cache aparente |
| Código | github.com/Orloxx23/vlresports — open source, auto-hospedável (plano B, não necessário por ora) |
| Versão da API | v1.0.9 (OpenAPI 3.1.0). Guardar a especificação em `docs/openAPI-doc.json`; se a versão mudar, reauditar |
| Escopo | Só **VCT** (tier 1) e **VCL** (tier 2). Game Changers, t3, collegiate e offseason ficam de fora |
| Rate limit declarado | **30 requisições por 60 s**, via headers `ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset`, `ratelimit-policy: 30;w=60` |
| Limite real | O vlr.gg estrangula a instância compartilhada: **502 e 503 aparecem abaixo de 30/min** (rajada de 10 requisições a ~1/s: 4 × 200, 1 × 502, 4 × 503, recuperou na 10ª). E a cota de 30/min é **da instância**, dividida entre todos os usuários: no D5 a vazão real foi de ~6–10/min (pegadinha 21) |
| Tempo de resposta do detalhe | 3 a 5 s. Sem abas 5,1 s; com `tabs=all` 5,8 s (medido na 734308) |
| Ritmo seguro | Sequencial, **~1 requisição a cada 3–6 s** (10–20/min), retry com backoff em 429/502/503/504 |
| Duração do backfill | ~1h40 por mil partidas. Janela VCT + VCL: uma noite. Histórico: mais uma a duas noites. Contagem exata no D5 |

---

## Endpoints

| Endpoint | O que entrega | Uso no projeto |
|---|---|---|
| `/events` | Eventos, 50 por página, com filtros `status`, `region` (americas, emea, pacific, china) e `tier` (vct, vcl, t3, game-changers, collegiate, offseason) | **Início do backfill**: `tier=vct` e `tier=vcl` (D5) |
| `/events/{id}/matches` | Todas as partidas de um evento, filtráveis por `stage` e `status` | **Listagem de partidas** (D5) |
| `/matches/{id}` | Veto, mapas, rounds com lado e método, stats e agentes por jogador por mapa. Abas opcionais via `tabs` | **Fonte principal** (D6) |
| `/events/{id}/agents` | Por mapa: mapas jogados, win rate de ataque/defesa, pick rate de agentes | **Gabarito** para a validação cruzada do D13 |
| `/events/{id}` | Detalhe do evento, estágios, rosters, chaveamento | Metadados de estágio se necessário |
| `/teams/{id}` | Nome, logo, país e roster **atual** | Não traz região. Enriquecimento opcional |
| `/players/{id}` | Perfil e stats por agente | Enriquecimento opcional |
| `/events/{id}/stats` | Estatísticas de jogadores no evento | Não usado |
| `/results` | Resultados paginados | Não usado — substituído pela rota de eventos |
| `/players`, `/teams` | Leaderboard e ranking | **Não usar como cadastro** (pegadinha 7) |
| `/matches` | Partidas futuras e ao vivo | Fora de escopo |

---

## Tabelas raw (fechadas no D6)

Schema com tipos forçados em `ingestion/lake.py` (`SCHEMAS`). Layout:
`data/lake/{tabela}/season=YYYY/{event_id}.parquet`, com `season` só no caminho (chave Hive).
`raw_event` é um arquivo único, com `season` como coluna.

| Tabela | Grão | Chave |
|---|---|---|
| `raw_event` | evento | `event_id` (+ tier, `tier_ambiguous`, região, temporada) |
| `raw_event_match` | evento × partida listada | `event_id`, `match_id` |
| `raw_event_agents` | evento × mapa × agente (gabarito) | `event_id`, `map_name`, `agent` |
| `raw_match` | partida | `match_id` |
| `raw_map` | partida × mapa jogado | `map_id` (+ `map_order`, que só existe pela posição no array) |
| `raw_veto` | partida × passo do veto | `match_id`, `step` |
| `raw_round` | mapa × round, com economia dos dois times quando houver | `map_id`, `round_number` |
| `raw_player_map` | mapa × jogador, com agente e stats | `map_id`, `player_id` |
| `raw_reject` | partida que falhou no contrato, na API ou não estava finalizada | `match_id` |

Colunas `team1_*`/`team2_*` seguem sempre a ordem de `teams[]` da partida; tag → id pela ponte
por placar. Se a ponte não fecha num mapa, os ids dele ficam nulos e `raw_map.bridge_ok = false`.

O JSON bruto de cada detalhe fica em `data/lake/_json/season=YYYY/{event_id}.jsonl.gz`. Kill
matrices e `performance` existem só ali até haver uso.

---

## Pegadinhas

1. **`rounds[].side` é o lado de quem venceu o round.** Não documentado. Confirmado batendo com `roundsCt`/`roundsT` (Bind, partida 130691: OpTic venceu 7 rounds com `side: "t"` e `roundsT: 7`). É o que permite reconstruir o lado de cada time em cada round. **`roundsCt` e `roundsT` contam só o tempo regulamentar (rounds 1–24)**; `score` inclui o overtime. Num mapa 14–12, os dois times têm `roundsCt + roundsT = 12` (confirmado no D3: Ascent e Haven da 734308, Lotus da 707490).

2. **O mesmo time aparece de três formas.** Id + nome em `teams[]` do detalhe; só nome em `maps[].teams`, `maps[].pickedBy` e na lista de partidas do evento; tag em `rounds[].winner`, `picksBans`, `players[].teamTag` e `economy.teams`. A ponte tag → id posicional (`economy.teams[i]` ↔ `teams[i]`) só existe com `tabs=economy`; na resposta básica a ponte é por placar (`ingestion/bridge.py`). As duas concordam na 734308 (teste do D3). A chave é sempre o `id` — o nome é o da época ("KIWOOM DRX" já mudou).

3. **Multikills e clutches por mapa vêm sempre zerados** — confirmado em 2022 (130691) e em 2026 (734308). O agregado da partida tem valores. É defeito do parser: **inutilizável por mapa**.

4. **Pistol é classificado como `eco`.** Rounds 1 e 13 entram nos totais de eco do resumo de economia. Excluir antes de qualquer análise de conversão de eco.

5. **Kill matrix e `performance` identificam jogador só pelo nome**, sem id. Join por `(nome, tag)` dentro da mesma partida.

6. **Tipos inconsistentes.** `rating` pode vir inteiro (`1`); `duration` mistura `h:mm:ss` e `mm:ss`; `prizepool` é string; nomes de agente capitalizados em `players` e minúsculos em `performance` e em `/events/{id}/agents`. O schema força tipos, nunca infere.

7. **Endpoints de listagem são recortes, não cadastros.** `/players` é o leaderboard de estatísticas do vlr.gg, ordenado por rating e cortado nos 100 primeiros (confirmado). A documentação o descreve como "todos os jogadores profissionais" — só o VCT franqueado já passa de 200. **A documentação não substitui teste.**

8. **`teamTag` em `/players` é o time atual, não o histórico.** Jogador sem time recebe o próprio nome como tag ("Ray", "MONSTEERR", "runneR"). `/teams/{id}` segue a mesma lógica: roster atual.

9. **O mesmo campo muda de significado entre endpoints.** Em `/players`, `country` é código ISO; no detalhe de partida, `country` é o nome e o código fica em `flag`. `limit` volta como string. A paginação também muda: `/players` tem bloco `pagination`, `/events` só tem `size` — o fim é detectado por `data` vazio.

10. **Abas do detalhe são opcionais.** `tabs=performance`, `economy` ou `all`. Sem `tabs`, a resposta já traz rounds com lado e método, veto e stats por mapa (confirmado na 734308). Cada aba é uma requisição extra do servidor ao vlr.gg; o custo em tempo medido foi pequeno (+0,65 s), mas a carga recai sobre o gargalo real. Com abas, `economy` e `performance` aparecem **por mapa** (`maps[].economy`, com rounds) e **na partida** (`data.economy`, com `rounds` vazio). O contrato consome só o nível do mapa.

11. **`/teams/{id}` não traz região**, só país. Região do time é derivada da liga VCT ou VCL que ele disputa.

12. **`/events/{id}/agents` é agregado arredondado.** Win rates e pick rates inteiros, sem contagem de rounds, metodologia não documentada. Semântica confirmada num evento recente de VCT: a soma de `played` por mapa bate com a linha `All`, e os `pickRate` de cada mapa somam ~500% (percentual de composições time-mapa). Serve de gabarito, não de fonte.

13. **O limite declarado não é o limite real.** 30/min nos headers, mas 502/503 aparecem bem abaixo disso — o vlr.gg estrangula o servidor, que é compartilhado por todos os usuários da instância. 503 vem rápido (~0,5 s), 502 depois de ~6 s. O cliente espaça as requisições muito abaixo do declarado e trata 502/503 como transitórios.

14. **Mapa não jogado some de `maps[]`, mas continua no veto.** Em BO3 decididas em 2–0 (734313, 734307, 734312), só dois mapas aparecem; o decisivo não vem nem com `status` diferente. No `picksBans`, ele continua como `remains`. A análise de veto não pode assumir que todo mapa do veto tem linha em `raw_map`. O inverso também acontece: a 707490 (Challengers Brasil) vem com `picksBans.list` vazio e `pickedBy` nulo em todos os mapas. A análise de veto também não pode assumir que toda partida tem veto.

15. **O tier do vlr.gg é ruidoso.** China Evolution Series 2026: Act 3 (3105) aparece em `tier=vct` **e** em `tier=vcl`. O `vcl` inclui eventos como THE POKAL 2026 e China National Tournament: Pro Qualifier. Antes de 2023, `tier=vct` inclui eventos de Challengers do formato pré-franquia ("Champions Tour Korea Stage 1: Challengers"). Deduplicar por `event_id` e corrigir via seed `event_overrides.csv`.

16. **A lista de partidas do evento é pobre em identificadores e datas.** Times sem id (só nome e bandeira); `date` e `time` sem fuso horário; `eta` sem sentido em partida concluída; `dates` do evento sem ano ("Sep 3 13"). Datas e ids vêm sempre do detalhe da partida (`timestamp`, `utcDate`, `teams[].id`).

17. **A região do filtro `region` não separa internacional de doméstico antes de 2025.** Masters e
    Champions de 2025 em diante (e o Masters Shanghai 2024) aparecem nas quatro regiões; LOCK//IN,
    Masters Tokyo, Champions 2023, Masters Madrid e Champions 2024 aparecem só na região-sede. A VCL
    chinesa de 2023–2024 aparece em `china` **e** `pacific`. A coleta marca `international` quando o
    evento aparece em mais de uma região; o resto é corrigido no seed `event_overrides.csv`.

18. **Nenhum endpoint traz o patch da partida.** O vlr.gg mostra o patch na página, a vlresports não
    expõe. O patch sai do seed `patches.csv` pela data. Torneio que trava um patch anterior ao
    vigente fica atribuído ao patch errado — limitação conhecida.

19. **Partida `upcoming` vem com `score: null`** na listagem do evento (Champions 2026, fixture
    `event_matches_ongoing_champions_2026.json`). O contrato aceita nulo só ali.

20. **Nome de evento nem sempre tem ano.** Challengers de 2023 ("Challengers League Brazil: Split 1")
    e todo o circuito 2021–2022 vêm sem ano. A temporada sai do nome (`VCT 2026`, `VCL 26`) ou, sem
    ano, da data da primeira partida listada — que custa uma requisição por evento.

21. **A cota de 30/min é da instância, não do cliente.** No D5, a primeira requisição do dia já veio
    com `ratelimit-remaining: 3`, e houve 429 com o cliente a 10–20/min. A cota é dividida com todos
    os usuários da instância: a vazão real ficou em ~6–10 requisições por minuto.

**Descartes:** `streams`, `picksBans.note`, `eta`, `dates` do evento.

---

## Casos de teste

| Caso | Partida / evento | Status | Observação |
|---|---|---|---|
| BO5 completa, 2022 | 130691 — Champions 2022, OPTC × KRX | ✅ | Agentes em todos os mapas |
| BO5 recente com overtime | 734308 — VCT Americas Stage 2 2026 GF, 100T × LOUD | ✅ | Ascent e Haven com 26 rounds |
| Detalhe sem `tabs` | 734308 | ✅ | Rounds e 10 jogadores por mapa; sem economia e performance |
| Multikills por mapa em 2026 | 734308 com `tabs=all` | ✅ | Continuam zerados: inutilizáveis |
| BO3 decidida em 2–0 | 734313, 734307, 734312 | ✅ | Mapa decisivo ausente de `maps[]` |
| `tier=vct` inclui internacionais | `/events?tier=vct` | ✅ | Masters e Champions presentes desde 2024 |
| Profundidade de `/events` | `tier=vct`, `status=completed` | ✅ | Página 6 com dados (Challengers pré-franquia); página 10 vazia |
| Forfeit | Busca manual na VCL | ✅ | Não encontrado. Decisão defensiva: partida sem mapa jogado é descartada no staging e contada em teste |
| Rate limit | Headers + rajada de 10 | ✅ | 30/60 s declarado; 502/503 abaixo disso |
| `ratelimit-reset` em segundos relativos | `/events?tier=vct` | ✅ | Conferido no D5: `Ratelimit-Reset: 16` com `Ratelimit-Remaining: 3`. O cliente pausa pelos segundos informados |
| Cliente real: 2ª busca sem rede | 734308, `pytest -m live` | ✅ | Rodado no D5, com a instância de volta: uma requisição de rede, contrato ok |
| `/players` | — | ✅ | Leaderboard top 100 por rating. Não usado |
| `/teams/{id}` | Pela especificação | ✅ | Só país e roster atual |
| `/events/{id}/agents` | Evento recente de VCT | ✅ | Somas conferem; 8 mapas no evento |
| Detalhe de partida VCL | 707490 — Challengers 2026 Brazil Stage 2 | ✅ | Retorna igual as partidas do VCT, só não são atualizadas em tempo real. Passa no contrato; veto vazio |
| Lado reconstruído no overtime | 734308, 707490 | ✅ | `roundsCt`/`roundsT` excluem os rounds 25+; `score` os inclui |
| Listagem de evento em andamento | 2766 — Champions 2026 | ✅ | `score: null` nas partidas `upcoming` (pegadinha 19); fixture gravado |
| Filtro `region` de `/events` | tier vct e vcl × 4 regiões | ✅ | Internacional em várias regiões só de 2025 em diante (pegadinha 17) |
| Profundidade de `/events?tier=vcl` | páginas 1–16 | ✅ | 7 páginas com dados; página 4 já em 2024 |
| BO5 completa em Parquet | 734308 com `tabs=all` | ✅ | Cinco tabelas lidas pelo DuckDB com `hive_partitioning`, tipos do schema (`test_lake.py`) |

Fixtures em `ingestion/tests/fixtures/`, com nome descritivo.

---

## Decisões derivadas da auditoria

- **Escopo VCT + VCL**, filtrado na origem pelo parâmetro `tier` de `/events`, deduplicado por `event_id` e corrigido pelo seed `event_overrides.csv`.
- **Backfill pela rota de eventos:** `/events` → `/events/{id}/matches` → `/matches/{id}`.
- **`tabs=all` só na janela** de 12 meses + aquecimento; histórico só com a resposta básica.
- **Backfill do mais recente para o mais antigo.** Se a instância cair no meio, sobra o que as análises usam.
- **Cliente conservador** (`ingestion/client.py`): 3–6 s entre o início de duas requisições, sequencial, retry com backoff exponencial em 429/502/503/504 e em falha de transporte, pausa até o reset quando `ratelimit-remaining` ≤ 1 ou quando vem `retry-after`.
- **Cache de conteúdo, não HTTP:** um JSON por `path + params` em `.cache/api/`, com validade decidida pelo coletor (partida finalizada vale para sempre; listagem expira). Só respostas 200 com `status: OK` entram. Não depende dos headers `Cache-Control` da instância.
- **Jogadores, times, datas e ids vêm do detalhe da partida.** Listagens só servem para descobrir ids.
- **Partida sem mapa jogado é descartada** no staging, com contagem em teste.
- **Região do time** derivada da liga VCT ou VCL que ele disputa.
- **Agregados do vlr.gg são gabarito:** a validação cruzada do D13 compara completude, win rate de lado e pick rate por evento.
- **Schema com tipos forçados** em todas as tabelas raw.
- **Ponte tag → id por placar** (`ingestion/bridge.py`): rounds vencidos por tag em `rounds[].winner` casam com `maps[].teams[i].score`, e o nome casa com `teams[j].name` para chegar ao id. Funciona na resposta básica, a única do histórico. Mapa que não fecha levanta erro em vez de chutar.
- **Contrato em Pydantic** (`ingestion/schemas.py`) com só os campos consumidos e `extra="ignore"`. Os coletores validam toda resposta por ele antes de gravar.
- **Histórico desde 2023** (D5): início da era franqueada; antes disso `tier=vct` mistura Challengers.
- **China Evolution Series excluída** (D5), via seed. A coleta não aplica overrides: tudo que `tier=vct|vcl` devolve é coletado, o filtro é no dbt.
- **Partição por temporada, um arquivo por evento** (D5). Reescrever o evento é o upsert.
- **`tabs=all` pela data da listagem** (D6): partida a partir de hoje − (`analysis_window_months` + `elo_warmup_months`) vem com abas. As duas vars ficam em `dbt/dbt_project.yml` e a coleta lê de lá (`ingestion/config.py`). Data que não parseia pede abas.
- **Gabarito para todos os eventos do escopo** (D5): uma requisição por evento, ~5% do custo da coleta.
- **Evento gravado inteiro, no fim** (D6). Partida que falha no contrato ou na API vai para `raw_reject` e a coleta segue; **5 falhas seguidas abortam** (sinal de mudança de formato). Queda da instância aborta sem gravar o evento em curso; rodar de novo retoma pelo cache.
- **Evento completo no lake é pulado** (D7): status `completed` e toda partida listada já em `raw_match` ou `raw_reject`. `--force` regrava.
- **Região do time** (D8, implementada no `dim_team` do D10): a região do evento doméstico (VCT ou VCL, depois dos overrides) mais recente que o time disputou **antes** da partida. Evento internacional não conta. Time sem evento doméstico anterior herda o primeiro posterior; sem nenhum, região nula e fora da análise regional do D19.
- **Patches pela data de publicação das notas oficiais** (D8), com a URL de origem no seed.

---

## Decisões pendentes

1. **Patch de torneio** (pegadinha 18): aceitar a atribuição por data como limitação documentada, ou
   acrescentar uma coluna de patch por evento em `event_overrides.csv` para os torneios que travam
   patch anterior.
2. **Revisar as linhas `julgamento:` do `event_overrides.csv`**: qualificatórias abertas excluídas
   (NA, NORTH//EAST, China). Relegation, promotion, Ascension e LCQ ficaram dentro.
