"""Lake de fixtures: os JSONs reais do repositório passam pelo mesmo caminho da coleta (D14).

Trilho de CI sem segredo: `dbt build` e os testes rodam sobre dados reais, pequenos e fixos, sem
rede e sem o Hugging Face. Os fixtures entram pelo `backfill` de verdade, com um cliente offline no
lugar do HTTP — o lake de fixtures tem exatamente o formato do lake real.

Conteúdo (cada caso existe por um motivo de teste):

    2977  VCT 2026: Americas Stage 2   734308 (BO5, overtime, com abas), 734313 (BO3 2–0),
                                       734307 listada sem detalhe (404) → `raw_reject` `not_found`
    2962  Challengers 2026: Brazil     707490 (VCL, sem veto, overtime), 681934 (Ascent sem
                                       histórico de lado, pegadinha 22)
    1015  Valorant Champions 2022      130691 (BO5 de 2022: fora da janela e antes do 1º patch
                                       do seed; exercita os filtros de janela e de temporada)
    3125  Elevate Play: Avalanche      757797 (tags de caixa mista e economia rotulada pelo
                                       nome, pegadinha 29; evento excluído pelo seed)

`AS_OF` fixa a data de referência: janela, aquecimento e corte das abas não mudam com o relógio.

CLI: python -m ingestion.fixture_lake [--lake data/fixture_lake]
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import shutil
from datetime import date
from functools import cache
from pathlib import Path

from ingestion.client import NotFound
from ingestion.collectors import backfill
from ingestion.config import ROOT

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
FIXTURE_LAKE_DIR = ROOT / "data" / "fixture_lake"
AS_OF = date(2026, 9, 29)
SINCE = 2022  # inclui a partida de 2022 de propósito

log = logging.getLogger(__name__)


def route(path: str, **params) -> tuple[str, tuple]:
    return path, tuple(sorted((k, str(v)) for k, v in params.items()))


class OfflineClient:
    """Mesma interface de `ApiClient.fetch`, servindo respostas roteirizadas.

    Rota ausente vira 404 (`NotFound`), exceto em `/events`: página sem rota é página vazia,
    que é como a API sinaliza o fim da paginação. Rota com uma exceção levanta a exceção (ex.:
    `TransientError`, o que o cliente real levanta depois de esgotar as tentativas).
    """

    def __init__(self, routes: dict[tuple[str, tuple], dict | Exception]):
        self.routes = routes
        self.calls: list[tuple[str, tuple]] = []
        self.network_requests = 0

    def fetch(self, path: str, params: dict | None = None, *, max_age_s=None) -> dict:
        key = route(path, **(params or {}))
        self.calls.append(key)
        self.network_requests += 1
        if key in self.routes:
            answer = self.routes[key]
            if isinstance(answer, Exception):
                raise answer
            return copy.deepcopy(answer)
        if path == "/events":
            return {"status": "OK", "size": 0, "data": []}
        raise NotFound(f"404 em {path}")


@cache
def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load(name: str) -> dict:
    return copy.deepcopy(_json(name))


def _events(name: str, ids: list[str], extra: list[dict] = ()) -> dict:
    body = load(name)
    body["data"] = [e for e in body["data"] if e["id"] in ids] + list(extra)
    return body


def _listing(matches: list[tuple[str, str, str, str]]) -> dict:
    """Listagem sintética: (id, data, time 1, time 2), o time 1 vencedor. A listagem só serve
    para descobrir ids e datas; nomes e placares de verdade vêm do detalhe."""
    return {
        "status": "OK",
        "data": [
            {
                "id": mid,
                "status": "completed",
                "date": day,
                "teams": [
                    {"name": a, "score": 2, "winner": True},
                    {"name": b, "score": 0, "winner": False},
                ],
            }
            for mid, day, a, b in matches
        ],
    }


CHAMPIONS_2022 = {
    "id": "1015",
    "name": "Valorant Champions 2022",
    "status": "completed",
    "prizepool": "1000000",
    "country": "tr",
}


ELEVATE_PLAY = {
    "id": "3125",
    "name": "Elevate Play: Avalanche",
    "status": "completed",
    "prizepool": "0",
    "country": "br",
}


def routes() -> dict:
    s2 = load("event_matches_vct_americas_s2_2026.json")
    s2["data"] = [m for m in s2["data"] if m["id"] in ("734308", "734313", "734307")]
    bo5_basic = load("match_bo5_2026_ot_basic.json")
    bo3 = load("match_bo3_2x0_basic.json")
    vcl = load("match_vcl_brasil_basic.json")
    without_sides = load("match_vcl_map_without_sides_tabs_all.json")
    bo5_2022 = load("match_bo5_2022_basic.json")
    vct_ids = ["2977"]
    return {
        route("/events", tier="vct", page=1): _events(
            "events_vct_p1.json", vct_ids, [CHAMPIONS_2022]
        ),
        route("/events", tier="vct", region="americas", page=1): _events(
            "events_vct_p1.json", vct_ids, [CHAMPIONS_2022]
        ),
        # Champions 2022 também em EMEA: internacional pela regra do filtro `region`.
        route("/events", tier="vct", region="emea", page=1): _events(
            "events_vct_p1.json", [], [CHAMPIONS_2022]
        ),
        route("/events", tier="vcl", page=1): _events(
            "events_vcl_p1.json", ["2962"], [ELEVATE_PLAY]
        ),
        route("/events", tier="vcl", region="americas", page=1): _events(
            "events_vcl_p1.json", ["2962"], [ELEVATE_PLAY]
        ),
        route("/events/2977/matches"): s2,
        route("/events/2977/agents"): load("event_agents_vct_americas_s2_2026.json"),
        route("/events/2962/matches"): _listing(
            [
                ("707490", "Thu, July 16, 2026", "Team A", "Team B"),
                ("681934", "Thu, June 18, 2026", "Team A", "Team B"),
            ]
        ),
        route("/events/1015/matches"): _listing(
            [("130691", "Sat, September 17, 2022", "Team A", "Team B")]
        ),
        route("/events/3125/matches"): _listing(
            [("757797", "Wed, September 23, 2026", "Arashi", "BIDINHAS")]
        ),
        route("/matches/734308", tabs="all"): load("match_bo5_2026_ot_tabs_all.json"),
        route("/matches/734308"): bo5_basic,
        route("/matches/734313", tabs="all"): bo3,
        route("/matches/734313"): bo3,
        route("/matches/707490", tabs="all"): vcl,
        route("/matches/707490"): vcl,
        route("/matches/681934", tabs="all"): without_sides,
        route("/matches/681934"): without_sides,
        route("/matches/130691", tabs="all"): bo5_2022,
        route("/matches/130691"): bo5_2022,
        route("/matches/757797", tabs="all"): load("match_mixed_case_tags_tabs_all.json"),
    }


def build(root: Path = FIXTURE_LAKE_DIR) -> Path:
    """Recria o lake de fixtures do zero em `root`."""
    shutil.rmtree(root, ignore_errors=True)
    backfill(OfflineClient(routes()), since=SINCE, root=root, today=AS_OF)
    return root


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Recria o lake de fixtures (CI sem segredo).")
    parser.add_argument("--lake", type=Path, default=FIXTURE_LAKE_DIR)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    print(f"lake de fixtures em {build(args.lake)}")


if __name__ == "__main__":
    main()
