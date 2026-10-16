"""Elo dos times por partida (D15): duas linhas por partida, uma por time, com o rating antes.

Python model do dbt-duckdb, a exceção documentada à regra "transformação em SQL": o Elo é
iterativo (cada partida depende do rating que as anteriores deixaram), e a conta vive em
`pipeline/elo.py`, testada no pytest. O Makefile exporta `PYTHONPATH` com a raiz do projeto para o
dbt importar `pipeline`.
"""

import pandas as pd


def model(dbt, session):
    dbt.config(materialized="table")

    from pipeline.elo import EloParams, run_elo

    matches = dbt.ref("int_elo_matches").df()
    rows = run_elo(matches.to_dict("records"), EloParams())
    columns = [
        "match_id",
        "match_at",
        "season",
        "team_id",
        "opponent_id",
        "rating_before",
        "opponent_rating_before",
        "expected_result",
        "result",
        "rating_after",
        "k",
        "is_promotion",
    ]
    return pd.DataFrame(rows, columns=columns)
