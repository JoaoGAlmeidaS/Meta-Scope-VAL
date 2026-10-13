"""Coletores: JSON da API → contrato (`schemas.py`) → tabelas raw → Parquet no lake (`lake.py`).

    D5 — eventos (`/events`, tier vct e vcl) com tier, região e temporada; listagem de partidas
         (`/events/{id}/matches`) e gabarito `/events/{id}/agents`
    D6 — detalhe de partida (`/matches/{id}`) nas cinco tabelas raw (`flatten.py`)
    D7 — backfill do mais recente para o mais antigo, retomável pelo cache do cliente

Jogadores e times saem do detalhe de partida, nunca das listagens `/players` e `/teams`.
A coleta não filtra por override: tudo que `tier=vct|vcl` devolve entra; exclusões e
reclassificações são do seed `event_overrides.csv`, aplicado no dbt.

Partição: temporada (`season=YYYY`, chave Hive), um arquivo por evento.

CLI:
    python -m ingestion.collectors events                  índice, listagens e gabarito
    python -m ingestion.collectors backfill                tudo desde 2025, mais recente primeiro
    python -m ingestion.collectors backfill --event 2977   um evento só
    python -m ingestion.collectors backfill --season 2026  uma temporada (partição do Dagster)
    python -m ingestion.collectors incremental             só a temporada corrente
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import ValidationError

from ingestion import lake
from ingestion.client import ApiClient, ApiError, NotFound, TransientError
from ingestion.config import HISTORY_SINCE, tabs_cutoff
from ingestion.flatten import flatten_match
from ingestion.schemas import (
    EventAgentsMap,
    EventMatch,
    EventSummary,
    MatchDetail,
    Response,
    known_source_defect,
)

log = logging.getLogger(__name__)

PARTITION_KEY = "season"

TIERS = ("vct", "vcl")
REGIONS = ("americas", "emea", "pacific", "china")
INTERNATIONAL = "international"

LISTING_MAX_AGE_S = 24 * 3600  # índice de eventos
ONGOING_MAX_AGE_S = 6 * 3600  # listagem e gabarito de evento em andamento
MAX_PAGES = 50
OLDER_PAGES_TO_STOP = 2  # páginas seguidas só com temporadas anteriores a `since`
MAX_CONSECUTIVE_REJECTS = 5
MAX_CONSECUTIVE_UNAVAILABLE = 3  # listagens de evento seguidas sem resposta: instância fora do ar
SECONDS_PER_MATCH = 6.0  # medido no D2: ~1h40 por mil partidas

_SEASON_FULL = re.compile(r"\b(20[2-9]\d)\b")
_SEASON_SHORT = re.compile(r"\b(?:VCT|VCL)\s?(\d{2})\b")


class CollectionAborted(RuntimeError):
    """Falhas seguidas demais: mudança de formato da API ou instância fora do ar, não um caso
    isolado. Rodar de novo retoma pelo cache."""


def season_from_name(name: str) -> int | None:
    """Temporada pelo nome: "VCT 2026: ...", "VCL 26: ...", "Champions Tour 2024: ..."."""
    if m := _SEASON_FULL.search(name):
        return int(m.group(1))
    if m := _SEASON_SHORT.search(name):
        return 2000 + int(m.group(1))
    return None


# --- D5: eventos -----------------------------------------------------------------------------


@dataclass
class Event:
    id: str
    name: str
    status: str
    country: str | None
    prizepool: str
    tiers: set[str] = field(default_factory=set)
    regions: set[str] = field(default_factory=set)
    matches: list[EventMatch] = field(default_factory=list)

    @property
    def tier(self) -> str:
        return "vct" if "vct" in self.tiers else "vcl"

    @property
    def tier_ambiguous(self) -> bool:
        """Aparece em `tier=vct` e `tier=vcl` (pegadinha 15). Resolvido pelo seed de overrides."""
        return len(self.tiers) > 1

    @property
    def region(self) -> str | None:
        """Evento doméstico aparece numa região do filtro `region`; internacional, em várias."""
        if len(self.regions) > 1:
            return INTERNATIONAL
        return next(iter(self.regions), None)

    @property
    def listed_dates(self) -> list[date]:
        return [d for m in self.matches if (d := m.listed_on) is not None]

    @property
    def season(self) -> int | None:
        """Ano do nome; sem ano no nome, o ano da primeira partida listada."""
        by_name = season_from_name(self.name)
        if by_name is not None:
            return by_name
        dates = self.listed_dates
        return min(dates).year if dates else None

    @property
    def last_listed_on(self) -> date | None:
        return max(self.listed_dates, default=None)

    @property
    def completed_matches(self) -> list[EventMatch]:
        return [m for m in self.matches if m.status == "completed"]

    def row(self, collected_at: datetime) -> dict:
        return {
            "event_id": self.id,
            "name": self.name,
            "status": self.status,
            "tier": self.tier,
            "tier_ambiguous": self.tier_ambiguous,
            "region": self.region,
            "season": self.season,
            "country": self.country,
            "prizepool": self.prizepool,
            "first_listed_on": min(self.listed_dates, default=None),
            "last_listed_on": self.last_listed_on,
            "collected_at": collected_at,
        }


def _event_pages(client: ApiClient, tier: str, region: str | None, since: int):
    """Pagina `/events` até `data` vazio (pegadinha 9) ou até passar de `since` com folga."""
    older = 0
    for page in range(1, MAX_PAGES + 1):
        params = {"tier": tier, "page": page} | ({"region": region} if region else {})
        body = client.fetch("/events", params, max_age_s=LISTING_MAX_AGE_S)
        rows = Response[list[EventSummary]].model_validate(body).data
        if not rows:
            return
        yield from rows
        seasons = [s for r in rows if (s := season_from_name(r.name)) is not None]
        older = older + 1 if seasons and max(seasons) < since else 0
        if older >= OLDER_PAGES_TO_STOP:
            return


def is_china_tier2(event: Event) -> bool:
    """Tier 2 chinês: fica fora da coleta (decisão de 05/10).

    Disputado em plataformas de terceiros, chega com dados faltando (pegadinhas 27, 31 e 33) e vale
    pouco para a análise além do volume. Pega a VCL China (aparece em `tier=vcl` com `region=china`,
    inclusive o China Evolution Series 2026, que aparece nos dois tiers) e o China Evolution Series
    pelo nome (o de 2025 só aparece em `tier=vct`). O VCT China (Kickoff e Stages) é tier 1 e fica.
    """
    return ("vcl" in event.tiers and "china" in event.regions) or (
        "china evolution series" in event.name.casefold()
    )


def list_events(client: ApiClient, *, since: int) -> list[Event]:
    """Eventos VCT e VCL, deduplicados por id, com as regiões em que aparecem.

    Cada tier é listado por região e sem filtro: o evento que só aparece sem filtro fica com
    região nula (override no seed). Eventos futuros, de temporadas anteriores e o tier 2 chinês
    (`is_china_tier2`) ficam de fora.
    """
    events: dict[str, Event] = {}
    for tier in TIERS:
        for region in (*REGIONS, None):
            for s in _event_pages(client, tier, region, since):
                event = events.setdefault(
                    s.id, Event(s.id, s.name, s.status, s.country, s.prizepool)
                )
                event.tiers.add(tier)
                if region:
                    event.regions.add(region)
    china = [e.id for e in events.values() if is_china_tier2(e)]
    if china:
        log.info("%d eventos do tier 2 chinês fora da coleta", len(china))
    return [
        e
        for e in events.values()
        if e.status != "upcoming"
        and (season_from_name(e.name) or since) >= since
        and not is_china_tier2(e)
    ]


def _max_age(event: Event) -> float | None:
    return None if event.status == "completed" else ONGOING_MAX_AGE_S


def attach_matches(client: ApiClient, event: Event) -> None:
    body = client.fetch(f"/events/{event.id}/matches", max_age_s=_max_age(event))
    event.matches = Response[list[EventMatch]].model_validate(body).data


def event_agents(client: ApiClient, event: Event) -> list[EventAgentsMap] | None:
    """Gabarito do D13. É opcional: nenhuma falha aqui para a coleta.

    `[]` quando o vlr.gg não tem o agregado (erro definitivo): grava arquivo vazio e não insiste.
    `None` quando a falha pode passar (502 persistente, contrato): não grava, e a próxima
    execução tenta de novo. Caso real: `/events/1309/agents` deu 502 em 6 tentativas no D5.
    """
    try:
        body = client.fetch(f"/events/{event.id}/agents", max_age_s=_max_age(event))
        return Response[list[EventAgentsMap]].model_validate(body).data
    except ApiError as exc:
        log.error("evento %s sem gabarito: %s", event.id, str(exc)[:200])
        return []
    except (TransientError, ValidationError) as exc:
        log.error("gabarito do evento %s indisponível agora: %s", event.id, str(exc)[:200])
        return None


def _event_match_rows(event: Event) -> list[dict]:
    return [
        {
            "event_id": event.id,
            "match_id": m.id,
            "status": m.status,
            "listed_on": m.listed_on,
            **{
                f"team{i}_{k}": getattr(t, k)
                for i, t in enumerate(m.teams, start=1)
                for k in ("name", "score", "winner")
            },
        }
        for m in event.matches
    ]


def _event_agent_rows(event: Event, maps: list[EventAgentsMap]) -> list[dict]:
    return [
        {
            "event_id": event.id,
            "map_name": row.map,
            "played": row.played,
            "atk_win_rate": row.atk_win_rate,
            "def_win_rate": row.def_win_rate,
            "agent": agent.name,
            "pick_rate": agent.pick_rate,
        }
        for row in maps
        for agent in row.agents
    ]


def collect_events(
    client: ApiClient,
    *,
    since: int,
    root: Path,
    only_event: str | None = None,
    only_season: int | None = None,
) -> list[Event]:
    """D5: índice de eventos + listagem de partidas + gabarito, gravados no lake.

    Um evento com problema fica fora, com o motivo no log, e a coleta segue. Listagens seguidas
    sem resposta abortam (instância fora do ar). O índice `raw_event` é gravado mesmo quando a
    coleta cai no meio, com os eventos vistos até ali.

    `only_event` e `only_season` recortam antes de buscar as listagens: validar um evento ou
    materializar uma partição do Dagster não custa as listagens de todos os outros eventos.
    """
    collected_at = datetime.now(UTC)
    events: list[Event] = []
    candidates = [
        e
        for e in list_events(client, since=since)
        if (only_event is None or e.id == only_event)
        and (only_season is None or season_from_name(e.name) in (None, only_season))
    ]
    log.info("%d eventos candidatos desde %d", len(candidates), since)
    unavailable = 0
    try:
        for event in candidates:
            try:
                attach_matches(client, event)
            except (ApiError, ValidationError) as exc:
                log.error("listagem do evento %s ignorada: %s", event.id, str(exc)[:300])
                continue
            except TransientError as exc:
                unavailable += 1
                log.error("listagem do evento %s indisponível agora: %s", event.id, exc)
                if unavailable >= MAX_CONSECUTIVE_UNAVAILABLE:
                    raise CollectionAborted(
                        f"{unavailable} listagens seguidas sem resposta; instância fora do ar?"
                    ) from exc
                continue
            unavailable = 0
            if event.season is None or event.season < since:
                log.info("evento %s (%s) fora da temporada; ignorado", event.id, event.name)
                continue
            if only_season is not None and event.season != only_season:
                continue
            lake.write_table(
                root,
                "raw_event_match",
                _event_match_rows(event),
                season=event.season,
                event_id=event.id,
            )
            agents = event_agents(client, event)
            if agents is not None:
                lake.write_table(
                    root,
                    "raw_event_agents",
                    _event_agent_rows(event, agents),
                    season=event.season,
                    event_id=event.id,
                )
            events.append(event)
    finally:
        # Upsert por id: a carga incremental (ou uma coleta interrompida) reescreve só o que viu.
        existing = {r["event_id"]: r for r in lake.read_table(root, "raw_event").to_pylist()}
        existing.update({e.id: e.row(collected_at) for e in events})
        lake.write_table(root, "raw_event", sorted(existing.values(), key=lambda r: r["event_id"]))
    return events


# --- D6: detalhe de partida ------------------------------------------------------------------


@dataclass
class RunStats:
    events_written: int = 0
    events_skipped: int = 0
    matches: int = 0
    rejects: Counter = field(default_factory=Counter)
    consecutive_failures: int = 0


def _fetch_detail(client: ApiClient, match: EventMatch, cutoff: date) -> tuple[bool, dict]:
    tabs = match.listed_on is None or match.listed_on >= cutoff
    body = client.fetch(f"/matches/{match.id}", {"tabs": "all"} if tabs else None)
    return tabs, body


def collect_event_details(
    client: ApiClient,
    event: Event,
    *,
    root: Path,
    cutoff: date,
    stats: RunStats,
    force: bool = False,
) -> bool:
    """D6: detalhe de cada partida concluída do evento → cinco tabelas raw + JSON bruto.

    O evento só é gravado inteiro, no fim: se a coleta cai no meio, nada fica pela metade, e a
    próxima execução retoma pelo cache. Devolve `False` se o evento já estava completo no lake.
    """
    listed = event.completed_matches
    if not force and event.status == "completed":
        done = lake.collected_match_ids(root, event.season, event.id)
        if done is not None and {m.id for m in listed} <= done:
            stats.events_skipped += 1
            return False

    collected_at = datetime.now(UTC)
    tables: dict[str, list[dict]] = {name: [] for name in lake.DETAIL_TABLES}
    archive: list[dict] = []

    def reject(match_id: str, reason: str, error: object, *, counts: bool) -> None:
        log.warning("partida %s rejeitada (%s): %s", match_id, reason, str(error)[:300])
        tables["raw_reject"].append(
            {
                "event_id": event.id,
                "match_id": match_id,
                "reason": reason,
                "error": str(error)[:2000],
                "collected_at": collected_at,
            }
        )
        stats.rejects[reason] += 1
        if counts:
            stats.consecutive_failures += 1
            if stats.consecutive_failures >= MAX_CONSECUTIVE_REJECTS:
                raise CollectionAborted(
                    f"{stats.consecutive_failures} rejeições seguidas; a API mudou de formato? "
                    f"Última: {match_id} ({reason})"
                )

    for match in listed:
        try:
            tabs, body = _fetch_detail(client, match, cutoff)
            # Partida não finalizada (forfeit, adiada) não passa pelo contrato: os mapas vêm "TBD"
            # com placar nulo e falhariam como formato novo (pegadinha 34, 688926).
            status = (body.get("data") or {}).get("status")
            if status != "final":
                reject(match.id, "not_final", f"status {status!r}", counts=False)
                continue
            # Defeito conhecido da fonte (time "TBD", jogador fundido...): definitivo, mas não é
            # formato novo; não conta para o aborto.
            if defect := known_source_defect(body):
                reject(match.id, "source", defect, counts=False)
                continue
            detail = Response[MatchDetail].model_validate(body).data
        except ValidationError as exc:
            reject(match.id, "contract", exc, counts=True)
            continue
        except NotFound as exc:
            # Página apagada no vlr.gg (pegadinha 26): definitiva e comum em qualificatória aberta,
            # não é sinal de formato novo nem de instância fora do ar.
            reject(match.id, "not_found", exc, counts=False)
            continue
        except ApiError as exc:
            reject(match.id, "api", exc, counts=True)
            continue
        except TransientError as exc:
            # Não conta como coletada (`lake.RETRYABLE_REJECTS`): a próxima execução tenta de novo.
            reject(match.id, "unavailable", exc, counts=True)
            continue
        stats.consecutive_failures = 0

        if detail.event.id != event.id:
            log.warning(
                "partida %s listada no evento %s, detalhe diz %s",
                match.id,
                event.id,
                detail.event.id,
            )

        for name, rows in flatten_match(detail, has_tabs=tabs, collected_at=collected_at).items():
            tables[name].extend(rows)
        archive.append({"match_id": match.id, "tabs": tabs, "body": body})
        stats.matches += 1

    for name, rows in tables.items():
        lake.write_table(root, name, rows, season=event.season, event_id=event.id)
    lake.write_json_archive(root, event.season, event.id, archive)
    stats.events_written += 1
    return True


# --- D7: backfill ----------------------------------------------------------------------------


def backfill(
    client: ApiClient,
    *,
    since: int,
    root: Path,
    today: date | None = None,
    only_event: str | None = None,
    only_season: int | None = None,
    force: bool = False,
) -> RunStats:
    """Do evento mais recente para o mais antigo. Janela + aquecimento vêm com `tabs=all`."""
    today = today or datetime.now(UTC).date()
    cutoff = tabs_cutoff(today)
    events = collect_events(
        client, since=since, root=root, only_event=only_event, only_season=only_season
    )
    if only_event and not events:
        raise SystemExit(f"evento {only_event} fora do escopo (tier vct/vcl, desde {since})")
    events.sort(key=lambda e: e.last_listed_on or date.min, reverse=True)

    stats = RunStats()
    total = len(events)
    started = time.monotonic()
    log.info("backfill: %d eventos, tabs=all desde %s", total, cutoff)
    for i, event in enumerate(events, start=1):
        log.info(
            "[%d/%d] %s %s — %s, %s, %d partidas",
            i,
            total,
            event.id,
            event.name,
            event.tier,
            event.region,
            len(event.completed_matches),
        )
        collect_event_details(client, event, root=root, cutoff=cutoff, stats=stats, force=force)
        net = getattr(client, "network_requests", 0)
        log.info(
            "   %d partidas gravadas, %d eventos pulados, %d requisições, %.0f min",
            stats.matches,
            stats.events_skipped,
            net,
            (time.monotonic() - started) / 60,
        )
    log.info("fim: %s, rejeições %s", stats, dict(stats.rejects))
    return stats


def report(events: list[Event]) -> str:
    """Partidas concluídas por temporada × tier e a duração estimada da coleta dos detalhes."""
    by_key: Counter = Counter()
    n_events: Counter = Counter()
    for e in events:
        by_key[(e.season, e.tier)] += len(e.completed_matches)
        n_events[(e.season, e.tier)] += 1

    def line(label: str, n_ev: int, n: int) -> str:
        return f"{label:<12} {n_ev:7d} {n:8d} {n * SECONDS_PER_MATCH / 3600:6.1f}"

    lines = ["season tier  eventos partidas  horas"]
    for (season, tier), n in sorted(by_key.items(), reverse=True):
        lines.append(line(f"{season}   {tier}", n_events[(season, tier)], n))
    lines.append(line("total", len(events), sum(by_key.values())))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["events", "backfill", "incremental"])
    parser.add_argument("--since", type=int, default=HISTORY_SINCE, help="primeira temporada")
    parser.add_argument("--event", help="só este evento (backfill)")
    parser.add_argument("--season", type=int, help="só esta temporada (backfill)")
    parser.add_argument("--force", action="store_true", help="regrava eventos já completos")
    parser.add_argument("--lake", type=Path, default=None, help="raiz do lake (padrão: data/lake)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # uma linha por requisição é ruído
    root = args.lake or lake.default_root()
    today = datetime.now(UTC).date()
    with ApiClient() as client:
        if args.command == "events":
            print(report(collect_events(client, since=args.since, root=root)))
        elif args.command == "backfill":
            backfill(
                client,
                since=args.season or args.since,
                root=root,
                only_event=args.event,
                only_season=args.season,
                force=args.force,
            )
        else:
            backfill(client, since=today.year, root=root, only_season=today.year, force=args.force)


if __name__ == "__main__":
    main()
