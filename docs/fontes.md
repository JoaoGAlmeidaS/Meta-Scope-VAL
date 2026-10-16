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
| Duração do backfill | Medido no D9: 60 partidas em ~5 min com a cota livre (~12/min); com a cota disputada, metade disso. Em 05/10, ~13/min; escopo 2025+ sem o tier 2 chinês = 154 eventos, ~7.329 partidas (~10 h) |

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
| `raw_reject` | partida que falhou no contrato, na API, não estava finalizada ou não respondeu (`unavailable`, tentada de novo) | `match_id` |

Colunas `team1_*`/`team2_*` seguem sempre a ordem de `teams[]` da partida; tag → id pela ponte
por placar. Se a ponte não fecha num mapa, os ids dele ficam nulos e `raw_map.bridge_ok = false`.
Mapa sem histórico de lado (pegadinha 22) tem `raw_map.has_round_sides = false`.

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

22. **Mapa sem histórico de lado.** O vlr.gg nem sempre tem a linha do tempo de rounds de um mapa:
    vêm o vencedor de cada round, o placar, os jogadores, os agentes e até a economia, mas `side` e
    `method` nulos em **todo** round e `roundsCt`/`roundsT` nulos. Visto no D13 em 681934 (Ascent),
    707213, 707209 e 681918, todas do Challengers Brasil. O contrato aceita o caso, mas tudo ou
    nada: lado pela metade continua quebrando. O mapa entra com `has_round_sides = false` e fica
    fora só das análises de lado. Fixture `match_vcl_map_without_sides_tabs_all.json`.

23. **`loadout` nulo em rounds soltos da economia**, com `bank` e `buy` preenchidos (668479,
    681918, 681920). O contrato aceita nulo nesse campo.

24. **Time sem página no vlr.gg.** Na 668491 o adversário vem como "TBD", `id` nulo e nome vazio nos
    mapas. Sem chave de time a partida não entra: o contrato rejeita, de propósito, e ela fica em
    `raw_reject`. Até o D13, o único motivo definitivo de rejeição (a pegadinha 26 trouxe o `not_found`).

25. **O `atkWinRate` do gabarito exclui o overtime.** Descoberto na validação cruzada do D13 com o
    evento 2977: contando só os rounds 1–24, os 8 mapas batem exatamente com o vlr.gg; com overtime,
    3 erram por 1 p.p. A validação usa a mesma metodologia.

26. **Partida apagada no vlr.gg continua na listagem do evento.** No 3125 (Elevate Play:
    Avalanche, terceiro listado como `vcl`), as partidas da qualificatória aberta (756212 em
    diante) vêm `completed` na listagem, mas o detalhe dá 404 na API e a página dá 404 no próprio
    vlr.gg; os playoffs do mesmo evento respondem normalmente. Derrubou a coleta completa de
    2026 na 1ª tentativa (5 rejeições seguidas). Agora o 404 vira `NotFound` no cliente e rejeição
    definitiva `not_found`, que **não conta para o aborto**: erro de formato (`contract`) e outros
    erros definitivos (`api`) continuam contando.

27. **Aba pedida sem dado.** (O ECS saiu da coleta em 05/10; o caso segue no VCT China.) Com `tabs=all`, partidas do China Evolution Series 2026 Act 3 (3105,
    748619 a 748623) trazem `economy: {teams: [], rounds: []}` e `performance` só com listas vazias,
    nos mapas e na partida. Derrubou a 2ª tentativa da coleta (5 rejeições de contrato seguidas). O
    contrato trata o vazio total como aba ausente (`economy`/`performance` nulos, `has_tabs`
    continua verdadeiro); economia pela metade continua recusada. Fixture
    `match_empty_tabs_tabs_all.json`.

28. **Partida órfã de evento.** A 756175, listada no 3125, vem com o link do evento quebrado:
    `event.id` nulo, nome vazio, `series: ":"`. O contrato rejeita, de propósito (o evento da
    partida é chave); é caso isolado de evento excluído e fica em `raw_reject` como `contract`.

29. **A caixa da tag muda conforme o campo.** Para time com tag que não é toda maiúscula,
    `rounds[].winner` vem em caixa alta ("ARAS", "CATB"), `players[].teamTag` vem como cadastrado
    ("Aras", "Catb") e `economy.teams[].name` vem com o **nome** do time ("Arashi", "Catboys").
    Achado no primeiro `make build` sobre o lake real: 57 mapas com jogador sem `team_id`, economia
    descartada e ponte quebrada nos 13–0 (757797, 747659, 681920 do 2962). O contrato põe toda tag
    em caixa alta (`Tag` em `schemas.py`); o `flatten` casa o rótulo da economia pela tag ou pelo
    nome. Fixture `match_mixed_case_tags_tabs_all.json`, também no lake de fixtures. Partidas
    achatadas antes da correção são regravadas do cache com `--force`, sem rede.

30. **Nota editorial grudada no veto.** Quando o vlr.gg põe uma nota acima do veto ("Map 3 stats
    are incomplete due to lobby remake.", 698906, VCT Pacific Stage 2), o parser cola a nota no
    1º passo: `action: "note"` e, em `map`, a nota com o passo real na última linha ("T1 ban
    Split"). O contrato recupera o passo pela última linha, só se ela tiver o formato de um passo;
    nota sem passo reconhecível continua recusada. Fixture `match_veto_note_tabs_all.json`.
    Variante: partida sem veto com nota (678049 "Map 1 stats are incomplete...", 678062 "The game
    is being postponed due to weather...") traz **só** a nota na lista; vira veto vazio. Fixture
    `match_veto_only_note_tabs_all.json`.

31. **Método de vitória faltando.** A 748625 (China Evolution Series 2026 Act 3) traz `side` em todo
    round e `roundsCt`/`roundsT` completos, mas `method` nulo em todos os rounds; a 433835 (LATAM
    South 2025) e a 450075 (VCT China 2025 Stage 1) trazem o método nulo em rounds soltos. O método
    não entra na reconstrução de lado, então **pode faltar por round** (revisão de 07/10: antes
    era tudo ou nada e derrubava a partida); só o lado continua tudo ou nada (22). Fixtures
    `match_sides_without_method_tabs_all.json` e `match_method_partial_basic.json`.

32. **Substituição no meio do mapa.** Na 678042 (Challengers 2026 LATAM North ACE Stage 2), um
    slot do Haven aparece como "Rayz/Ju4nn", com `id` nulo. O contrato rejeita a partida, como no
    time "TBD" (24): sem id não há chave de jogador, e escolher um dos dois seria chute. Se ficar
    frequente na contagem de `raw_reject`, revisar.

33. **Mapa sem nenhum dado.** Na 669559 (Challengers 2026 SEA Split 2, BO3 2–1), o decider Haven vem
    `played`, 0–0, sem rounds e sem agente em nenhum jogador. O contrato descarta só esse vazio
    total e a partida entra com dois mapas. Mapa vazio pela metade continua recusado. Fixture
    `match_map_without_data_tabs_all.json`. Na 681318 o mapa vazio tem placar (Pearl 13–5) e o
    vlr.gg avisa na nota do veto que os dados estão incompletos. A coleta completa mostrou que o
    caso típico é o **W.O. de um mapa no meio da série** (43 partidas de 2025–26: mapa "TBD" com
    placar nulo; nota "Fraggerz forfeited map 1 due not being ready on time"), que o placar da
    série conta. Por isso o contrato conta os mapas descartados (`maps_without_data`, gravado em
    `raw_match.n_maps_without_data`) e os testes de placar da série e de pick sem jogo descontam
    esses mapas, em vez de uma exceção escrita por partida.

34. **Forfeit tem status próprio e mapas "TBD".** 688778 ("forfeited by team ra'ad"), 688926 e
    688927 ("forfeited by fraggerz", EMEA LCQ 2026): `status` não é `final` e os mapas vêm
    `upcoming` com placar nulo. O coletor olha o `status` cru **antes** do contrato: partida não
    finalizada vira `not_final` e não conta para o aborto. Fixture `match_forfeit_tabs_all.json`.

35. **Razão social na partida, nome curto no mapa.** Times chineses vêm em `teams[]` como "Wuxi Titan
    Esports Club (Titan Esports Club)" e em `maps[].teams` / `pickedBy` como "Titan Esports Club".
    No VCT 2026 China Stage 2 (2978), 55 de 166 mapas ficaram sem ponte e sem placar de um lado. A
    resolução de nome → id (`bridge.team_id_by_name`) aceita o nome inteiro, a parte de fora e a
    de dentro dos parênteses, sem caixa, e descarta casamento ambíguo. Fixture
    `match_cn_legal_name_tabs_all.json`; o VCT China também vem com abas vazias (27).

36. **Mapa refeito por lobby remake, e o gabarito inconsistente.** A nota do veto "Map N stats are
    incomplete due to lobby remake" (variantes: "are partially unavailable", 724620; "are
    unavailable" e "unavailable", 482510 e 459856) marca o mapa N. **N é a ordem da série** —
    picks do veto, na ordem, e o decider por último —, não a posição em `maps[]`: a API pode pôr o
    mapa refeito no fim (459856: "Map 1" é o Split, último em `maps[]`; 482510: o Haven). Sem
    veto, vale a posição. Mapa com placar e jogadores mas **nenhum round** também é marcado: a
    estatística não existe, e o gabarito o deixa fora (2380, 2787, 2801). O vlr.gg **ora** deixa esse mapa
    fora do `/events/{id}/agents` (2776, 2780, 2976: um mapa a mais na nossa contagem, sempre o da
    nota, pick rates desviando até 3 p.p.), **ora** o conta (3063: o gabarito só bate com ele), e
    nada na API diz qual. O mapa entra no lake com `has_complete_stats = false` (placar, Elo e
    composição seguem valendo); a validação calcula cada check com e sem os mapas marcados e aceita
    a leitura que bate. Nota em ~0,75% das partidas. Exceção aberta: no VCT 2026 China Stage 2
    (2978) o gabarito conta 3 mapas a menos (162 × 165) sem nota nenhuma; 17 divergências estão no
    seed `validation_exceptions.csv`, com investigação em aberto.

37. **Jogador sem página fundido em outro.** No 2829 (Challengers 2026 SEA Split 2 – Vietnam
    Qualifier), o VNSport aparece com 4 jogadores em 14 mapas e um deles com dois agentes ("Bumble",
    `Neon` e `Tejo`): o 5º jogador, sem página no vlr.gg, some, e o agente dele é colado no anterior.
    Também em 3125 e 2970 (excluídos). Os mapas com menos de 10 jogadores são exatamente os com
    jogador de vários agentes. O contrato exige um agente por jogador e a partida é rejeitada
    (decisão do usuário: composição nunca pela metade). Fixture `match_merged_player_tabs_all.json`.

38. **Formato de mapas fixos, com empate.** A fase de grupos do Challengers Spain Rising (2317, 2393,
    2792) é jogada em "2 maps": dois mapas sempre, sem desempate. 57 das 118 partidas nesse formato
    terminam 1–1, sem vencedor. `stg_matches` traz `fixed_maps` (o `best_of` fica nulo: não é
    melhor-de-N) e `fct_match` traz `is_draw`; o vencedor só é exigido fora de empate, e empate só
    é aceito em formato de mapas fixos. **O Elo (D15) precisa tratar empate** (0,5 para cada lado).

39. **Veto digitado errado no vlr.gg.** Na 433629 o Abyss é pick **e** decider; na 473235 o decider
    aparece duas vezes. Cinco partidas assim no escopo. O `fct_map` agrega o veto por mapa antes do
    join (o join multiplicava o mapa) e trata mapa escolhido como nunca decider.

40. **Time sem tag.** No Korea WDG (2830), times de nome só em coreano não têm tag no vlr.gg: os
    jogadores vêm com `teamTag: ""` e os rounds que o time venceu, com `winner` nulo (6 partidas
    rejeitadas na coleta de 06/10). O contrato dá aos rounds sem vencedor a mesma tag vazia dos
    jogadores, e a ponte por placar confere a contagem contra o placar do mapa; no staging a tag
    vazia vira nula. Fixture `match_team_without_tag_tabs_all.json`.

41. **Showmatch dentro do evento.** O vlr.gg lista showmatches junto das partidas, com `series`
    "Showmatch: Main Event", "Showmatch: All-Star Match", "Showmatch: Override" (7 no escopo: 2282,
    2497, 2498, 2499, 2500, 2501, 2584). Não são jogo competitivo: o `fct_match` marca
    `is_showmatch` e liga `is_excluded`, que todos os fatos herdam. O gabarito do VCT os deixa fora
    (era o "Corrode a mais" de 2498, 2500 e 2501), e a leitura `complete` da validação também. No
    Japan Finals (2584) o showmatch tem os dois times com a tag "TEAM" e a ponte não os distingue;
    lá o gabarito o conta, e as divergências estão no seed de exceções. A 450589 (Masters Bangkok,
    Team International × Team Thailand, sem agentes) é showmatch rejeitado no contrato, de propósito.

42. **Logo do time com placeholder.** `teams[].img` do detalhe da partida é o logo no CDN do
    vlr.gg (`https://owcdn.net/img/...`); time sem logo vem com a imagem genérica do site,
    `https://www.vlr.gg/img/vlr/tmp/vlr.png` (2.920 de 14.038 aparições no lake de 15/10, ~21%). O
    contrato (`MatchTeam.img`, opcional) anula o placeholder e completa URL sem protocolo; o
    `raw_match` guarda `team1_img`/`team2_img`, e o `dim_team.logo_url` é o logo mais recente. Sem
    logo, o site mostra as iniciais do time. O ícone do agente (`players[].agents[].img`,
    `https://www.vlr.gg/img/vlr/game/agents/{nome}.png`) não tem placeholder: um por agente, vira
    `raw_player_map.agent_img` e `dim_agent.image_url`. Uma única aparição (15/10) traz agente com
    nome de id (`b444168c-4e35-8076-d`, sem ícone válido): o site cai nas iniciais. O `www.vlr.gg`
    responde 403 a imagem pedida com Referer de outro site (o owcdn.net dos logos não bloqueia):
    os ícones são servidos de cópias locais (`make agent-icons`), nunca contornando o bloqueio.
43. **Torneio aberto listado como VCT.** O Project Blender 2026 (evento 3122, out/2026) vem com
    tier VCT no filtro de `/events`, mas é torneio aberto de terceiros: Round of 64 com mixes
    ("cat meow cat", "BRATAN MIX") e nenhum dos 64 times em outro evento VCT. Sem correção, cada
    time amador entra no Elo com o rating inicial do VCT e os times da VCL que o jogam passam a
    ser rotulados de VCT no ranking (a CGN chegou a 11º com um 6–0 contra amadores). O seed
    `event_overrides.csv` exclui; o teste `assert_vct_events_have_vct_teams` (aviso) acusa evento
    VCT em que mais da metade dos times nunca jogou outro VCT.

**Rejeições de contrato restantes (07/10): 4**, todas explicadas. A 450589 é o showmatch do Masters
Bangkok (41). As outras 3 são de qualificatórias do SEA, que estão fora da análise: W.O. da série
inteira com status `final` e mapas "TBD" (611307, 611460) e nota no fim da lista do veto (659576).

**Validação cruzada (07/10, lake completo): build verde.** Divergência só com exceção escrita no
seed `validation_exceptions.csv` (47 linhas, cinco motivos): VCT China 2978 e 2499 (o gabarito conta
mapas a menos sem explicação na API), showmatch com tag repetida no 2584, mapa sem rounds sem
ponte no 2801 e o 2380, em que o gabarito exclui um mapa refeito e conta outro. Mapa sem
estatística (sem duração e sem rating de nenhum jogador, 644253) fica com
`has_complete_stats = false` no `fct_map`, fora da leitura `complete`, como o mapa refeito.

**Descartes:** `streams`, `eta`, `dates` do evento. (`picksBans.note` passou a ser lido: pegadinhas 30 e 36.)

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
| Forfeit | 688778, 688926, 688927 (coleta completa) | ✅ | Achado na coleta completa: status `forfeited by …`, mapas "TBD" com placar nulo. Vira `not_final` antes do contrato (pegadinha 34). A regra defensiva do staging continua |
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
| Gabarito com 502 persistente | `/events/1309/agents` | ✅ | Derrubou a coleta do D5; agora o evento segue sem gabarito e a próxima execução tenta de novo. Em 05/10 continua com 502 (custa ~4 min de retry por execução); o 1309 está excluído pelo seed, então não faz falta |
| Evento real ponta a ponta | 2977 — VCT Americas Stage 2 2026 | ✅ | 60 partidas em 5 min, zero rejeições; validação cruzada idêntica ao gabarito |
| VCL real ponta a ponta | 2962 — Challengers Brasil Stage 2 | ✅ | 66 partidas: pegadinhas 22–24; 65 gravadas, 1 rejeitada (TBD) |
| Mapa sem histórico de lado | 681934 (Ascent) | ✅ | Pegadinha 22; fixture gravado, contrato tudo ou nada |

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
- **Histórico desde 2025** (05/10; era 2023 desde o D5): janela e aquecimento cabem aí, e o pré-2025 do drift vem de dataset pronto. O índice, as listagens e o gabarito de 2023–2024 já coletados foram removidos do lake e do HF; as linhas desses anos no seed de overrides ficam, sem efeito.
- **Tier 2 chinês fora da coleta** (05/10; antes, só o China Evolution Series era excluído pelo seed, no D5): VCL China (`tier=vcl` com `region=china`) e China Evolution Series (pelo nome; o de 2025 só aparece em `tier=vct`) saem em `collectors.is_china_tier2`. São plataformas de terceiros com dados faltando — os casos reais das pegadinhas 27, 31 e 33 vieram quase todos daí. Os 13 eventos de 2025+ já coletados foram removidos do lake e do HF. Fora isso, a coleta não aplica overrides: tudo que `tier=vct|vcl` devolve é coletado, o filtro é no dbt.
- **Partição por temporada, um arquivo por evento** (D5). Reescrever o evento é o upsert.
- **`tabs=all` pela data da listagem** (D6): partida a partir de hoje − (`analysis_window_months` + `elo_warmup_months`) vem com abas. As duas vars ficam em `dbt/dbt_project.yml` e a coleta lê de lá (`ingestion/config.py`). Data que não parseia pede abas.
- **Gabarito para todos os eventos do escopo** (D5): uma requisição por evento, ~5% do custo da coleta.
- **Evento gravado inteiro, no fim** (D6). Partida que falha no contrato ou na API vai para `raw_reject` e a coleta segue; **5 falhas seguidas abortam** (sinal de mudança de formato). Partida que não responde depois de todas as tentativas vira rejeição `unavailable` e também conta para o aborto. Partida com 404 (página apagada no vlr.gg, pegadinha 26) vira `not_found`, definitiva, e **não** conta.
- **Evento completo no lake é pulado** (D7): status `completed` e toda partida listada já em `raw_match` ou `raw_reject` definitivo. Rejeição `unavailable` não conta: o evento volta na próxima execução, e o resto vem do cache. `--force` regrava.
- **Nenhuma falha isolada derruba a coleta** (D9, depois da queda do D5): gabarito indisponível só não grava o arquivo (a próxima execução tenta de novo); listagem indisponível pula o evento, e **3 seguidas abortam** (instância fora do ar); o índice `raw_event` é gravado mesmo quando a coleta cai no meio.
- **Defeito conhecido da fonte é rejeição `source`** (coleta completa): time "TBD" (24), evento órfão
  (28), substituição no mapa (32) e jogador fundido (37) são reconhecidos antes do contrato
  (`schemas.known_source_defect`), vão para `raw_reject` como definitivos e **não** contam para o
  aborto. Só chave presente com valor nulo é caso conhecido; chave ausente continua sendo formato
  novo. Sem isso, um time sem página numa chave inteira travaria a coleta a cada execução.
- **Qualificatórias nacionais do SEA excluídas** (07/10, julgamento): as 10 de 2026 (2818–2822,
  2824, 2826–2829) saem pelo seed, como o NA ACE Qualifier e o NORTH//EAST Open Qualifier.
  Concentravam 31 dos 48 defeitos de fonte e contrato da coleta completa.
- **Validação cruzada só no escopo da análise** (coleta completa): evento excluído pelo seed
  (terceiro, China Evolution Series) não é validado contra o gabarito, e o teste de 5 jogadores
  por composição vale só fora dele. Torneio amador lista 9 jogadores em alguns mapas (3125, 2970).
- **Build nunca sobre o lake vivo** (coleta completa): as tabelas de um evento são gravadas uma a
  uma; um `make build` durante a coleta leu um evento pela metade. O build roda sobre uma cópia.
- **Contrato estrito, casos da fonte explícitos** (D13): mapa sem histórico de lado entra, tudo ou nada (22); `loadout` nulo entra (23); time sem id continua rejeitado (24). Cada caso tem teste de contrato.
- **Região do time** (D8, implementada no `dim_team` do D10): a região do evento doméstico (VCT ou VCL, depois dos overrides) mais recente que o time disputou **antes** da partida. Evento internacional não conta. Time sem evento doméstico anterior herda o primeiro posterior; sem nenhum, região nula e fora da análise regional do D19.
- **Patches pela data de publicação das notas oficiais** (D8), com a URL de origem no seed.

---

## Decisões pendentes

1. **Patch de torneio** (pegadinha 18): aceitar a atribuição por data como limitação documentada, ou
   acrescentar uma coluna de patch por evento em `event_overrides.csv` para os torneios que travam
   patch anterior.
2. **Revisar as linhas `julgamento:` do `event_overrides.csv`**: qualificatórias abertas excluídas
   (NA, NORTH//EAST, China). Relegation, promotion, Ascension e LCQ ficaram dentro.
3. **Vazão da instância pública** (pegadinha 21): com ~6–12 requisições por minuto, o histórico
   completo leva dias. Medido na coleta completa de 05/10: ~13 requisições/min; 16.889 partidas
   em escopo, ~22 h só de detalhes sem contar refazer nada. **Resolvido em 05/10 pelo corte do
   escopo para 2025+ e pela saída do tier 2 chinês** (~7.329 partidas, ~10 h); o plano B (auto-hospedar) segue disponível.
