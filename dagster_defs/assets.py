"""Assets — D12. O Dagster define o pipeline; o `make` e o GitHub Actions disparam.

    lake/raw_*  (partição: temporada)  →  dbt: staging → intermediate → marts → analysis
                                          (testes do dbt viram asset checks)
                                       →  site/site_artifacts (JSONs de dist/data, D22)
                                       →  site/site_pages (HTML de dist/, D24)

A coleta é um multi-asset: materializar uma temporada roda a coleta daquela temporada, que grava
as nove tabelas raw juntas, evento a evento (`ingestion/collectors.py`). O dbt não é
particionado: o DuckDB é efêmero e o warehouse é reconstruído inteiro a cada build.

Os sources do dbt (`lake.raw_*`) viram as chaves `lake/raw_*` pelo tradutor padrão do
dagster-dbt, o mesmo nome dos assets da coleta: a linhagem lake → dbt sai sem configuração.

Sem `from __future__ import annotations` aqui: o Dagster inspeciona a anotação de `context` em
tempo de definição, e anotação em string não passa.
"""

from contextlib import AbstractContextManager

from dagster import (
    AssetCheckResult,
    AssetCheckSpec,
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    ConfigurableResource,
    MaterializeResult,
    asset,
    multi_asset,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from dagster_defs.partitions import season_partitions
from ingestion import lake
from ingestion.client import ApiClient
from ingestion.collectors import backfill
from ingestion.config import ROOT

LAKE_KEYS = [AssetKey(["lake", name]) for name in lake.SCHEMAS]


class VlrApi(ConfigurableResource):
    """A API vlresports como resource: o asset não constrói o cliente, recebe.

    Em produção é o `ApiClient` (retry, rate limit, cache); nos testes, o cliente offline dos
    fixtures (`ingestion/fixture_lake.py`) no lugar, sem rede.
    """

    def open(self) -> AbstractContextManager:
        return ApiClient()


dbt_project = DbtProject(project_dir=ROOT / "dbt")
dbt_project.prepare_if_dev()  # `dagster dev` gera o manifest; `make` roda `dbt parse` antes


@multi_asset(
    specs=[
        AssetSpec(
            key,
            group_name="lake",
            kinds={"parquet"},
            description=f"Tabela raw `{key.path[-1]}` do lake (schema em ingestion/lake.py).",
        )
        for key in LAKE_KEYS
    ],
    partitions_def=season_partitions,
    can_subset=False,
)
def lake_tables(context: AssetExecutionContext, vlr: VlrApi):
    """Coleta uma temporada: eventos VCT e VCL, listagens, gabarito e detalhe de partida.

    Retomável: evento completo no lake é pulado e o resto vem do cache do cliente.
    """
    season = int(context.partition_key)
    root = lake.default_root()
    with vlr.open() as client:
        stats = backfill(client, since=season, root=root, only_season=season)
    metadata = {
        "season": season,
        "events_written": stats.events_written,
        "events_skipped": stats.events_skipped,
        "matches": stats.matches,
        "rejects": sum(stats.rejects.values()),
        "lake": str(root),
    }
    for key in LAKE_KEYS:
        yield MaterializeResult(asset_key=key, metadata=metadata)


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def warehouse(context: AssetExecutionContext, dbt: DbtCliResource):
    """`dbt build`: seeds, models e testes (cada teste vira um asset check no Dagster)."""
    yield from dbt.cli(["build"], context=context).stream()


# Marts que o site lê (pipeline/site_artifacts.py): a ordem no job vem destas dependências.
SITE_SOURCES = [
    AssetKey(["analysis", name])
    for name in (
        "mart_team_ratings",
        "mart_team_matches",
        "mart_team_maps",
        "mart_team_roster",
        "mart_matchups",
        "mart_side_by_map",
        "mart_pistol",
        "mart_veto_picks",
        "mart_veto_actions",
        "mart_international_matches",
        "mart_compositions",
        "mart_agent_popularity",
        "mart_drift_side_by_quarter",
        "mart_drift_agents_by_quarter",
        "mart_elo_calibration",
    )
] + [AssetKey(["marts", "fct_team_elo"]), AssetKey(["marts", "dim_patch"])]

MAX_FILE_KB = 300  # critério de pronto do D22: o maior JSON cabe em poucas centenas de KB


@asset(
    key=AssetKey(["site", "site_artifacts"]),
    group_name="site",
    kinds={"json"},
    deps=SITE_SOURCES,
    check_specs=[
        AssetCheckSpec("largest_file_under_limit", asset=AssetKey(["site", "site_artifacts"]))
    ],
)
def site_artifacts(context: AssetExecutionContext):
    """JSONs pré-computados do site em dist/data: meta, times, previsões, meta e análises."""
    from pipeline.site_artifacts import build, dist_dir

    sizes = build()
    largest, size = max(sizes.items(), key=lambda kv: kv[1])
    return MaterializeResult(
        metadata={
            "files": len(sizes),
            "total_kb": round(sum(sizes.values()) / 1024, 1),
            "largest": largest,
            "largest_kb": round(size / 1024, 1),
            "dir": str(dist_dir() / "data"),
        },
        check_results=[
            AssetCheckResult(
                check_name="largest_file_under_limit",
                passed=size <= MAX_FILE_KB * 1024,
                metadata={"largest": largest, "kb": round(size / 1024, 1), "limit_kb": MAX_FILE_KB},
            )
        ],
    )


@asset(
    key=AssetKey(["site", "site_pages"]),
    group_name="site",
    kinds={"html"},
    deps=[site_artifacts],
)
def site_pages(context: AssetExecutionContext):
    """Páginas do site (Jinja2 sobre web/templates) e os assets de web/assets, em dist/."""
    from pipeline.build_site import build

    pages = build()
    return MaterializeResult(metadata={"pages": len(pages), "files": ", ".join(sorted(pages))})
