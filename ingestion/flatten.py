"""Detalhe de partida → linhas das cinco tabelas raw (D6). Funções puras sobre o contrato.

    raw_match       uma linha por partida
    raw_map         partida × mapa jogado; `map_order` só existe pela posição no array
    raw_veto        partida × passo do veto (pode não haver nenhum: pegadinha 14)
    raw_round       mapa × round, com a economia dos dois times quando veio `tabs=all`
    raw_player_map  mapa × jogador, com agente e stats

Nada de regra de negócio aqui: só achatar, forçar tipos e resolver tag → id pela ponte por placar
(`ingestion/bridge.py`). As colunas `team1_*`/`team2_*` seguem sempre a ordem de `teams[]` da
partida. Se a ponte não fecha num mapa, os ids daquele mapa ficam nulos e `bridge_ok = false`:
o staging descarta e conta, em vez de atribuir rounds ao time errado.

Mapa sem histórico de lado (pegadinha 22) entra com `has_round_sides = false`: placar, vencedor
de cada round, jogadores e agentes valem; lado e método ficam nulos.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ingestion.bridge import BridgeError, tag_to_team_id, team_id_by_name
from ingestion.schemas import Map, MatchDetail

log = logging.getLogger(__name__)

STATS = (
    "rating",
    "acs",
    "kills",
    "deaths",
    "assists",
    "kast",
    "adr",
    "hs",
    "first_bloods",
    "first_deaths",
)


def flatten_match(
    detail: MatchDetail, *, has_tabs: bool, collected_at: datetime
) -> dict[str, list[dict]]:
    team1, team2 = detail.teams
    match_id = detail.id

    rows: dict[str, list[dict]] = {
        "raw_match": [
            {
                "match_id": match_id,
                "event_id": detail.event.id,
                "event_series": detail.event.series,
                "status": detail.status,
                "format": detail.format,
                "match_ts": detail.timestamp,
                "team1_id": team1.id,
                "team1_name": team1.name,
                "team1_score": team1.score,
                "team2_id": team2.id,
                "team2_name": team2.name,
                "team2_score": team2.score,
                "n_maps": len(detail.maps),
                "n_maps_without_data": detail.maps_without_data,
                "has_tabs": has_tabs,
                "collected_at": collected_at,
            }
        ],
        "raw_map": [],
        "raw_veto": [],
        "raw_round": [],
        "raw_player_map": [],
    }

    tag_ids: dict[str, str] = {}
    for order, map_ in enumerate(detail.maps, start=1):
        try:
            bridge = tag_to_team_id(detail, map_)
        except BridgeError as exc:
            log.warning("partida %s: %s", match_id, exc)
            bridge = {}
        tag_ids.update(bridge)

        # Time do mapa → time da partida pelo nome em qualquer forma (pegadinha 35).
        sides = {team_id_by_name(detail, t.name): t for t in map_.teams}
        a, b = sides.get(team1.id), sides.get(team2.id)
        rows["raw_map"].append(
            {
                "map_id": map_.id,
                "match_id": match_id,
                "map_order": order,
                "map_name": map_.name,
                "status": map_.status,
                "picked_by_name": map_.picked_by,
                "picked_by_team_id": team_id_by_name(detail, map_.picked_by),
                "duration_s": map_.duration_seconds,
                "team1_id": team1.id,
                **_map_team("team1", a),
                "team2_id": team2.id,
                **_map_team("team2", b),
                "bridge_ok": bool(bridge) and a is not None and b is not None,
                "has_round_sides": map_.has_sides,
                "has_complete_stats": not map_.stats_incomplete,
            }
        )

        economy = _economy_by_round(map_, bridge, detail, team1.id, team2.id)
        for rnd in map_.rounds:
            rows["raw_round"].append(
                {
                    "match_id": match_id,
                    "map_id": map_.id,
                    "round_number": rnd.number,
                    "winner_tag": rnd.winner,
                    "winner_team_id": bridge.get(rnd.winner),
                    "winner_side": rnd.side,
                    "method": rnd.method,
                    **economy.get(rnd.number, {}),
                }
            )

        for player in map_.players:
            if len(player.agents) > 1:
                log.warning(
                    "partida %s, mapa %s: %s com vários agentes", match_id, map_.id, player.id
                )
            stats = player.stats
            rows["raw_player_map"].append(
                {
                    "match_id": match_id,
                    "map_id": map_.id,
                    "player_id": player.id,
                    "player_name": player.name,
                    "team_tag": player.team_tag,
                    "team_id": bridge.get(player.team_tag),
                    "agent": player.agents[0].name,
                    **{name: getattr(stats, name) for name in STATS},
                }
            )

    for step, veto in enumerate(detail.picks_bans.steps, start=1):
        rows["raw_veto"].append(
            {
                "match_id": match_id,
                "step": step,
                "action": veto.action,
                "map_name": veto.map,
                "team_tag": veto.team,
                "team_id": tag_ids.get(veto.team) if veto.team else None,
            }
        )
    return rows


def _map_team(prefix: str, team) -> dict:
    if team is None:
        return {}
    return {
        f"{prefix}_score": team.score,
        f"{prefix}_rounds_ct": team.rounds_ct,
        f"{prefix}_rounds_t": team.rounds_t,
    }


def _economy_by_round(
    map_: Map, bridge: dict[str, str], detail: MatchDetail, team1_id: str, team2_id: str
):
    """Economia por número de round, nas colunas `team1_*`/`team2_*`, alinhada por tag → id.

    O rótulo de `economy.teams` é a tag ou, quando a tag não é toda maiúscula, o nome do time
    (pegadinha 29): casa pela ponte e, se não for tag, pelo nome da partida.
    """
    if map_.economy is None or not bridge:
        return {}
    slots = {team1_id: "team1", team2_id: "team2"}

    def team_id(label: str) -> str | None:
        return bridge.get(label.strip().upper()) or team_id_by_name(detail, label)

    prefixes = [slots.get(team_id(t.name)) for t in map_.economy.teams]
    if set(prefixes) != {"team1", "team2"}:
        log.warning("mapa %s: economia não casa com a ponte (%s)", map_.id, prefixes)
        return {}
    return {
        rnd.number: {
            f"{prefix}_{field}": getattr(team, field)
            for prefix, team in zip(prefixes, rnd.teams, strict=True)
            for field in ("bank", "loadout", "buy")
        }
        for rnd in map_.economy.rounds
    }
