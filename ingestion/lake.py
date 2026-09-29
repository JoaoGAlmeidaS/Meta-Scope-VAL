"""Lake em Parquet: schema fechado, um arquivo por evento, partição Hive por temporada.

Layout (D5/D6):

    data/lake/raw_event/raw_event.parquet                     todos os eventos do escopo
    data/lake/{tabela}/season=2026/{event_id}.parquet         demais tabelas raw
    data/lake/_json/season=2026/{event_id}.jsonl.gz           respostas brutas do detalhe

Reescrever o arquivo de um evento é o upsert: rodar duas vezes não duplica linha. A temporada
fica só no caminho (chave Hive), nunca dentro do arquivo, para o DuckDB não ver duas colunas
`season`. O dbt lê com `read_parquet('{tabela}/**/*.parquet', hive_partitioning=true)`.

Tipos são forçados pelo schema: `pa.Table.from_pylist(rows, schema=...)` falha em vez de inferir.

Remoto (D7): dataset **privado** no Hugging Face (`python -m ingestion.lake push|pull`), com o
login do `hf auth login` ou `HF_TOKEN`. O backfill roda local e sobe; o CI baixa antes do dbt.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ingestion.config import LAKE_DIR

TS = pa.timestamp("us", tz="UTC")
HUB_REPO_NAME = "meta-scope-val-lake"


def _schema(*fields: tuple) -> pa.Schema:
    """Campos `(nome, tipo)` são anuláveis; `(nome, tipo, False)` não."""
    return pa.schema([pa.field(*f) for f in fields])


def _team_cols(prefix: str, *cols: tuple[str, pa.DataType]) -> list[tuple]:
    return [(f"{prefix}_{name}", type_) for name, type_ in cols]


_SCORE = [("score", pa.int16()), ("rounds_ct", pa.int16()), ("rounds_t", pa.int16())]
_ECONOMY = [("bank", pa.int32()), ("loadout", pa.int32()), ("buy", pa.string())]

SCHEMAS: dict[str, pa.Schema] = {
    # --- D5: eventos -----------------------------------------------------------------------
    "raw_event": _schema(
        ("event_id", pa.string(), False),
        ("name", pa.string(), False),
        ("status", pa.string(), False),
        ("tier", pa.string(), False),
        ("tier_ambiguous", pa.bool_(), False),
        ("region", pa.string()),
        ("season", pa.int16(), False),
        ("country", pa.string()),
        ("prizepool", pa.string()),
        ("first_listed_on", pa.date32()),
        ("last_listed_on", pa.date32()),
        ("collected_at", TS, False),
    ),
    "raw_event_match": _schema(
        ("event_id", pa.string(), False),
        ("match_id", pa.string(), False),
        ("status", pa.string(), False),
        ("listed_on", pa.date32()),
        ("team1_name", pa.string(), False),
        ("team1_score", pa.int16()),
        ("team1_winner", pa.bool_(), False),
        ("team2_name", pa.string(), False),
        ("team2_score", pa.int16()),
        ("team2_winner", pa.bool_(), False),
    ),
    "raw_event_agents": _schema(
        ("event_id", pa.string(), False),
        ("map_name", pa.string(), False),
        ("played", pa.int16(), False),
        ("atk_win_rate", pa.float64(), False),
        ("def_win_rate", pa.float64(), False),
        ("agent", pa.string(), False),
        ("pick_rate", pa.float64(), False),
    ),
    # --- D6: detalhe de partida ------------------------------------------------------------
    "raw_match": _schema(
        ("match_id", pa.string(), False),
        ("event_id", pa.string(), False),
        ("event_series", pa.string()),
        ("status", pa.string(), False),
        ("format", pa.string()),
        ("match_ts", TS, False),
        ("team1_id", pa.string(), False),
        ("team1_name", pa.string(), False),
        ("team1_score", pa.int16(), False),
        ("team2_id", pa.string(), False),
        ("team2_name", pa.string(), False),
        ("team2_score", pa.int16(), False),
        ("n_maps", pa.int16(), False),
        ("has_tabs", pa.bool_(), False),
        ("collected_at", TS, False),
    ),
    "raw_map": _schema(
        ("map_id", pa.string(), False),
        ("match_id", pa.string(), False),
        ("map_order", pa.int16(), False),
        ("map_name", pa.string(), False),
        ("status", pa.string(), False),
        ("picked_by_name", pa.string()),
        ("picked_by_team_id", pa.string()),
        ("duration_s", pa.int32()),
        ("team1_id", pa.string(), False),
        *_team_cols("team1", *_SCORE),
        ("team2_id", pa.string(), False),
        *_team_cols("team2", *_SCORE),
        ("bridge_ok", pa.bool_(), False),
    ),
    "raw_veto": _schema(
        ("match_id", pa.string(), False),
        ("step", pa.int16(), False),
        ("action", pa.string(), False),
        ("map_name", pa.string(), False),
        ("team_tag", pa.string()),
        ("team_id", pa.string()),
    ),
    "raw_round": _schema(
        ("match_id", pa.string(), False),
        ("map_id", pa.string(), False),
        ("round_number", pa.int16(), False),
        ("winner_tag", pa.string(), False),
        ("winner_team_id", pa.string()),
        ("winner_side", pa.string(), False),
        ("method", pa.string(), False),
        *_team_cols("team1", *_ECONOMY),
        *_team_cols("team2", *_ECONOMY),
    ),
    "raw_player_map": _schema(
        ("match_id", pa.string(), False),
        ("map_id", pa.string(), False),
        ("player_id", pa.string(), False),
        ("player_name", pa.string(), False),
        ("team_tag", pa.string(), False),
        ("team_id", pa.string()),
        ("agent", pa.string(), False),
        ("rating", pa.float64()),
        ("acs", pa.int16()),
        ("kills", pa.int16()),
        ("deaths", pa.int16()),
        ("assists", pa.int16()),
        ("kast", pa.int16()),
        ("adr", pa.int16()),
        ("hs", pa.int16()),
        ("first_bloods", pa.int16()),
        ("first_deaths", pa.int16()),
    ),
    "raw_reject": _schema(
        ("event_id", pa.string(), False),
        ("match_id", pa.string(), False),
        ("reason", pa.string(), False),
        ("error", pa.string(), False),
        ("collected_at", TS, False),
    ),
}

EVENT_TABLES = ("raw_event_match", "raw_event_agents")
DETAIL_TABLES = ("raw_match", "raw_map", "raw_veto", "raw_round", "raw_player_map", "raw_reject")


def to_table(name: str, rows: list[dict]) -> pa.Table:
    table = pa.Table.from_pylist(rows, schema=SCHEMAS[name])
    table.validate(full=True)
    for field, column in zip(table.schema, table.columns, strict=True):
        if not field.nullable and column.null_count:
            raise ValueError(
                f"{name}.{field.name}: {column.null_count} nulos em coluna obrigatória"
            )
    return table


def table_path(root: Path, name: str, season: int | None = None, event_id: str | None = None):
    if name == "raw_event":
        return root / name / f"{name}.parquet"
    return root / name / f"season={season}" / f"{event_id}.parquet"


def _atomic(path: Path, write) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    write(tmp)
    os.replace(tmp, path)
    return path


def write_table(
    root: Path,
    name: str,
    rows: list[dict],
    *,
    season: int | None = None,
    event_id: str | None = None,
) -> Path:
    """Grava (ou regrava) o arquivo inteiro. Tabela vazia também é gravada: marca o evento."""
    table = to_table(name, rows)
    path = table_path(root, name, season, event_id)
    return _atomic(path, lambda tmp: pq.write_table(table, tmp, compression="zstd"))


def write_json_archive(root: Path, season: int, event_id: str, records: list[dict]) -> Path:
    """Respostas brutas do detalhe, uma por linha. Kill matrix e `performance` só existem aqui."""
    path = root / "_json" / f"season={season}" / f"{event_id}.jsonl.gz"

    def write(tmp: Path) -> None:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return _atomic(path, write)


def read_table(root: Path, name: str) -> pa.Table:
    """Tabela inteira, com `season` vindo do caminho. Vazia (com schema) se não existir."""
    base = root / name
    if not base.exists():
        return SCHEMAS[name].empty_table()
    if name == "raw_event":
        return pq.read_table(table_path(root, name))
    dataset = ds.dataset(base, format="parquet", partitioning="hive", exclude_invalid_files=True)
    return dataset.to_table()


def collected_match_ids(root: Path, season: int, event_id: str) -> set[str] | None:
    """Partidas do evento já no lake (gravadas ou rejeitadas). `None`: evento nunca gravado."""
    paths = [table_path(root, name, season, event_id) for name in ("raw_match", "raw_reject")]
    if not all(p.exists() for p in paths):
        return None
    return {mid for p in paths for mid in pq.read_table(p, columns=["match_id"])[0].to_pylist()}


def default_root() -> Path:
    return Path(os.environ.get("LAKE_DIR", LAKE_DIR))


# --- D7: lake remoto no Hugging Face Datasets (privado) --------------------------------------


def hub_repo_id(api) -> str:
    """`HF_LAKE_REPO` ou `{usuário logado}/meta-scope-val-lake`."""
    return os.environ.get("HF_LAKE_REPO") or f"{api.whoami()['name']}/{HUB_REPO_NAME}"


def push(root: Path) -> str:
    """Sobe o lake local. Retomável: `upload_large_folder` guarda o progresso na própria pasta."""
    from huggingface_hub import HfApi

    api = HfApi()
    repo_id = hub_repo_id(api)
    api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
    api.upload_large_folder(
        repo_id,
        root,
        repo_type="dataset",
        private=True,
        allow_patterns=["**/*.parquet", "**/*.jsonl.gz"],
    )
    return repo_id


def pull(root: Path) -> str:
    """Baixa o lake para `root` (o CI faz isso antes do dbt)."""
    from huggingface_hub import HfApi, snapshot_download

    repo_id = hub_repo_id(HfApi())
    snapshot_download(repo_id, repo_type="dataset", local_dir=root)
    return repo_id


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sincroniza o lake com o Hugging Face.")
    parser.add_argument("command", choices=["push", "pull"])
    parser.add_argument("--lake", type=Path, default=None, help="raiz do lake (padrão: data/lake)")
    args = parser.parse_args(argv)
    root = args.lake or default_root()
    repo_id = push(root) if args.command == "push" else pull(root)
    print(f"{args.command}: {root} ↔ datasets/{repo_id}")


if __name__ == "__main__":
    main()
