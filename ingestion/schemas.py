"""Contrato da API vlresports — só os campos que o projeto consome.

Regra: `extra="ignore"`. Campo novo na API não quebra nada; campo consumido que some ou muda de
tipo quebra a validação. Os coletores (D5/D6) validam toda resposta por estes modelos antes de
gravar no lake, e os testes de contrato (D3) os validam contra os fixtures reais.

Pegadinhas tratadas aqui (numeração de `docs/fontes.md`):
    6  — `rating` pode vir inteiro; nomes de agente com caixa inconsistente; `duration` mistura
         `h:mm:ss` e `mm:ss`; `prizepool` é string.
    10 — `economy` e `performance` só existem com `tabs`; são opcionais.
    14 — mapa não jogado some de `maps[]`, mas continua no veto.
    19 — partida `upcoming` na listagem do evento vem com `score: null`.
    22 — mapa sem histórico de lado: `side`, `method`, `roundsCt` e `roundsT` nulos, tudo ou nada.
    23 — `loadout` nulo em rounds soltos da economia.
    24 — time sem página no vlr.gg ("TBD", id nulo): a partida é rejeitada, de propósito.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel


class _Contract(BaseModel):
    """Base: ignora campos extras e lê as chaves camelCase da API em atributos snake_case."""

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )


def _canonical_tag(v: str) -> str:
    return v.strip().upper()


# Tag de time em caixa alta (pegadinha 29): `rounds[].winner` vem "ARAS", `players[].teamTag` vem
# "Aras" para o mesmo time. Sem a forma canônica, a ponte tag → id não fecha.
Tag = Annotated[str, AfterValidator(_canonical_tag)]


class Response[T](_Contract):
    """Envelope de toda resposta: `{"status": "OK", "data": ...}`."""

    status: Literal["OK"]
    data: T


# --- agentes ---------------------------------------------------------------------------------


class Agent(_Contract):
    """Agente. O nome vem capitalizado em `players` e minúsculo nos demais lugares.

    `img` é o ícone do agente no vlr.gg (`/img/vlr/game/agents/{nome}.png`); opcional, porque nem
    todo endpoint o traz.
    """

    name: str = Field(min_length=1)
    img: str | None = None

    @field_validator("name")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("img", mode="before")
    @classmethod
    def _icon(cls, v: Any) -> str | None:
        if not v:
            return None
        return f"https:{v}" if v.startswith("//") else v


# --- detalhe de partida: /matches/{id} -------------------------------------------------------


class EventRef(_Contract):
    id: str
    name: str
    series: str


# Time sem logo no vlr.gg vem com a imagem genérica do site (pegadinha 42): vira "sem logo".
_PLACEHOLDER_LOGO = "/img/vlr/tmp/"


class MatchTeam(_Contract):
    """Time no topo da partida: a única fonte de `id` de time.

    `img` é o logo (CDN do vlr.gg). Opcional: o placeholder genérico do vlr.gg vira `None`, e URL
    sem protocolo (`//owcdn.net/...`) ganha `https:`.
    """

    id: str
    name: str
    score: int
    img: str | None = None

    @field_validator("img", mode="before")
    @classmethod
    def _logo(cls, v: Any) -> str | None:
        if not v or _PLACEHOLDER_LOGO in v:
            return None
        return f"https:{v}" if v.startswith("//") else v


_VETO_STEP = re.compile(r"^(?P<team>\S+)\s+(?P<action>ban|pick)\s+(?P<map>.+)$")
_VETO_REMAINS = re.compile(r"^(?P<map>.+?)\s+remains$")


def _note_step(text: str) -> dict | None:
    """Passo de veto na última linha de uma nota grudada (pegadinha 30), ou `None`."""
    lines = text.strip().splitlines()
    line = lines[-1].strip() if lines else ""
    if m := _VETO_REMAINS.match(line):
        return {"team": None, "action": "remains", "map": m["map"]}
    if m := _VETO_STEP.match(line):
        return {"team": m["team"], "action": m["action"], "map": m["map"]}
    return None


class VetoStep(_Contract):
    """Passo do veto. `team` é a tag e vem nulo no `remains`."""

    team: Tag | None = None
    action: Literal["ban", "pick", "remains"]
    map: str

    @model_validator(mode="before")
    @classmethod
    def _note_glued_to_first_step(cls, data: Any) -> Any:
        """Nota editorial do vlr.gg grudada no 1º passo (pegadinha 30, partida 698906).

        O parser devolve `action: "note"` e, em `map`, a nota seguida do passo real na última
        linha ("...lobby remake." e, embaixo, "T1 ban Split"). O passo só é recuperado se a
        última linha tiver o formato de um passo; senão o `action` desconhecido é recusado.
        """
        if not isinstance(data, dict) or data.get("action") != "note":
            return data
        step = _note_step(str(data.get("map") or ""))
        return {**data, **step} if step else data


class PicksBans(_Contract):
    """Veto. Pode vir vazio: a 707490 (Challengers Brasil) não tem veto no vlr.gg."""

    steps: list[VetoStep] = Field(alias="list")

    @model_validator(mode="before")
    @classmethod
    def _note_alone_is_no_veto(cls, data: Any) -> Any:
        """Partida sem veto e com nota editorial (pegadinha 30, 678049 e 678062): a lista traz só a
        nota, sem passo nenhum. É veto vazio. Nota sem passo ao lado de outros passos continua
        recusada no `VetoStep`: ali um passo se perdeu."""
        if not isinstance(data, dict):
            return data
        steps = data.get("list")
        if (
            isinstance(steps, list)
            and len(steps) == 1
            and isinstance(steps[0], dict)
            and steps[0].get("action") == "note"
            and not _note_step(str(steps[0].get("map") or ""))
        ):
            return {**data, "list": []}
        return data


class MapTeam(_Contract):
    """Time dentro do mapa, identificado só pelo nome.

    `rounds_ct` e `rounds_t` contam apenas o tempo regulamentar (rounds 1–24); `score` inclui o
    overtime. Confirmado no D3 com a 734308 (Ascent e Haven) e a 707490 (Lotus). Nulos quando o
    mapa não tem histórico de lado (pegadinha 22; regra tudo-ou-nada em `Map`).
    """

    name: str
    score: int
    rounds_ct: int | None
    rounds_t: int | None


class Round(_Contract):
    """Round. `winner` é a tag; `side` é o lado de quem venceu (pegadinha 1).

    `side` e `method` são nulos quando o vlr.gg não tem a linha do tempo do mapa (pegadinha 22,
    partida 681934): o vencedor de cada round continua vindo.
    """

    number: int = Field(ge=1)
    winner: Tag
    side: Literal["ct", "t"] | None
    method: Literal["elim", "defuse", "boom", "time"] | None


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
    """Jogador num mapa. Exatamente um agente: dois agentes na mesma linha é o 5º jogador do time,
    sem página no vlr.gg, colado pelo parser no jogador anterior (pegadinha 37)."""

    id: str
    name: str
    team_tag: Tag
    agents: list[Agent] = Field(min_length=1, max_length=1)
    stats: PlayerStats


class EconomyTeam(_Contract):
    """`name` é a tag, ou o nome do time quando a tag não é toda maiúscula (pegadinha 29:
    "Catboys" com tag "Catb"). Não é normalizado: o `flatten` casa pela tag ou pelo nome."""

    name: str
    pistol_won: int


class EconomyRoundTeam(_Contract):
    """`loadout` pode vir nulo em rounds soltos, com `bank` e `buy` preenchidos (pegadinha 23:
    partidas 668479, 681918 e 681920 do Challengers Brasil)."""

    bank: int
    loadout: int | None
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
    # Marcado pelo `MatchDetail` a partir da nota do veto (pegadinha 36); não vem da API.
    stats_incomplete: bool = False

    @field_validator("duration")
    @classmethod
    def _duration_format(cls, v: str | None) -> str | None:
        if v is not None and not _DURATION.match(v):
            raise ValueError(f"duração fora de `h:mm:ss` ou `mm:ss`: {v!r}")
        return v

    @model_validator(mode="before")
    @classmethod
    def _team_without_tag(cls, data: Any) -> Any:
        """Time sem tag no vlr.gg (pegadinha 40, Korea WDG 2830): os jogadores dele vêm com
        `teamTag` vazio e os rounds que ele venceu, com `winner` nulo. O nulo vira a mesma tag
        vazia; a ponte por placar (`bridge.py`) confere a contagem contra o placar do mapa."""
        if not isinstance(data, dict):
            return data
        players = [p for p in data.get("players") or [] if isinstance(p, dict)]
        if not any(p.get("teamTag") == "" for p in players):
            return data
        rounds = [
            {**r, "winner": ""} if isinstance(r, dict) and r.get("winner") is None else r
            for r in data.get("rounds") or []
        ]
        return {**data, "rounds": rounds}

    @field_validator("economy", "performance", mode="before")
    @classmethod
    def _empty_tab_is_absent(cls, v: Any) -> Any:
        """Aba pedida sem dado no vlr.gg (pegadinha 27): toda lista vazia equivale à aba ausente.

        Só o vazio total: economia com rounds e sem times continua sendo recusada.
        """
        if isinstance(v, dict) and v and all(x == [] for x in v.values()):
            return None
        return v

    @model_validator(mode="after")
    def _sides_all_or_nothing(self) -> Map:
        """Mapa sem histórico de lado é caso da fonte (pegadinha 22); lado pela metade é defeito.

        O lado (`side` de todo round e os contadores `roundsCt`/`roundsT`) é tudo ou nada: é dele
        que sai atacante e defensor de cada round. O método de vitória pode faltar em qualquer
        round (pegadinha 31: todo o mapa na 748625, rounds soltos na 433835 e na 450075); só entra
        nas contagens de método, que ignoram o nulo.
        """
        fields = (
            [r.side for r in self.rounds]
            + [t.rounds_ct for t in self.teams]
            + [t.rounds_t for t in self.teams]
        )
        filled = sum(v is not None for v in fields)
        if filled not in (0, len(fields)):
            raise ValueError(f"mapa {self.id}: lado preenchido em {filled} de {len(fields)} campos")
        return self

    @property
    def has_sides(self) -> bool:
        return all(t.rounds_ct is not None for t in self.teams)

    @property
    def duration_seconds(self) -> int | None:
        if self.duration is None:
            return None
        h, m, s = _DURATION.match(self.duration).groups()
        return int(h or 0) * 3600 + int(m) * 60 + int(s)


_INCOMPLETE_MAP = re.compile(
    r"Map (\d+) stats (?:are )?(?:incomplete|partially unavailable|unavailable)", re.IGNORECASE
)


def _series_order(steps: list) -> list[str]:
    """Mapas na ordem da série: os picks do veto, na ordem, e o decider por último."""
    parsed = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("action") == "note":  # nota grudada no 1º passo (pegadinha 30)
            step = _note_step(str(step.get("map") or "")) or {}
        parsed.append(step)
    picks = [s.get("map") for s in parsed if s.get("action") == "pick"]
    return picks + [s.get("map") for s in parsed if s.get("action") == "remains"]


def _is_empty_map(m: Any) -> bool:
    return (
        isinstance(m, dict)
        and m.get("rounds") == []
        and bool(m.get("players"))
        and all(isinstance(p, dict) and p.get("agents") == [] for p in m["players"])
    )


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
    # Mapas descartados por não ter dado nenhum (pegadinha 33); não vem da API.
    maps_without_data: int = 0

    @model_validator(mode="before")
    @classmethod
    def _mark_incomplete_and_drop_empty_maps(cls, data: Any) -> Any:
        """Casos da fonte nos mapas, tratados sobre a lista original, antes de qualquer descarte:

        * mapa refeito por lobby remake (pegadinha 36): a nota do veto diz "Map N stats are
          incomplete", "are unavailable", "unavailable" ou "are partially unavailable". N é a
          ordem da série (picks do veto, na ordem, e o decider por último), não a posição em
          `maps[]`: a API pode pôr o mapa refeito no fim (459856, 482510). Sem veto, vale a
          posição. O mapa entra marcado com `stats_incomplete`;
        * mapa com placar e jogadores, mas nenhum round: estatística indisponível, também
          `stats_incomplete` (o gabarito do vlr.gg o deixa fora: 2380, 2787, 2801);
        * mapa sem nenhum dado (pegadinha 33): nenhum round e nenhum jogador com agente; é
          descartado e contado em `maps_without_data`. Costuma ser o mapa perdido por W.O. no
          meio da série ("TBD", placar nulo), que o placar da série conta.
        """
        if not isinstance(data, dict) or not isinstance(data.get("maps"), list):
            return data
        picks_bans = data.get("picksBans") or {}
        numbers = {int(n) for n in _INCOMPLETE_MAP.findall(str(picks_bans.get("note") or ""))}
        order = _series_order(picks_bans.get("list") or [])
        raw_maps = data["maps"]
        names = [m.get("name") if isinstance(m, dict) else None for m in raw_maps]
        remade = set()
        for n in numbers:
            name = order[n - 1] if 0 < n <= len(order) else None
            if name in names:
                remade.add(names.index(name))
            elif 0 < n <= len(raw_maps):
                remade.add(n - 1)
        maps = [
            (
                {
                    **m,
                    "statsIncomplete": i in remade
                    or (m.get("rounds") == [] and not _is_empty_map(m)),
                }
                if isinstance(m, dict)
                else m
            )
            for i, m in enumerate(raw_maps)
        ]
        kept = [m for m in maps if not _is_empty_map(m)]
        return {**data, "maps": kept, "mapsWithoutData": len(maps) - len(kept)}


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


# --- defeitos conhecidos da fonte -------------------------------------------------------------


def known_source_defect(body: dict) -> str | None:
    """Defeito conhecido do vlr.gg que impede a partida de entrar, ou `None`.

    O contrato também recusa esses casos; o coletor pergunta antes, para separá-los de formato
    novo: são rejeições definitivas que não contam para o aborto de rejeições seguidas (um time
    sem página numa chave inteira derrubaria a coleta toda vez).
    """

    def null_id(node: Any) -> bool:
        # Chave presente com valor nulo: o caso conhecido. Chave ausente é formato novo, e fica
        # para o contrato (que conta para o aborto).
        return isinstance(node, dict) and "id" in node and node["id"] is None

    data = body.get("data") or {}
    if null_id(data.get("event")):
        return "evento sem id: link do evento quebrado (pegadinha 28)"
    if any(null_id(t) for t in data.get("teams") or []):
        return 'time sem página no vlr.gg, "TBD" (pegadinha 24)'
    for m in data.get("maps") or []:
        players = [p for p in m.get("players") or [] if isinstance(p, dict)]
        if any(isinstance(p.get("agents"), list) and len(p["agents"]) > 1 for p in players):
            return f"mapa {m.get('id')}: jogador sem página fundido em outro (pegadinha 37)"
        if any(null_id(p) and p.get("agents") for p in players):
            return f"mapa {m.get('id')}: jogador sem id, substituição no mapa (pegadinha 32)"
    return None
