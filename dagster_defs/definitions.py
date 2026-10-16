"""Ponto de entrada do Dagster — D12.

    uv run dagster dev -m dagster_defs.definitions                     UI local
    uv run dagster asset materialize -m dagster_defs.definitions \\
        --select 'group:lake' --partition 2026                         coleta uma temporada
    uv run dagster job execute -m dagster_defs.definitions -j build    warehouse + site (dist/)

O `make ingest` e o `make build` chamam esses comandos; o GitHub Actions chama o `make`.
"""

from __future__ import annotations

from dagster import AssetSelection, Definitions, define_asset_job
from dagster_dbt import DbtCliResource

from dagster_defs.assets import (
    VlrApi,
    dbt_project,
    lake_tables,
    site_artifacts,
    site_pages,
    warehouse,
)
from dagster_defs.checks import LAKE_CHECKS

ingest_job = define_asset_job(
    "ingest",
    selection=AssetSelection.assets(lake_tables),  # particionado por temporada, pelos assets
    description="Coleta uma temporada do lake, com os checks do lake.",
)

build_job = define_asset_job(
    "build",
    selection=AssetSelection.assets(warehouse, site_artifacts, site_pages),
    description=(
        "Reconstrói o warehouse do zero a partir do lake (dbt build, testes = checks) e gera os "
        "JSONs e as páginas do site em dist/."
    ),
)

defs = Definitions(
    assets=[lake_tables, warehouse, site_artifacts, site_pages],
    asset_checks=LAKE_CHECKS,
    jobs=[ingest_job, build_job],
    resources={"dbt": DbtCliResource(project_dir=dbt_project), "vlr": VlrApi()},
)
