"""O Dagster lê o manifest do dbt ao importar as definições: gera antes, uma vez por sessão."""

from __future__ import annotations

import pytest
from dbt.cli.main import dbtRunner

from ingestion.config import ROOT

DBT_DIR = ROOT / "dbt"


@pytest.fixture(scope="session", autouse=True)
def dbt_manifest():
    if not (DBT_DIR / "dbt_packages").exists():
        pytest.skip("rode `dbt deps` antes (make dbt-deps)")
    result = dbtRunner().invoke(
        ["parse", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet"]
    )
    assert result.success, result.exception
    return DBT_DIR / "target" / "manifest.json"
