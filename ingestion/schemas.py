"""Contrato da API vlresports — só os campos que o projeto consome.

Regra: `extra="ignore"`. Campo novo na API não quebra nada; campo consumido que some ou muda de
tipo quebra a validação. Os coletores (D5/D6) validam toda resposta por estes modelos antes de
gravar no lake, e os testes de contrato (D3) os validam contra os fixtures reais.

Pegadinhas tratadas aqui (numeração de `docs/fontes.md`):
    6  — `rating` pode vir inteiro; nomes de agente com caixa inconsistente; `duration` mistura
         `h:mm:ss` e `mm:ss`; `prizepool` é string.
    10 — `economy` e `performance` só existem com `tabs`; são opcionais.
    14 — mapa não jogado some de `maps[]`, mas continua no veto.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class _Contract(BaseModel):
    """Base: ignora campos extras e lê as chaves camelCase da API em atributos snake_case."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


class Response[T](_Contract):
    """Envelope de toda resposta: `{"status": "OK", "data": ...}`."""

    status: Literal["OK"]
    data: T


# --- agentes ---------------------------------------------------------------------------------


class Agent(_Contract):
    """Agente. O nome vem capitalizado em `players` e minúsculo nos demais lugares."""

    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


# --- detalhe de partida: /matches/{id} -------------------------------------------------------


class EventRef(_Contract):
    id: str
    name: str
    series: str


class MatchTeam(_Contract):
    """Time no topo da partida: a única fonte de `id` de time."""

    id: str
    name: str
    score: int


class VetoStep(_Contract):
    """Passo do veto. `team` é a tag e vem nulo no `remains`."""

    team: str | None = None
    action: Literal["ban", "pick", "remains"]
    map: str


class PicksBans(_Contract):
    """Veto. Pode vir vazio: a 707490 (Challengers Brasil) não tem veto no vlr.gg."""

    steps: list[VetoStep] = Field(alias="list")


class MapTeam(_Contract):
    """Time dentro do mapa, identificado só pelo nome.

    `rounds_ct` e `rounds_t` contam apenas o tempo regulamentar (rounds 1–24); `score` inclui o
    overtime. Confirmado no D3 com a 734308 (Ascent e Haven) e a 707490 (Lotus).
    """

    name: str
    score: int
    rounds_ct: int
    rounds_t: int


class Round(_Contract):
    """Round. `winner` é a tag; `side` é o lado de quem venceu (pegadinha 1)."""

    number: int = Field(ge=1)
    winner: str
    side: Literal["ct", "t"]
    method: Literal["elim", "defuse", "boom", "time"]


class PlayerStats(_Contract):
    """Stats por mapa. Todos opcionais: as análises não dependem deles."""

    rating: float | None = None
    acs: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    kast: int | None = None
    adr: int | None = None
    hs: int | None = None
    first_bloods: int | None = None
    first_deaths: int | None = None


class PlayerMap(_Contract):
    id: str
    name: str
    team_tag: str
    agents: list[Agent] = Field(min_length=1)
    stats: PlayerStats


class EconomyTeam(_Contract):
    """`name` é a tag. A ordem espelha `teams[]` da partida (ponte posicional)."""

    name: str
    pistol_won: int


class EconomyRoundTeam(_Contract):
    bank: int
    loadout: int
    buy: Literal["eco", "semi-eco", "semi-buy", "full-buy"]
    winner: bool


class EconomyRound(_Contract):
    number: int = Field(ge=1)
    teams: list[EconomyRoundTeam] = Field(min_length=2, max_length=2)


class Economy(_Contract):
    teams: list[EconomyTeam] = Field(min_length=2, max_length=2)
    rounds: list[EconomyRound]


_DURATION = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


class Map(_Contract):
    id: str
    name: str
    status: str
    picked_by: str | None = None
    duration: str | None = None
    teams: list[MapTeam] = Field(min_length=2, max_length=2)
    rounds: list[Round]
    players: list[PlayerMap]
    economy: Economy | None = None
    performance: dict[str, Any] | None = None

    @field_validator("duration")
    @classmethod
    def _duration_format(cls, v: str | None) -> str | None:
        if v is not None and not _DURATION.match(v):
            raise ValueError(f"duração fora de `h:mm:ss` ou `mm:ss`: {v!r}")
        return v

    @property
    def duration_seconds(self) -> int | None:
        if self.duration is None:
            return None
        h, m, s = _DURATION.match(self.duration).groups()
        return int(h or 0) * 3600 + int(m) * 60 + int(s)


class MatchDetail(_Contract):
    id: str
    event: EventRef
    status: str
    format: str
    timestamp: datetime
    utc_date: str
    teams: list[MatchTeam] = Field(min_length=2, max_length=2)
    picks_bans: PicksBans
    maps: list[Map]


# --- eventos: /events, /events/{id}/matches, /events/{id}/agents -----------------------------


class EventSummary(_Contract):
    """Evento na listagem `/events`. Sem ano nem região (pegadinhas 9 e 16)."""

    id: str
    name: str
    status: Literal["upcoming", "ongoing", "completed"]
    prizepool: str
    country: str | None = None


class EventMatchTeam(_Contract):
    """Time na lista de partidas do evento: sem id (pegadinha 16). `score` é nulo em partida
    `upcoming` (Champions 2026, fixture `event_matches_ongoing_champions_2026.json`)."""

    name: str
    score: int | None
    winner: bool


class EventMatch(_Contract):
    """Partida na listagem do evento. `date` vem sem fuso ("Thu, July 16, 2026"): serve para
    ordenar a coleta e decidir as abas, nunca como data da partida (essa vem do detalhe)."""

    id: str
    status: str
    date: str | None = None
    teams: list[EventMatchTeam] = Field(min_length=2, max_length=2)

    @property
    def listed_on(self) -> date | None:
        try:
            return datetime.strptime(self.date or "", "%a, %B %d, %Y").date()
        except ValueError:
            return None


class EventAgent(Agent):
    pick_rate: float


class EventAgentsMap(_Contract):
    """Agregado do vlr.gg por mapa. A linha `map == "All"` soma o evento inteiro."""

    map: str
    played: int
    atk_win_rate: float
    def_win_rate: float
    agents: list[EventAgent]
