"""Assets — D12. O Dagster define o pipeline; o `make` e o GitHub Actions disparam.

    lake/raw_*  (partição: temporada)  →  dbt: staging → intermediate → marts
                                          (testes do dbt viram asset checks)

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
    AssetExecutionContext,
    AssetKey,
    AssetSpec,
    ConfigurableResource,
    MaterializeResult,
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
