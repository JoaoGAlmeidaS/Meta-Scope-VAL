"""D12: o Dagster é o pipeline. As definições carregam, a coleta materializa uma temporada sem
rede (cliente offline dos fixtures) e os checks do lake pegam o que devem pegar."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext

import pyarrow.parquet as pq
from dagster import AssetKey, materialize

from ingestion import lake
from ingestion.fixture_lake import OfflineClient, build, routes


def test_definicoes_carregam_com_a_linhagem_lake_dbt():
    from dagster_defs.definitions import defs

    repo = defs.get_repository_def()
    keys = repo.asset_graph.get_all_asset_keys()
    assert {AssetKey(["lake", t]) for t in lake.SCHEMAS} <= keys
    assert AssetKey(["marts", "fct_round"]) in keys
    # O source `lake.raw_round` do dbt é o mesmo asset da coleta: a linhagem liga os dois.
    parents = repo.asset_graph.get(AssetKey(["staging", "stg_rounds"])).parent_keys
    assert AssetKey(["lake", "raw_round"]) in parents
    assert {job.name for job in repo.get_all_jobs()} >= {"ingest", "build"}
    # O site depende dos marts de análise: o job `build` gera os JSONs depois do dbt.
    site = repo.asset_graph.get(AssetKey(["site", "site_artifacts"]))
    assert AssetKey(["analysis", "mart_team_ratings"]) in site.parent_keys
    assert AssetKey(["analysis", "mart_matchups"]) in site.parent_keys


def test_ingest_materializa_uma_temporada_sem_rede(tmp_path, monkeypatch):
    from dagster_defs.assets import VlrApi, lake_tables

    class OfflineVlr(VlrApi):
        def open(self) -> AbstractContextManager:
            return nullcontext(OfflineClient(routes()))

    monkeypatch.setenv("LAKE_DIR", str(tmp_path))
    result = materialize([lake_tables], partition_key="2026", resources={"vlr": OfflineVlr()})

    assert result.success
    matches = lake.read_table(tmp_path, "raw_match")["match_id"].to_pylist()
    assert sorted(matches) == [
        "681934",
        "707490",
        "734308",
        "734313",
        "757797",
    ]  # 2022 fica de fora
    (materialization,) = (
        m
        for m in result.asset_materializations_for_node("lake_tables")
        if m.asset_key == AssetKey(["lake", "raw_match"])
    )
    assert materialization.metadata["matches"].value == 5


def test_checks_do_lake(tmp_path):
    from dagster_defs.checks import (
        duplicated_matches,
        events_missing_from_index,
        final_reject_rate,
    )

    root = build(tmp_path / "lake")
    assert duplicated_matches(root) == []
    assert events_missing_from_index(root) == []
    assert final_reject_rate(root) == (1, 7)  # 734307: 404 definitivo

    # Uma partida gravada em dois arquivos de evento: o staging deduplicaria em silêncio.
    source = root / "raw_match" / "season=2026" / "2977.parquet"
    pq.write_table(pq.read_table(source), root / "raw_match" / "season=2026" / "9999.parquet")
    assert [m for m, _ in duplicated_matches(root)] == ["734308", "734313"]
