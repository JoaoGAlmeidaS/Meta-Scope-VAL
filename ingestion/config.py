"""Configuração compartilhada entre a coleta e o dbt.

A janela de análise e o aquecimento do Elo vivem em `dbt/dbt_project.yml` (vars). A coleta lê de
lá para decidir quais partidas vêm com `tabs=all`: uma fonte só, nunca hardcoded.
"""

from __future__ import annotations

import calendar
from datetime import date
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT = ROOT / "dbt" / "dbt_project.yml"
LAKE_DIR = ROOT / "data" / "lake"

# A coleta própria começa em 2025 (decisão de 05/10): janela de análise e aquecimento do Elo cabem
# aí, e a instância pública rende ~13 requisições/min. O histórico anterior, que só o drift (D17)
# usa, vem de um dataset pronto importado à parte.
HISTORY_SINCE = 2025


@cache
def dbt_vars() -> dict:
    return yaml.safe_load(DBT_PROJECT.read_text(encoding="utf-8"))["vars"]


def months_before(day: date, months: int) -> date:
    """`day` recuado `months` meses; o dia é limitado ao fim do mês (31/03 − 1 → 28/02)."""
    total = day.year * 12 + day.month - 1 - months
    year, month = divmod(total, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last))


def tabs_cutoff(today: date) -> date:
    """Primeiro dia coletado com `tabs=all`: janela de análise + aquecimento do Elo."""
    v = dbt_vars()
    return months_before(today, int(v["analysis_window_months"]) + int(v["elo_warmup_months"]))
