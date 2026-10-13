"""Asset checks do lake — D13.

Os testes do dbt cobrem o warehouse (viram asset checks pelo dagster-dbt). Estes olham o lake
antes do dbt, direto nos Parquet com DuckDB: o que pode dar errado na gravação e que o staging
esconderia ao deduplicar.

    raw_match   nenhuma partida em dois arquivos de evento (o staging deduplicaria em silêncio)
    raw_reject  rejeição definitiva abaixo de 5% das partidas (acima disso, a coleta quebrou)
    raw_event   todo evento com listagem está no índice (o índice é gravado mesmo em queda)
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from dagster import AssetCheckResult, AssetCheckSeverity, AssetKey, asset_check

from ingestion import lake

MAX_FINAL_REJECT_RATE = 0.05


def _read(root: Path, table: str) -> str:
    return f"read_parquet('{(root / table).as_posix()}/**/*.parquet', hive_partitioning = true)"


def _has(root: Path, table: str) -> bool:
    return any((root / table).glob("**/*.parquet"))


def duplicated_matches(root: Path) -> list[tuple[str, int]]:
    if not _has(root, "raw_match"):
        return []
    sql = f"""
        select match_id, count(*) as files from {_read(root, "raw_match")}
        group by match_id having count(*) > 1 order by match_id
    """
    return duckdb.sql(sql).fetchall()


def final_reject_rate(root: Path) -> tuple[int, int]:
    """(rejeições definitivas, partidas gravadas + rejeitadas)."""
    if not _has(root, "raw_reject"):
        return 0, 0
    matches = duckdb.sql(f"select count(*) from {_read(root, 'raw_match')}").fetchone()[0]
    rejects = duckdb.sql(
        f"select count(*) from {_read(root, 'raw_reject')} where reason <> 'unavailable'"
    ).fetchone()[0]
    return rejects, matches + rejects


def events_missing_from_index(root: Path) -> list[str]:
    if not _has(root, "raw_event_match"):
        return []
    indexed = set(lake.read_table(root, "raw_event")["event_id"].to_pylist())
    sql = f"select distinct event_id from {_read(root, 'raw_event_match')} order by 1"
    return [e for (e,) in duckdb.sql(sql).fetchall() if e not in indexed]


@asset_check(asset=AssetKey(["lake", "raw_match"]), blocking=True)
def raw_match_has_no_duplicates() -> AssetCheckResult:
    duplicated = duplicated_matches(lake.default_root())
    return AssetCheckResult(
        passed=not duplicated,
        metadata={"duplicated": len(duplicated), "sample": str(duplicated[:10])},
    )


@asset_check(asset=AssetKey(["lake", "raw_reject"]))
def raw_reject_rate_is_low() -> AssetCheckResult:
    rejects, total = final_reject_rate(lake.default_root())
    rate = rejects / total if total else 0.0
    return AssetCheckResult(
        passed=rate <= MAX_FINAL_REJECT_RATE,
        severity=AssetCheckSeverity.WARN,
        metadata={"final_rejects": rejects, "matches": total, "rate": round(rate, 4)},
    )


@asset_check(asset=AssetKey(["lake", "raw_event"]))
def raw_event_indexes_every_listing() -> AssetCheckResult:
    missing = events_missing_from_index(lake.default_root())
    return AssetCheckResult(
        passed=not missing,
        metadata={"missing": len(missing), "sample": str(missing[:10])},
    )


LAKE_CHECKS = [raw_match_has_no_duplicates, raw_reject_rate_is_low, raw_event_indexes_every_listing]
