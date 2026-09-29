"""A janela vem do `dbt_project.yml`, a mesma variável que os marts de análise leem."""

from __future__ import annotations

from datetime import date

import pytest

from ingestion.config import dbt_vars, months_before, tabs_cutoff


def test_janela_e_aquecimento_vem_do_dbt():
    v = dbt_vars()
    assert v["analysis_window_months"] == 12
    assert v["elo_warmup_months"] > 0


@pytest.mark.parametrize(
    "day,months,expected",
    [
        (date(2026, 9, 29), 18, date(2025, 3, 29)),
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
        (date(2024, 3, 31), 1, date(2024, 2, 29)),
        (date(2026, 1, 15), 12, date(2025, 1, 15)),
        (date(2026, 1, 15), 13, date(2024, 12, 15)),
    ],
)
def test_months_before(day, months, expected):
    assert months_before(day, months) == expected


def test_corte_das_abas_soma_janela_e_aquecimento():
    v = dbt_vars()
    today = date(2026, 9, 29)
    expected = months_before(today, v["analysis_window_months"] + v["elo_warmup_months"])
    assert tabs_cutoff(today) == expected
