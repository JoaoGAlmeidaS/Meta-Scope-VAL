"""Ponte tag → id de time (pegadinha 2 de `docs/fontes.md`).

O mesmo time aparece como id + nome (`teams[]`), só nome (`maps[].teams`) e só tag
(`rounds[].winner`, `players[].teamTag`). A ponte posicional `economy.teams[i]` ↔ `teams[i]`
só existe com `tabs=economy`, que o histórico não usa. Esta ponte funciona na resposta básica:

    1. conta os rounds vencidos por tag em `rounds[].winner` e casa com `maps[].teams[i].score`
       (o placar final de um mapa nunca empata);
    2. casa `maps[].teams[i].name` com `teams[j].name` por nome, não por posição, para chegar
       ao id.

Qualquer ambiguidade levanta `BridgeError`: melhor perder um mapa no staging do que atribuir
rounds ao time errado.
"""

from __future__ import annotations

import re
from collections import Counter

from ingestion.schemas import Map, MatchDetail


class BridgeError(ValueError):
    """A ponte tag → time não fecha para este mapa."""


def tags_by_score(map_: Map) -> dict[str, str]:
    """Tag → nome do time no mapa, casando rounds vencidos com o placar."""
    wins = Counter(r.winner for r in map_.rounds)
    tags = set(wins)
    if len(tags) == 1:
        # Mapa 13–0: o perdedor não aparece em `rounds[].winner`; a tag dele vem dos jogadores.
        tags |= {p.team_tag for p in map_.players}
    if len(tags) != 2:
        raise BridgeError(f"mapa {map_.id}: esperava 2 tags, achei {sorted(tags)}")

    names_by_score = {t.score: t.name for t in map_.teams}
    if len(names_by_score) != 2:
        raise BridgeError(f"mapa {map_.id}: placar empatado, a ponte não decide")

    bridge = {}
    for tag in tags:
        if wins[tag] not in names_by_score:
            raise BridgeError(
                f"mapa {map_.id}: {tag} venceu {wins[tag]} rounds, placar é {names_by_score}"
            )
        bridge[tag] = names_by_score[wins[tag]]
    return bridge


_LEGAL_NAME = re.compile(r"^(?P<full>.+?)\s*\((?P<short>[^()]+)\)$")


def name_keys(name: str) -> set[str]:
    """Formas de um nome de time, sem caixa. Na partida, time chinês vem com a razão social e o
    nome curto entre parênteses ("Wuxi Titan Esports Club (Titan Esports Club)"); no mapa e no
    `pickedBy`, às vezes só o curto (pegadinha 35)."""
    name = name.strip()
    keys = {name.casefold()}
    if m := _LEGAL_NAME.match(name):
        keys |= {m["full"].strip().casefold(), m["short"].strip().casefold()}
    return keys


def team_id_by_name(match: MatchDetail, name: str | None) -> str | None:
    """`teams[].id` da partida pelo nome em qualquer das formas; `None` se não casa ou é ambíguo."""
    if not name:
        return None
    ids = {t.id for t in match.teams if name_keys(t.name) & name_keys(name)}
    return ids.pop() if len(ids) == 1 else None


def tag_to_team_id(match: MatchDetail, map_: Map) -> dict[str, str]:
    """Tag → `teams[].id` da partida, para um mapa dela."""
    bridge = {}
    for tag, name in tags_by_score(map_).items():
        team_id = team_id_by_name(match, name)
        if team_id is None:
            raise BridgeError(f"mapa {map_.id}: {name!r} não está em teams[] da partida")
        bridge[tag] = team_id
    if len(set(bridge.values())) != 2:
        raise BridgeError(f"mapa {map_.id}: as duas tags caem no mesmo time ({bridge})")
    return bridge
