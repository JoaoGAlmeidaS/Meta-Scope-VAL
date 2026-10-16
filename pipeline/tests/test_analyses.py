"""Peças das análises que não dependem do warehouse: conversão série ↔ mapa e veredito."""

from __future__ import annotations

import pytest

from pipeline.analyses import map_probability, series_probability, verdict
from pipeline.stats import Estimate


@pytest.mark.parametrize("best_of", [3, 5])
@pytest.mark.parametrize("p", [0.2, 0.5, 0.65, 0.9])
def test_mapa_e_serie_sao_inversos(best_of, p):
    assert map_probability(series_probability(p, best_of), best_of) == pytest.approx(p, abs=1e-9)


def test_serie_amplifica_o_favorito():
    assert series_probability(0.6, 3) > 0.6
    assert series_probability(0.6, 5) > series_probability(0.6, 3)
    assert series_probability(0.5, 5) == pytest.approx(0.5)


def test_bo1_e_formatos_fixos_nao_convertem():
    assert map_probability(0.7, 1) == 0.7
    assert map_probability(0.7, None) == 0.7


def test_veredito_inconclusivo_sem_significancia():
    est = Estimate(0.53, 0.49, 0.57, 100)
    assert verdict(est, 0.5, 0.2, "ataque", "defesa") == "inconclusivo"
    assert verdict(est, 0.5, 0.01, "ataque", "defesa") == "ataque"
    assert verdict(Estimate(0.45, 0.4, 0.48, 100), 0.5, 0.01, "ataque", "defesa") == "defesa"


def test_todo_mart_lido_tem_ordem_fixa():
    """O bootstrap com semente só é reprodutível se a ordem das linhas for fixa (ver ORDER)."""
    import re
    from pathlib import Path

    from pipeline.analyses import ORDER

    analysis = Path(__file__).resolve().parents[2] / "dbt" / "models" / "analysis"
    marts = {p.stem for p in analysis.glob("mart_*.sql")}
    assert marts == set(ORDER)
    source = (Path(__file__).resolve().parents[1] / "analyses.py").read_text(encoding="utf-8")
    assert set(re.findall(r'table\(con, "(mart_\w+)"', source)) <= set(ORDER)


def test_time_que_mais_usou_a_composicao():
    import pandas as pd

    from pipeline.analyses import top_users

    rows = [
        # Haven 13: A usou 2 vezes, B 1 vez → A
        ("Haven", "13", "x", "A", "m1", "2026-01-01"),
        ("Haven", "13", "x", "A", "m2", "2026-01-02"),
        ("Haven", "13", "x", "B", "m3", "2026-03-01"),
        # Bind 13: empate 1 × 1 → vence o uso mais recente (D)
        ("Bind", "13", "x", "C", "m4", "2026-01-01"),
        ("Bind", "13", "x", "D", "m5", "2026-02-01"),
        # Bind 12: empate total → menor team_id (E)
        ("Bind", "12", "y", "F", "m6", "2025-12-01"),
        ("Bind", "12", "y", "E", "m7", "2025-12-01"),
    ]
    df = pd.DataFrame(
        rows,
        columns=["map_name", "patch_major", "composition_key", "team_id", "map_id", "match_date"],
    )
    top = top_users(df).set_index(["map_name", "patch_major"])
    assert top.loc[("Haven", "13"), "top_team_id"] == "A"
    assert top.loc[("Haven", "13"), "top_team_maps"] == 2
    assert top.loc[("Bind", "13"), "top_team_id"] == "D"
    assert top.loc[("Bind", "12"), "top_team_id"] == "E"


# --- recortes do site (janela × tier) ------------------------------------------------------------


def test_recorte_vira_where():
    from pipeline.analyses import DEFAULT, SCOPES, Scope, scope_where

    assert scope_where("mart_side_by_map", DEFAULT) == ""
    assert scope_where("mart_side_by_map", Scope(tier="vct")) == "where tier = 'vct'"
    assert scope_where("mart_pistol", Scope("recent")) == "where is_in_recent_window"
    assert (
        scope_where("mart_compositions", Scope("recent", "vcl"))
        == "where tier = 'vcl' and is_in_recent_window"
    )
    assert [s.key for s in SCOPES] == [
        "full-all",
        "full-vct",
        "full-vcl",
        "recent-all",
        "recent-vct",
        "recent-vcl",
    ]


def test_recorte_que_o_mart_nao_tem_e_erro():
    """Filtro ignorado em silêncio publicaria o número da janela inteira como sendo o do recorte."""
    from pipeline.analyses import Scope, scope_where

    with pytest.raises(ValueError):
        scope_where("mart_team_ratings", Scope(tier="vct"))
    with pytest.raises(ValueError):
        scope_where("mart_drift_side_by_quarter", Scope("recent"))  # o drift é o histórico inteiro
    with pytest.raises(ValueError):
        Scope("3m")
    with pytest.raises(ValueError):
        Scope(tier="'; drop table x; --")


def test_marts_com_recorte_tem_as_colunas():
    """TIERED e WINDOWED dizem quais marts têm as colunas; o SQL do mart tem que concordar."""
    from pathlib import Path

    from pipeline.analyses import TIERED, WINDOWED

    analysis = Path(__file__).resolve().parents[2] / "dbt" / "models" / "analysis"
    for name in TIERED:
        assert "tier" in (analysis / f"{name}.sql").read_text(encoding="utf-8"), name
    for name in WINDOWED:
        assert "is_in_recent_window" in (analysis / f"{name}.sql").read_text(encoding="utf-8"), name


def _warehouse(tables: dict[str, str]):
    """DuckDB em memória com os schemas do warehouse e as tabelas dadas (nome → select)."""
    import duckdb

    con = duckdb.connect()
    con.execute("create schema main_analysis; create schema main_marts")
    for name, select in tables.items():
        con.execute(f"create table {name} as {select}")
    return con


def test_velocidade_soma_os_tiers_antes_da_taxa():
    """Com todos os tiers, o pick rate do mês é a soma das composições, não a média das taxas."""
    import pandas as pd

    from pipeline.analyses import Scope, meta_speed

    con = _warehouse(
        {
            "main_analysis.mart_agent_popularity": """select * from (values
                (date '2026-01-01', 'vct', false, 'jett', 1, 2, 0.5),
                (date '2026-01-01', 'vct', false, 'omen', 2, 2, 1.0),
                (date '2026-01-01', 'vcl', false, 'jett', 6, 8, 0.75),
                (date '2026-01-01', 'vcl', false, 'omen', 2, 8, 0.25),
                (date '2026-02-01', 'vct', true, 'omen', 1, 1, 1.0)
            ) t(month, tier, is_in_recent_window, agent, compositions_with_agent, compositions,
                pick_rate)""",
            "main_marts.dim_patch": """select '12.01' as patch, date '2026-01-15' as release_date
                union all select '11.10', date '2025-11-01'""",
        }
    )
    out = meta_speed(con, n_boot=50)
    jan = out["pick_rate"].loc[pd.Timestamp("2026-01-01")]
    assert jan["jett"] == pytest.approx(7 / 10)  # (1 + 6) / (2 + 8); a média das taxas daria 0,625
    assert jan["omen"] == pytest.approx(4 / 10)
    assert out["speed"]["compositions"].tolist() == [1]
    assert out["patches"]["patch"].tolist() == ["12.01"]  # só os patches do período

    vct = meta_speed(con, Scope(tier="vct"), n_boot=50)["pick_rate"]
    assert vct.loc[pd.Timestamp("2026-01-01"), "jett"] == pytest.approx(0.5)
    recent = meta_speed(con, Scope("recent"), n_boot=50)
    assert recent["pick_rate"].index.tolist() == [pd.Timestamp("2026-02-01")]
    assert recent["speed"].empty  # um mês só: nada a comparar


def test_drift_soma_os_tiers_e_ignora_a_janela():
    from pipeline.analyses import Scope, drift

    con = _warehouse(
        {
            # sem rounds com lado no recorte: efeito de desenho 1
            "main_analysis.mart_side_by_map": """select 'x' as map_id, 'vct' as tier,
                false as is_in_recent_window, 0 as attack_rounds_won, 0 as regulation_rounds
                where false""",
            "main_analysis.mart_drift_side_by_quarter": """select * from (values
                ('Bind', date '2026-01-01', 'vct', 2, 40, 22, ['12.01']),
                ('Bind', date '2026-01-01', 'vcl', 3, 60, 28, ['12.01', '12.02'])
            ) t(map_name, quarter_start, tier, maps, regulation_rounds, attack_rounds_won,
                patches)""",
        }
    )
    allq = drift(con)["by_quarter"].iloc[0]
    assert (allq["maps"], allq["rounds"]) == (5, 100)
    assert allq["attack_win_rate"] == pytest.approx(0.5)  # (22 + 28) / 100
    assert allq["patches"] == ["12.01", "12.02"]
    # a visão recente não se aplica ao drift: o recorte recent-vct é o mesmo que full-vct
    vct = drift(con, Scope("recent", "vct"))["by_quarter"].iloc[0]
    assert (vct["maps"], vct["rounds"]) == (2, 40)
