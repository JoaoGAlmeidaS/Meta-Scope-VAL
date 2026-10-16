"""D22: os JSONs pré-computados do site, em `dist/data/` (contrato da seção 4 do documento mestre).

    meta.json                         versão do build, data, janelas, recortes, patches, contagens
    teams/index.json                  todos os times da janela: alimenta rankings e busca
    teams/{id}.json                   perfil: Elo, partidas, mapas com IC, forma, elenco
    agents.json                       ícone de cada agente (cópia local em imgs/agentsV)
    predictions/{id}.json             probabilidade de vitória contra cada time (mart_matchups)
    meta/{recorte}/index.json         fatias mapa × patch disponíveis no recorte
    meta/{recorte}/{mapa}-{patch}.json  composições com shrinkage, pick rate, lado e veto do mapa
    analyses/{recorte}/{nome}.json    as análises dos notebooks, com IC

`{recorte}` é a `Scope.key` de `pipeline/analyses.py`: a janela (`full`, a de análise, ou
`recent`, a visão recente) e o tier (`all`, `vct`, `vcl`), seis ao todo; o padrão é `full-all`,
o mesmo número dos notebooks. Times e previsões não têm recorte.

Não existe backend: tudo que o site mostra sai daqui. Os números vêm de `pipeline/analyses.py`, as
mesmas funções dos notebooks. O asset `site_artifacts` do Dagster chama `build`.
"""

from __future__ import annotations

import json
import math
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ingestion.config import ROOT, dbt_vars, months_before
from pipeline import analyses as A
from pipeline import stats

MIN_SLICE_MAPS = 20  # recorte mapa × patch com menos composições não vira página
MIN_COMP_MAPS = 3  # composição com menos mapas não aparece na tabela
IMG_DIR = ROOT / "web" / "assets" / "imgs"


IMG_EXTS = ("svg", "png", "webp", "jpg", "jpeg")  # ordem de preferência quando há mais de um


def image(folder: str, key: str, api_url) -> str | None:
    """Imagem do site: um arquivo manual em web/assets/imgs/{folder}/{key}.* vence a da API
    (vlr.gg); sem nenhum, `None`, e o site mostra as iniciais.

    O nome casa sem diferenciar maiúsculas (`Haven.webp` serve para `haven`), e o caminho devolvido
    usa o nome real do arquivo: o GitHub Pages diferencia maiúsculas na URL.
    """
    base = IMG_DIR / folder
    if base.is_dir():
        found = {
            f.suffix.lower().lstrip("."): f.name
            for f in base.iterdir()
            if f.is_file() and f.stem.lower() == key.lower()
        }
        for ext in IMG_EXTS:
            if ext in found:
                return f"assets/imgs/{folder}/{found[ext]}"
    return api_url if isinstance(api_url, str) and api_url else None


def team_logo(team_id: str, logo_url) -> str | None:
    return image("teams", team_id, logo_url)


def dist_dir() -> Path:
    return Path(os.environ.get("DIST_DIR", ROOT / "dist"))


def clean(obj):
    """Converte para JSON: Estimate vira dict, NaN vira null, data vira ISO."""
    if isinstance(obj, stats.Estimate):
        return clean(obj.as_dict())
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | np.ndarray | pd.Series):
        return [clean(v) for v in obj]
    if isinstance(obj, pd.Timestamp | datetime):
        return obj.date().isoformat() if obj == obj.normalize() else obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, float | np.floating):
        return None if math.isnan(obj) else round(float(obj), 6)  # o texto arredonda; aqui não
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def records(df: pd.DataFrame) -> list[dict]:
    return [clean(r) for r in df.to_dict("records")]


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


class Writer:
    def __init__(self, root: Path):
        self.root = root
        self.sizes: dict[str, int] = {}

    def __call__(self, path: str, payload) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(clean(payload), ensure_ascii=False, separators=(",", ":"))
        target.write_text(text, encoding="utf-8")
        self.sizes[path] = len(text.encode("utf-8"))


# --- times ----------------------------------------------------------------------------------------


def teams(con, write: Writer, window_start: date) -> list[dict]:
    ratings = A.ratings(con)
    history = con.sql(f"""select e.team_id, cast(e.match_at as date) as day, e.rating_after
            from main_marts.fct_team_elo e
            where cast(e.match_at as date) >= date '{window_start}'
            order by e.team_id, e.match_at, e.match_id""").df()
    history_by_team = dict(tuple(history.groupby("team_id")))

    def trend(team_id: str) -> list[float]:
        """O Elo depois de cada uma das 10 últimas séries na janela (sparkline do ranking)."""
        h = history_by_team.get(team_id)
        return [] if h is None else [round(x, 1) for x in h["rating_after"].tail(10)]

    index = [
        {
            "id": r.team_id,
            "name": r.team_name,
            "tag": r.team_tag,
            "region": r.region,
            "logo": team_logo(r.team_id, r.logo_url),
            "tier": r.tier,
            "rating": round(r.rating, 1),
            "rank": int(r.rank_overall),
            "rank_region_tier": int(r.rank_in_region_tier),
            "matches": int(r.matches_in_window),
            # séries do tier atual na janela; poucas = rating ainda assentando (selo provisório)
            "tier_matches": int(r.tier_matches_in_window),
            "provisional": bool(r.is_provisional),
            "win_rate": r.win_rate_in_window,
            "peak": round(r.peak_rating_in_window, 1),
            "last_match": pd.Timestamp(r.last_match_at).date(),
            "trend": trend(r.team_id),
        }
        for r in ratings.itertuples()
    ]
    write("teams/index.json", index)

    matches = A.table(con, "mart_team_matches").sort_values(
        ["match_date", "match_id"], ascending=False
    )
    maps = A.table(con, "mart_team_maps")
    roster = A.table(con, "mart_team_roster")
    by_team = {
        "matches": dict(tuple(matches.groupby("team_id"))),
        "maps": dict(tuple(maps.groupby("team_id"))),
        "roster": dict(tuple(roster.groupby("team_id"))),
        "history": history_by_team,
    }
    empty = pd.DataFrame()
    for team in index:
        tid = team["id"]
        m = by_team["matches"].get(tid, empty)
        hist = by_team["history"].get(tid, empty)
        team_maps = by_team["maps"].get(tid, empty)
        team_roster = by_team["roster"].get(tid, empty)
        latest = team_roster["last_played_on"].max() if len(team_roster) else None
        write(
            f"teams/{tid}.json",
            {
                "team": team,
                "elo": [
                    [d, round(r, 1)]
                    for d, r in zip(hist.get("day", []), hist.get("rating_after", []), strict=True)
                ],
                "form": [float(x) for x in m.get("result", pd.Series(dtype=float)).head(10)],
                "matches": [
                    {
                        "date": r.match_date,
                        "event": r.event_name,
                        "series": r.series_name,
                        "opponent_id": r.opponent_id,
                        "opponent": r.opponent_name,
                        "score": f"{int(r.maps_won)}–{int(r.maps_lost)}",
                        "result": r.result,
                        "expected": r.expected_result,
                        "rating_after": round(r.rating_after, 1),
                    }
                    for r in m.itertuples()
                ],
                "maps": sorted(
                    (
                        {
                            "map": r.map_name,
                            "played": int(r.maps_played),
                            "won": int(r.maps_won),
                            "win_rate": stats.wilson(r.maps_won, int(r.maps_played)),
                        }
                        for r in team_maps.itertuples()
                    ),
                    key=lambda x: -x["played"],
                ),
                "roster": [
                    {
                        "id": r.player_id,
                        "name": r.player_name,
                        "maps": int(r.maps_played),
                        "agent": r.main_agent,
                        "last_played": r.last_played_on,
                        "current": r.last_played_on == latest,
                    }
                    for r in team_roster.sort_values(
                        ["last_played_on", "maps_played"], ascending=False
                    ).itertuples()
                ],
            },
        )
    return index


def agents(con, write: Writer) -> None:
    """`agents.json`: agente → ícone local em imgs/agentsV/{agente}.*, ou `null` (iniciais).

    O vlr.gg bloqueia exibir os ícones dele em outro site (403), então a URL da API
    (`dim_agent.image_url`) não vai para o site: `make agent-icons` baixa os que faltam.
    """
    df = con.sql("select agent from main_marts.dim_agent order by agent").df()
    write("agents.json", {a: image("agentsV", a, None) for a in df["agent"]})


def predictions(con, write: Writer) -> None:
    df = con.sql(
        "select team_id, opponent_id, win_probability from main_analysis.mart_matchups"
    ).df()
    for tid, g in df.groupby("team_id"):
        write(
            f"predictions/{tid}.json",
            {
                "team_id": tid,
                "p": {
                    o: round(float(p), 3)
                    for o, p in zip(g.opponent_id, g.win_probability, strict=True)
                },
            },
        )


# --- meta (mapa × patch) --------------------------------------------------------------------------


def team_cards(con) -> dict[str, dict]:
    """Times da coluna "time que mais usou" (nome, tag, região e logo do retrato do dim_team)."""
    team_rows = con.sql(
        "select team_id, team_name, team_tag, region, logo_url from main_marts.dim_team"
    ).df()
    return {
        r.team_id: {
            "id": r.team_id,
            "name": r.team_name,
            "tag": r.team_tag,
            "region": r.region,
            "logo": team_logo(r.team_id, r.logo_url),
        }
        for r in team_rows.itertuples()
    }


def meta_slices(
    con, write: Writer, scope: A.Scope, side: dict, veto: dict, teams_by_id: dict
) -> list[dict]:
    comps = A.compositions(con, min_maps=1, scope=scope)
    raw = A.table(con, "mart_compositions", scope)
    raw["patch_major"] = raw["patch"].str.split(".").str[0]
    side_by_map = side["by_map"].set_index("map_name") if len(side["by_map"]) else None
    veto_by_map = veto["by_map"].set_index("map_name") if len(veto["by_map"]) else None
    slices = []
    for (map_name, major), g in raw.groupby(["map_name", "patch_major"]):
        if len(g) < MIN_SLICE_MAPS:
            continue
        agents = g["agents"].explode().value_counts() / len(g)
        c = comps[(comps["map_name"] == map_name) & (comps["patch_major"] == major)]
        c = c[c["maps"] >= MIN_COMP_MAPS].sort_values("shrunk", ascending=False)
        name = f"{slug(map_name)}-{major}"
        # banner do Meta: imgs/maps/{mapa}.* posta pelo usuário (a API não tem imagem de mapa)
        map_image = image("maps", slug(map_name), None)
        sd = (
            side_by_map.loc[map_name]
            if side_by_map is not None and map_name in side_by_map.index
            else None
        )
        vt = (
            veto_by_map.loc[map_name]
            if veto_by_map is not None and map_name in veto_by_map.index
            else None
        )
        write(
            f"meta/{scope.key}/{name}.json",
            {
                "map": map_name,
                "patch": f"{major}.x",
                "image": map_image,
                "compositions": len(g),
                "patches": sorted(g["patch"].unique()),
                "agents": [{"agent": a, "pick_rate": float(p)} for a, p in agents.items()],
                "comps": [
                    {
                        "key": r.composition_key,
                        "agents": r.composition_key.split("+"),
                        "maps": int(r.maps),
                        "wins": int(r.wins),
                        "win_rate": r.win_rate,
                        "above_elo": stats.Estimate(r.shrunk, r.low, r.high, int(r.maps)),
                        "raw_above_elo": r.excess,
                        "top_team": (
                            {**teams_by_id[r.top_team_id], "maps": int(r.top_team_maps)}
                            if r.top_team_id in teams_by_id
                            else None
                        ),
                    }
                    for r in c.itertuples()
                ],
                "side": (
                    None
                    if sd is None
                    else {"attack": sd["estimate"], "verdict": sd["verdict"], "p_adj": sd["p_adj"]}
                ),
                "veto": (
                    None
                    if vt is None
                    else {
                        "picks": int(vt["picks"]),
                        "picker_win_rate": vt["picker_win_rate"],
                        "above_elo": vt["excess_over_elo"],
                        "verdict": vt["verdict"],
                    }
                ),
            },
        )
        slices.append(
            {
                "file": name,
                "map": map_name,
                "patch": f"{major}.x",
                "compositions": len(g),
                "image": map_image,
            }
        )
    write(f"meta/{scope.key}/index.json", slices)
    return slices


# --- análises -------------------------------------------------------------------------------------


def analyses(con, write: Writer, scope: A.Scope, drifts: dict) -> dict:
    """As análises do recorte em `analyses/{scope.key}/`.

    `drifts` guarda o drift por tier: ele é o histórico inteiro, igual nas duas janelas, e é o
    cálculo mais caro; sai uma vez por tier e é gravado nos dois recortes.
    """
    folder = f"analyses/{scope.key}"
    side = A.side_by_map(con, scope)
    write(
        f"{folder}/sides.json",
        {
            "overall": side["overall"],
            "maps": records(
                side["by_map"][["map_name", "maps", "rounds", "estimate", "p_adj", "verdict"]]
            ),
        },
    )

    pistol = A.pistol(con, scope)
    write(
        f"{folder}/pistol.json",
        {
            "n_maps": pistol["n_maps"],
            "raw": pistol["raw"],
            "equal_elo": pistol["model"]["probabilities"] if pistol["model"] else None,
            "odds_ratios": pistol["model"]["odds_ratios"] if pistol["model"] else None,
        },
    )

    veto = A.veto(con, scope)
    actions = veto["actions"]
    ladder = {}
    for map_name, g in actions.groupby("map_name"):
        steps = g.pivot_table(
            index="veto_step", columns="veto_action", values="times", aggfunc="sum", fill_value=0
        )
        ladder[map_name] = [
            {"step": int(step), **{a: int(row.get(a, 0)) for a in ("ban", "pick", "decider")}}
            for step, row in steps.iterrows()
        ]
    write(
        f"{folder}/veto.json",
        {
            "paired": veto["paired"],
            "paired_matches": veto["paired_matches"],
            "p_paired": veto["p_paired"],
            "maps": records(
                veto["by_map"][
                    ["map_name", "picks", "picker_win_rate", "excess_over_elo", "p_adj", "verdict"]
                ]
            ),
            "ladder": ladder,
        },
    )

    reg = A.regions(con, scope)
    write(
        f"{folder}/regions.json",
        {
            "matches": reg["matches"],
            "regions": records(reg["by_region"].drop(columns=["p"], errors="ignore")),
            "matrix": records(reg["matrix"].rename(columns={"sum": "wins", "count": "matches"})),
        },
    )

    comps = A.compositions(con, min_maps=5, scope=scope)
    write(
        f"{folder}/compositions.json",
        {
            "tested": len(comps),
            "above": int((comps["low"] > 0).sum()),
            "below": int((comps["high"] < 0).sum()),
            "top": [
                {
                    "map": r.map_name,
                    "patch": f"{r.patch_major}.x",
                    "key": r.composition_key,
                    "maps": int(r.maps),
                    "win_rate": r.win_rate,
                    "above_elo": stats.Estimate(r.shrunk, r.low, r.high, int(r.maps)),
                }
                for r in comps.sort_values("shrunk", ascending=False).head(15).itertuples()
            ],
        },
    )

    speed = A.meta_speed(con, scope)
    pick = speed["pick_rate"]
    top_agents = pick.mean().sort_values(ascending=False).head(18).index
    write(
        f"{folder}/meta-speed.json",
        {
            "months": [pd.Timestamp(m) for m in pick.index],
            "pick_rate": {a: pick[a].round(4).tolist() for a in top_agents},
            "speed": records(speed["speed"]),
            "patches": records(speed["patches"]),
        },
    )

    if scope.tier not in drifts:
        drift_side = A.drift(con, scope)
        drift_meta = A.meta_drift(con, scope)
        drifts[scope.tier] = {
            "meta_by_age": records(drift_meta["by_age"]),
            "meta_by_quarter": records(
                drift_meta["by_quarter"][
                    [
                        "map_name",
                        "quarter_start",
                        "quarters_before",
                        "distance",
                        "low",
                        "high",
                        "noise_floor",
                    ]
                ]
            ),
            "side_by_quarter": records(
                drift_side["by_quarter"][
                    ["map_name", "quarter_start", "rounds", "attack_win_rate", "low", "high"]
                ]
            ),
            "homogeneity": records(drift_side["homogeneity"]),
            "design_effect": drift_side["design_effect"],
        }
    write(f"{folder}/drift.json", drifts[scope.tier])

    cal = A.calibration(con, scope)
    write(f"{folder}/calibration.json", cal)
    return {"side": side, "veto": veto, "pistol": pistol, "regions": reg, "calibration": cal}


# --- tudo -----------------------------------------------------------------------------------------


def build(con=None, out: Path | None = None, *, version: str | None = None) -> dict[str, int]:
    """Gera `dist/data/` inteiro (apaga o anterior) e devolve o tamanho de cada arquivo."""
    con = con or A.connect()
    root = (out or dist_dir()) / "data"
    if root.exists():
        shutil.rmtree(root)
    write = Writer(root)
    now = datetime.now(UTC)
    as_of = (
        date.fromisoformat(os.environ["AS_OF_DATE"]) if os.environ.get("AS_OF_DATE") else now.date()
    )
    months = int(dbt_vars()["analysis_window_months"])
    recent_months = int(dbt_vars()["recent_window_months"])
    window_start = months_before(as_of, months)

    drifts: dict = {}
    teams_by_id = team_cards(con)
    slices = {}
    for scope in A.SCOPES:
        results = analyses(con, write, scope, drifts)
        slices[scope.key] = meta_slices(
            con, write, scope, results["side"], results["veto"], teams_by_id
        )
    index = teams(con, write, window_start)
    predictions(con, write)
    agents(con, write)

    observed = A.window(con)
    patches = con.sql(f"""select patch, release_date from main_marts.dim_patch
            where coalesce(next_release_date, date '9999-12-31') > date '{window_start}'
              and release_date <= date '{as_of}'
            order by release_date""").df()
    counts = con.sql("""select
             (select count(*) from main_analysis.mart_elo_calibration) as matches,
             (select count(*) from main_analysis.mart_side_by_map) as maps_with_sides,
             (select count(distinct map_id) from main_analysis.mart_compositions) as maps""").df()
    write(
        "meta.json",
        {
            "version": version
            or os.environ.get("GITHUB_SHA", "")[:7]
            or now.strftime("%Y%m%d%H%M"),
            "built_at": now.replace(microsecond=0).isoformat(),
            "as_of": as_of,
            "window": {
                "months": months,
                "start": window_start,
                "end": as_of,
                "first_match": observed["first_match"],
                "last_match": observed["last_match"],
                # visão recente, a alternativa da janela nas Análises e no Meta
                "recent_months": recent_months,
                "recent_start": months_before(as_of, recent_months),
            },
            "scopes": [s.key for s in A.SCOPES],
            "default_scope": A.DEFAULT.key,
            "patches": records(patches),
            "current_patch": patches["patch"].iloc[-1] if len(patches) else None,
            "counts": {"teams": len(index), **records(counts)[0]},
            "meta_slices": {k: len(v) for k, v in slices.items()},
        },
    )
    return write.sizes
