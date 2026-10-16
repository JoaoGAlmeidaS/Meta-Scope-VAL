"""As perguntas do projeto (D15–D21), sobre os marts de análise do warehouse.

Uma função por pergunta. Cada uma lê os `mart_*` (já filtrados pela janela e pelo escopo, no
dbt) e devolve estimativas com intervalo de confiança, via `pipeline/stats.py`. Os notebooks
(`notebooks/`) e o site (`pipeline/site_artifacts.py`) chamam estas mesmas funções: o número do
site é o número do notebook.

Recortes do site (`Scope`): a janela de análise inteira ou a visão recente, e o tier. Toda função
recebe `scope` (padrão: janela inteira, todos os tiers, o que os notebooks usam), e `table` é o
único ponto que filtra por ele.

Veredito de cada efeito: "inconclusivo" quando o IC (ou o p-valor corrigido para múltiplas
comparações) não descarta a ausência de efeito. É resultado válido, e o site mostra assim.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import chi2

from pipeline import stats

ROOT = Path(__file__).resolve().parents[1]
ALPHA = 0.05
MIN_MAPS_MODEL = 100  # abaixo disso, a logística do pistol não é ajustada


def warehouse_path() -> Path:
    """O DuckDB do `make build` (dbt/metascope.duckdb, ou `DBT_DUCKDB_PATH` relativo a dbt/)."""
    path = Path(os.environ.get("DBT_DUCKDB_PATH", "metascope.duckdb"))
    return path if path.is_absolute() else ROOT / "dbt" / path


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or warehouse_path()), read_only=True)


# Ordem fixa de cada mart: o DuckDB devolve as linhas em ordem não determinística (varredura
# paralela), e o bootstrap com semente reamostra posições. Sem ordem, o IC mudaria a cada leitura e
# o número do site deixaria de ser o do notebook.
ORDER = {
    "mart_team_ratings": "rank_overall, team_id",
    "mart_team_matches": "team_id, match_id",
    "mart_team_maps": "team_id, map_name",
    "mart_team_roster": "team_id, player_id",
    "mart_side_by_map": "map_id",
    "mart_pistol": "map_id, team_id",
    "mart_veto_picks": "map_id",
    "mart_veto_actions": "map_name, veto_action, veto_step, tier, is_in_recent_window",
    "mart_international_matches": "match_id",
    "mart_compositions": "map_id, team_id",
    "mart_agent_popularity": "month, tier, is_in_recent_window, agent",
    "mart_drift_side_by_quarter": "map_name, quarter_start, tier",
    "mart_drift_agents_by_quarter": "map_name, quarter_start, tier, agent",
    "mart_elo_calibration": "match_id",
    "mart_matchups": "team_id, opponent_id",
}


# --- recortes do site ----------------------------------------------------------------------------

WINDOWS = ("full", "recent")  # janela de análise | visão recente (os meses vêm do dbt_project.yml)
TIERS = (None, "vct", "vcl")  # None: todos


@dataclass(frozen=True)
class Scope:
    """Recorte do site (Análises e Meta): a janela e o tier.

    `full` é a janela de análise (`analysis_window_months`); `recent`, a visão recente dentro dela
    (`recent_window_months`, a coluna `is_in_recent_window` dos marts). Os meses nunca ficam aqui.
    """

    window: str = "full"
    tier: str | None = None

    def __post_init__(self):
        if self.window not in WINDOWS or self.tier not in TIERS:
            raise ValueError(f"recorte inválido: {self.window!r}, {self.tier!r}")

    @property
    def key(self) -> str:
        """Nome do recorte nos caminhos do site: `full-all`, `recent-vct`…"""
        return f"{self.window}-{self.tier or 'all'}"


DEFAULT = Scope()
SCOPES = [Scope(w, t) for w in WINDOWS for t in TIERS]

# Marts que levam as colunas dos recortes. O drift é o histórico inteiro: tier sim, janela não.
TIERED = {
    "mart_side_by_map",
    "mart_pistol",
    "mart_veto_picks",
    "mart_veto_actions",
    "mart_international_matches",
    "mart_compositions",
    "mart_agent_popularity",
    "mart_elo_calibration",
    "mart_drift_side_by_quarter",
    "mart_drift_agents_by_quarter",
}
WINDOWED = TIERED - {"mart_drift_side_by_quarter", "mart_drift_agents_by_quarter"}


def scope_where(name: str, scope: Scope) -> str:
    """O `where` do recorte; recorte que o mart não tem é erro, nunca filtro ignorado."""
    clauses = []
    if scope.tier:
        if name not in TIERED:
            raise ValueError(f"{name} não tem tier")
        clauses.append(f"tier = '{scope.tier}'")  # validado contra TIERS no Scope
    if scope.window == "recent":
        if name not in WINDOWED:
            raise ValueError(f"{name} não tem a visão recente")
        clauses.append("is_in_recent_window")
    return f"where {' and '.join(clauses)}" if clauses else ""


def table(con: duckdb.DuckDBPyConnection, name: str, scope: Scope = DEFAULT) -> pd.DataFrame:
    where = scope_where(name, scope)
    return con.sql(f"select * from main_analysis.{name} {where} order by {ORDER[name]}").df()


def window(con: duckdb.DuckDBPyConnection) -> dict:
    """Primeira e última data da janela que o warehouse usou (pelos marts)."""
    lo, hi = con.sql(
        "select min(match_date), max(match_date) from main_analysis.mart_elo_calibration"
    ).fetchone()
    return {"first_match": str(lo), "last_match": str(hi)}


# --- utilidades ---------------------------------------------------------------------------------


def series_probability(p: float, best_of: int | None) -> float:
    """Probabilidade de vencer a série, dada a de vencer um mapa (mapas independentes)."""
    q = 1 - p
    if best_of == 3:
        return p**2 * (1 + 2 * q)
    if best_of == 5:
        return p**3 * (1 + 3 * q + 6 * q**2)
    return p


def map_probability(series_p: float, best_of: int | None) -> float:
    """Inverso de `series_probability`: o Elo prevê a série; a análise por mapa precisa do mapa."""
    best_of = None if pd.isna(best_of) else int(best_of)
    if best_of not in (3, 5) or series_p in (0.0, 1.0):
        return float(series_p)
    return float(brentq(lambda p: series_probability(p, best_of) - series_p, 0.0, 1.0))


def verdict(est: stats.Estimate, null: float, p_adjusted: float, above: str, below: str) -> str:
    if np.isnan(p_adjusted) or p_adjusted >= ALPHA:
        return "inconclusivo"
    return above if est.value > null else below


def with_verdicts(out: pd.DataFrame, column: str, null: float, above: str, below: str):
    """Holm sobre a coluna `p` e o veredito de cada linha (funciona com o quadro vazio)."""
    out["p_adj"] = stats.adjust(out["p"])
    out["verdict"] = [
        verdict(e, null, p, above, below) for e, p in zip(out[column], out["p_adj"], strict=True)
    ]
    return out


def agent_distance(pick_a, n_a: int, pick_b, n_b: int, rng, n_boot: int = 1000) -> dict:
    """Distância de variação total entre dois metas de agentes (0 = iguais, 1 = disjuntos).

    `pick_*` é o pick rate por agente (fração das composições com o agente; soma 5, um por
    jogador). IC por bootstrap paramétrico (binomial por agente nas duas amostras) e o piso de
    ruído: o percentil 95 da distância se A tivesse o meta de B, só com o tamanho de amostra de A.
    """
    a = np.asarray(pick_a, dtype=float)
    b = np.asarray(pick_b, dtype=float)
    a_boot = rng.binomial(n_a, a, size=(n_boot, len(a))) / n_a
    b_boot = rng.binomial(n_b, b, size=(n_boot, len(b))) / n_b
    same = rng.binomial(n_a, b, size=(n_boot, len(b))) / n_a
    lo, hi = np.quantile(0.5 * np.abs(a_boot - b_boot).sum(axis=1) / 5, [0.025, 0.975])
    return {
        "distance": float(0.5 * np.abs(a - b).sum() / 5),
        "low": float(lo),
        "high": float(hi),
        "noise_floor": float(np.quantile(0.5 * np.abs(same - b_boot).sum(axis=1) / 5, 0.95)),
    }


# --- D15: rating ----------------------------------------------------------------------------------


def ratings(con, top: int | None = None) -> pd.DataFrame:
    df = table(con, "mart_team_ratings").sort_values("rank_overall")
    return df.head(top) if top else df


def rating_history(con, team_ids: list[str]) -> pd.DataFrame:
    ids = ", ".join(f"'{t}'" for t in team_ids)
    return con.sql(f"""select e.team_id, e.match_at, e.rating_after
            from main_marts.fct_team_elo e where e.team_id in ({ids}) order by e.match_at""").df()


# --- D17: drift -----------------------------------------------------------------------------------


def design_effect(con, scope: Scope = DEFAULT) -> float:
    """Quanto a correlação entre rounds do mesmo mapa infla a variância (bootstrap ÷ binomial)."""
    df = table(con, "mart_side_by_map", scope)
    if df.empty:
        return 1.0
    boot = stats.cluster_bootstrap_rate(df["attack_rounds_won"], df["regulation_rounds"])
    p, n = boot.value, df["regulation_rounds"].sum()
    se_boot = (boot.high - boot.low) / (2 * stats.Z95)
    return max(1.0, se_boot**2 / (p * (1 - p) / n))


def drift(con, scope: Scope = DEFAULT) -> dict:
    """Vantagem de ataque por mapa e trimestre, sobre o histórico inteiro (D17).

    IC de Wilson com o n efetivo (rounds ÷ efeito de desenho), e um teste de homogeneidade por
    mapa: o lado favorecido muda entre trimestres mais do que o acaso explicaria? Do recorte vale
    só o tier: o drift é o histórico inteiro, e os tiers do mesmo trimestre são somados.
    """
    scope = Scope(tier=scope.tier)
    deff = design_effect(con, scope)
    df = (
        table(con, "mart_drift_side_by_quarter", scope)
        .groupby(["map_name", "quarter_start"], as_index=False)
        .agg(
            maps=("maps", "sum"),
            regulation_rounds=("regulation_rounds", "sum"),
            attack_rounds_won=("attack_rounds_won", "sum"),
            patches=("patches", lambda s: sorted(set().union(*map(list, s)))),
        )
    )
    rows = []
    for r in df.itertuples():
        n_eff = max(1, round(r.regulation_rounds / deff))
        est = stats.wilson(r.attack_rounds_won / r.regulation_rounds * n_eff, n_eff)
        rows.append(
            {
                "map_name": r.map_name,
                "quarter_start": pd.Timestamp(r.quarter_start),
                "maps": r.maps,
                "rounds": r.regulation_rounds,
                "attack_win_rate": est.value,
                "low": est.low,
                "high": est.high,
                "patches": list(r.patches),
            }
        )
    out = pd.DataFrame(
        rows,
        columns=[
            "map_name",
            "quarter_start",
            "maps",
            "rounds",
            "attack_win_rate",
            "low",
            "high",
            "patches",
        ],
    )
    tests = []
    for map_name, g in df.groupby("map_name"):
        if len(g) < 2:
            continue
        att = g["attack_rounds_won"].to_numpy() / deff
        tot = g["regulation_rounds"].to_numpy() / deff
        p = att.sum() / tot.sum()
        expected_att, expected_def = tot * p, tot * (1 - p)
        stat = (((att - expected_att) ** 2) / expected_att).sum() + (
            ((tot - att - expected_def) ** 2) / expected_def
        ).sum()
        tests.append(
            {
                "map_name": map_name,
                "quarters": len(g),
                "chi2": float(stat),
                "p": float(chi2.sf(stat, len(g) - 1)),
            }
        )
    tests_df = pd.DataFrame(tests, columns=["map_name", "quarters", "chi2", "p"])
    tests_df["p_adj"] = stats.adjust(tests_df["p"])
    tests_df["changes"] = tests_df["p_adj"] < ALPHA
    return {"by_quarter": out, "homogeneity": tests_df, "design_effect": deff}


def meta_drift(
    con,
    scope: Scope = DEFAULT,
    *,
    min_compositions: int = 40,
    n_boot: int = 1000,
    seed: int = 7,
) -> dict:
    """Distância do meta de cada trimestre ao meta atual, por mapa, sobre o histórico inteiro (D17).

    Distância de variação total entre as distribuições de agentes (0 = mesmo meta, 1 = nenhum
    agente em comum). O trimestre de referência é o mais recente com `min_compositions` no mapa.
    IC por bootstrap paramétrico (binomial por agente nos dois trimestres) e um piso de ruído: a
    distância esperada se o trimestre tivesse o meta atual, só com o tamanho de amostra dele.
    Do recorte vale só o tier, como no `drift`; os tiers do mesmo trimestre são somados.
    """
    df = table(con, "mart_drift_agents_by_quarter", Scope(tier=scope.tier))
    # composições por mapa × trimestre: o total se repete em cada agente, uma vez por tier
    totals = (
        df.drop_duplicates(["map_name", "quarter_start", "tier"])
        .groupby(["map_name", "quarter_start"])["compositions"]
        .sum()
    )
    rng = np.random.default_rng(seed)
    rows = []
    for map_name, g in df.groupby("map_name"):
        counts = g.pivot_table(
            index="quarter_start",
            columns="agent",
            values="compositions_with_agent",
            aggfunc="sum",
            fill_value=0,
        )
        n = totals.loc[map_name].reindex(counts.index)
        quarters = n[n >= min_compositions].index
        if len(quarters) < 2:
            continue
        ref = quarters.max()
        for q in quarters:
            d = agent_distance(
                counts.loc[q] / n[q], int(n[q]), counts.loc[ref] / n[ref], int(n[ref]), rng, n_boot
            )
            rows.append(
                {
                    "map_name": map_name,
                    "quarter_start": pd.Timestamp(q),
                    "reference_quarter": pd.Timestamp(ref),
                    "quarters_before": (ref.year - q.year) * 4 + (ref.month - q.month) // 3,
                    "compositions": int(n[q]),
                    **d,
                }
            )
    out = pd.DataFrame(
        rows,
        columns=[
            "map_name",
            "quarter_start",
            "reference_quarter",
            "quarters_before",
            "compositions",
            "distance",
            "low",
            "high",
            "noise_floor",
        ],
    )
    by_age = (
        out[out["quarters_before"] > 0]
        .groupby("quarters_before")
        .agg(
            maps=("map_name", "nunique"),
            distance=("distance", "mean"),
            noise_floor=("noise_floor", "mean"),
        )
        .reset_index()
    )
    return {"by_quarter": out, "by_age": by_age}


# --- D18: lado e pistol ---------------------------------------------------------------------------


def side_by_map(con, scope: Scope = DEFAULT) -> dict:
    """Taxa de rounds vencidos no ataque (1–24) por mapa, com bootstrap por mapa e Holm."""
    df = table(con, "mart_side_by_map", scope)
    overall = stats.cluster_bootstrap_rate(df["attack_rounds_won"], df["regulation_rounds"])
    rows = []
    for map_name, g in df.groupby("map_name"):
        est = stats.cluster_bootstrap_rate(g["attack_rounds_won"], g["regulation_rounds"])
        rows.append(
            {
                "map_name": map_name,
                "maps": len(g),
                "rounds": int(g["regulation_rounds"].sum()),
                "estimate": est,
                "p": stats.two_sided_p(est, 0.5),
            }
        )
    out = pd.DataFrame(rows, columns=["map_name", "maps", "rounds", "estimate", "p"])
    out = with_verdicts(out, "estimate", 0.5, "ataque", "defesa")
    return {"overall": overall, "by_map": out.sort_values("map_name").reset_index(drop=True)}


def pistol(con, scope: Scope = DEFAULT) -> dict:
    """Pistol → vitória no mapa, controlando a diferença de Elo (regressão logística).

    Abaixo de `MIN_MAPS_MODEL` mapas o modelo não é ajustado (`model` = None): a regressão não
    converge com amostra mínima (o lake de fixtures do CI) e o site mostra amostra insuficiente.
    """
    df = table(con, "mart_pistol", scope)
    one_side = df.sort_values(["map_id", "team_id"]).drop_duplicates("map_id")
    effect = (
        stats.pistol_effect(one_side["pistols_won"], one_side["won_map"], one_side["rating_diff"])
        if len(one_side) >= MIN_MAPS_MODEL
        else None
    )
    raw = {k: stats.wilson(float(g["won_map"].sum()), len(g)) for k, g in df.groupby("pistols_won")}
    return {"model": effect, "raw": raw, "n_maps": len(one_side)}


# --- D19: veto e regiões --------------------------------------------------------------------------


def veto(con, scope: Scope = DEFAULT) -> dict:
    """Vantagem de quem escolhe o mapa.

    Desenho pareado: nas partidas em que cada time escolheu um mapa, a força dos times se cancela
    (o melhor vence mais nos dois picks), e sem efeito de pick a taxa de vitória de quem escolheu
    seria 0,5. Por mapa: a taxa de quem escolheu contra a probabilidade de mapa esperada pelo Elo.
    """
    df = table(con, "mart_veto_picks", scope)
    pickers = df.groupby("match_id")["picker_team_id"].nunique()
    paired = df[df["match_id"].isin(pickers[pickers >= 2].index)]
    by_match = paired.groupby("match_id")["picker_won"].mean()
    overall = stats.mean_bootstrap(by_match.to_numpy())
    df = df.assign(
        expected_map=[
            map_probability(p, b)
            for p, b in zip(df["picker_expected_match_result"], df["best_of"], strict=True)
        ]
    )
    rows = []
    for map_name, g in df.groupby("map_name"):
        excess = stats.mean_bootstrap(
            (g["picker_won"].astype(float) - g["expected_map"]).to_numpy()
        )
        rows.append(
            {
                "map_name": map_name,
                "picks": len(g),
                "picker_win_rate": stats.wilson(float(g["picker_won"].sum()), len(g)),
                "excess_over_elo": excess,
                "p": stats.two_sided_p(excess, 0.0),
            }
        )
    out = pd.DataFrame(
        rows, columns=["map_name", "picks", "picker_win_rate", "excess_over_elo", "p"]
    )
    out = with_verdicts(
        out, "excess_over_elo", 0.0, "vantagem de quem escolhe", "desvantagem de quem escolhe"
    )
    # o mart separa tier e visão recente; o veto do recorte soma as contagens
    actions = (
        table(con, "mart_veto_actions", scope)
        .groupby(["map_name", "veto_action", "veto_step"], as_index=False)
        .agg(
            times=("times", "sum"),
            times_played=("times_played", "sum"),
            last_match_date=("last_match_date", "max"),
        )
    )
    return {
        "paired": overall,
        "paired_matches": len(by_match),
        "p_paired": stats.two_sided_p(overall, 0.5),
        "by_map": out.sort_values("map_name").reset_index(drop=True),
        "actions": actions,
    }


def regions(con, scope: Scope = DEFAULT) -> dict:
    """Força relativa entre regiões em partidas internacionais: resultado − esperado pelo Elo."""
    df = table(con, "mart_international_matches", scope)
    long = pd.concat(
        [
            pd.DataFrame(
                {
                    "region": df["team1_region"],
                    "opponent_region": df["team2_region"],
                    "result": df["team1_result"],
                    "expected": df["team1_expected_result"],
                }
            ),
            pd.DataFrame(
                {
                    "region": df["team2_region"],
                    "opponent_region": df["team1_region"],
                    "result": 1 - df["team1_result"],
                    "expected": 1 - df["team1_expected_result"],
                }
            ),
        ]
    )
    rows = []
    for region, g in long.groupby("region"):
        excess = stats.mean_bootstrap((g["result"] - g["expected"]).to_numpy())
        rows.append(
            {
                "region": region,
                "matches": len(g),
                "win_rate": stats.wilson(float(g["result"].sum()), len(g)),
                "excess_over_elo": excess,
                "p": stats.two_sided_p(excess, 0.0),
            }
        )
    out = pd.DataFrame(rows, columns=["region", "matches", "win_rate", "excess_over_elo", "p"])
    out = with_verdicts(out, "excess_over_elo", 0.0, "acima do Elo", "abaixo do Elo")
    matrix = (
        long.groupby(["region", "opponent_region"])["result"].agg(["sum", "count"]).reset_index()
    )
    return {"by_region": out, "matrix": matrix, "matches": len(df)}


# --- D20: composição e velocidade do meta ---------------------------------------------------------


def top_users(df: pd.DataFrame) -> pd.DataFrame:
    """O time que mais usou cada composição em cada recorte mapa × patch maior.

    `df` é o `mart_compositions` com `patch_major`. Desempate determinístico: mais mapas, depois o
    uso mais recente, depois o `team_id`. Devolve `top_team_id` e `top_team_maps` por composição.
    """
    keys = ["map_name", "patch_major", "composition_key"]
    per_team = (
        df.groupby([*keys, "team_id"])
        .agg(top_team_maps=("map_id", "size"), last_used=("match_date", "max"))
        .reset_index()
        .sort_values(
            [*keys, "top_team_maps", "last_used", "team_id"],
            ascending=[True, True, True, False, False, True],
        )
    )
    top = per_team.drop_duplicates(keys).rename(columns={"team_id": "top_team_id"})
    return top[[*keys, "top_team_id", "top_team_maps"]].reset_index(drop=True)


def compositions(con, min_maps: int = 5, scope: Scope = DEFAULT) -> pd.DataFrame:
    """Win rate por comp × mapa × patch maior, acima do esperado pelo Elo, com shrinkage.

    O esperado de cada mapa é a probabilidade de mapa derivada da série (`map_probability`): time
    forte joga comp "forte" e venceria de qualquer jeito. O shrinkage é estimado por mapa.
    """
    df = table(con, "mart_compositions", scope)
    df["expected_map"] = [
        map_probability(p, b)
        for p, b in zip(df["expected_match_result"], df["best_of"], strict=True)
    ]
    df["patch_major"] = df["patch"].str.split(".").str[0]
    grouped = (
        df.groupby(["map_name", "patch_major", "composition_key"])
        .agg(maps=("won_map", "size"), wins=("won_map", "sum"), expected=("expected_map", "sum"))
        .reset_index()
    )
    grouped["excess"] = (grouped["wins"] - grouped["expected"]) / grouped["maps"]
    parts = []
    for _, g in grouped.groupby(["map_name", "patch_major"]):
        g = g.copy()
        shrunk = stats.shrink(g["excess"], g["maps"])
        g["shrunk"] = [s.value for s in shrunk]
        g["low"] = [s.low for s in shrunk]
        g["high"] = [s.high for s in shrunk]
        parts.append(g)
    out = pd.concat(parts) if parts else grouped
    out["win_rate"] = out["wins"] / out["maps"]
    out = out.merge(top_users(df), on=["map_name", "patch_major", "composition_key"], how="left")
    return out[out["maps"] >= min_maps].sort_values(["map_name", "patch_major", "shrunk"])


def meta_speed(con, scope: Scope = DEFAULT, *, n_boot: int = 1000, seed: int = 7) -> dict:
    """Popularidade de agentes por mês e a velocidade de reorganização do meta.

    Velocidade = distância de variação total entre o meta de um mês e o do mês anterior
    (`agent_distance`, com IC e piso de ruído), com os patches do período para marcar. O mart
    separa tier e visão recente: as contagens do recorte são somadas antes da taxa.
    """
    df = table(con, "mart_agent_popularity", scope)
    picks = df.pivot_table(
        index="month",
        columns="agent",
        values="compositions_with_agent",
        aggfunc="sum",
        fill_value=0,
    )
    # o total do mês se repete em cada agente, uma vez por tier × visão
    n = (
        df.drop_duplicates(["month", "tier", "is_in_recent_window"])
        .groupby("month")["compositions"]
        .sum()
        .reindex(picks.index)
    )
    pivot = picks.div(n, axis=0)
    rng = np.random.default_rng(seed)
    rows = []
    for prev, month in zip(pivot.index[:-1], pivot.index[1:], strict=True):
        d = agent_distance(
            pivot.loc[month], int(n[month]), pivot.loc[prev], int(n[prev]), rng, n_boot
        )
        rows.append({"month": pd.Timestamp(month), "compositions": int(n[month]), **d})
    patches = con.execute(
        """select patch, release_date from main_marts.dim_patch
           where release_date between ? and ? order by release_date""",
        [df["month"].min(), df["month"].max()],
    ).df()
    speed = pd.DataFrame(
        rows, columns=["month", "compositions", "distance", "low", "high", "noise_floor"]
    )
    return {"pick_rate": pivot, "speed": speed, "patches": patches}


# --- D21: previsão --------------------------------------------------------------------------------


def calibration(con, scope: Scope = DEFAULT) -> dict:
    """Calibração do recorte; com todos os tiers, também cada tier (com um só, seria repetição)."""
    df = table(con, "mart_elo_calibration", scope)
    out = {"all": stats.calibration(df["team1_win_probability"], df["team1_result"])}
    if scope.tier is None:
        for tier, g in df.groupby("tier"):
            out[tier] = stats.calibration(g["team1_win_probability"], g["team1_result"])
    return out


def matchup(con, team_id: str, opponent_id: str) -> float | None:
    row = con.sql(f"""select win_probability from main_analysis.mart_matchups
            where team_id = '{team_id}' and opponent_id = '{opponent_id}'""").fetchone()
    return float(row[0]) if row else None
