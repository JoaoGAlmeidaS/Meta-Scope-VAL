"""Lake: tipos forçados, idempotência e leitura pelo DuckDB do jeito que o dbt vai ler."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

import duckdb
import pyarrow as pa
import pytest

from ingestion import lake
from ingestion.flatten import flatten_match

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def _write_bo5(root, load_match) -> dict[str, list[dict]]:
    detail = load_match("match_bo5_2026_ot_tabs_all.json")
    tables = flatten_match(detail, has_tabs=True, collected_at=NOW)
    tables["raw_reject"] = []
    for name, rows in tables.items():
        lake.write_table(root, name, rows, season=2026, event_id=detail.event.id)
    return tables


def _duck(root, name: str) -> duckdb.DuckDBPyRelation:
    # Mesmo padrão do `external_location` em dbt/models/staging/_sources.yml.
    glob = (root / name / "**" / "*.parquet").as_posix()
    return duckdb.sql(f"select * from read_parquet('{glob}', hive_partitioning=true)")


def test_bo5_completa_nas_cinco_tabelas(tmp_path, load_match):
    tables = _write_bo5(tmp_path, load_match)
    for name in ("raw_match", "raw_map", "raw_veto", "raw_round", "raw_player_map"):
        rel = _duck(tmp_path, name)
        assert rel.count("*").fetchone()[0] == len(tables[name]) > 0, name
        # Temporada vem do caminho, não do arquivo.
        assert rel.filter("season = 2026").count("*").fetchone()[0] == len(tables[name])


def _types(root, name: str) -> dict[str, str]:
    rel = _duck(root, name)
    return {col: str(type_) for col, type_ in zip(rel.columns, rel.types, strict=True)}


def test_tipos_do_schema_chegam_ao_duckdb(tmp_path, load_match):
    _write_bo5(tmp_path, load_match)
    match = _types(tmp_path, "raw_match")
    assert match["match_ts"] == "TIMESTAMP WITH TIME ZONE"
    assert match["team1_score"] == "SMALLINT"
    assert match["match_id"] == "VARCHAR"
    assert _types(tmp_path, "raw_round")["team1_bank"] == "INTEGER"


def test_regravar_o_evento_nao_duplica(tmp_path, load_match):
    first = _write_bo5(tmp_path, load_match)
    _write_bo5(tmp_path, load_match)
    assert _duck(tmp_path, "raw_round").count("*").fetchone()[0] == len(first["raw_round"])
    assert not list(tmp_path.rglob("*.tmp"))


def test_tipo_errado_falha_em_vez_de_inferir():
    row = {"match_id": "1", "step": "três", "action": "ban", "map_name": "Bind"}
    with pytest.raises((pa.ArrowInvalid, pa.ArrowTypeError)):
        lake.to_table("raw_veto", [row])


def test_obrigatorio_nulo_falha():
    row = {"match_id": "1", "step": 1, "action": "ban", "map_name": None}
    with pytest.raises((ValueError, pa.ArrowInvalid)):
        lake.to_table("raw_veto", [row])


def test_tabela_vazia_e_gravada_com_schema(tmp_path):
    path = lake.write_table(tmp_path, "raw_veto", [], season=2026, event_id="2962")
    assert path.exists()
    assert lake.read_table(tmp_path, "raw_veto").schema.names[:6] == lake.SCHEMAS["raw_veto"].names


def test_partidas_coletadas_incluem_rejeitadas(tmp_path, load_match):
    _write_bo5(tmp_path, load_match)
    assert lake.collected_match_ids(tmp_path, 2026, "2977") == {"734308"}
    reject = {
        "event_id": "2977",
        "match_id": "999",
        "reason": "api",
        "error": "404",
        "collected_at": NOW,
    }
    lake.write_table(tmp_path, "raw_reject", [reject], season=2026, event_id="2977")
    assert lake.collected_match_ids(tmp_path, 2026, "2977") == {"734308", "999"}
    assert lake.collected_match_ids(tmp_path, 2026, "1") is None


class FakeHub:
    """Imita o `HfApi` e o `snapshot_download` sem rede."""

    calls: list[tuple] = []

    def whoami(self):
        return {"name": "joao"}

    def create_repo(self, repo_id, **kwargs):
        self.calls.append(("create_repo", repo_id, kwargs))

    def upload_large_folder(self, repo_id, folder_path, **kwargs):
        self.calls.append(("upload", repo_id, kwargs))


def test_push_sobe_privado_so_parquet_e_json(tmp_path, monkeypatch):
    import huggingface_hub

    FakeHub.calls = []
    monkeypatch.setattr(huggingface_hub, "HfApi", FakeHub)
    monkeypatch.delenv("HF_LAKE_REPO", raising=False)

    assert lake.push(tmp_path) == "joao/meta-scope-val-lake"
    (_, _, create), (_, _, upload) = FakeHub.calls
    assert create == {"repo_type": "dataset", "private": True, "exist_ok": True}
    assert upload["private"] is True and upload["repo_type"] == "dataset"
    assert upload["allow_patterns"] == ["**/*.parquet", "**/*.jsonl.gz"]


def test_pull_respeita_repo_da_variavel_de_ambiente(tmp_path, monkeypatch):
    import huggingface_hub

    seen = {}
    monkeypatch.setattr(huggingface_hub, "HfApi", FakeHub)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda repo, **kw: seen.update(kw))
    monkeypatch.setenv("HF_LAKE_REPO", "outra/conta")
    assert lake.pull(tmp_path) == "outra/conta"
    assert seen == {"repo_type": "dataset", "local_dir": tmp_path}


def test_arquivo_json_bruto(tmp_path, load_json):
    body = load_json("match_bo5_2026_ot_basic.json")
    path = lake.write_json_archive(tmp_path, 2026, "2977", [{"match_id": "734308", "body": body}])
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        (line,) = fh.readlines()
    assert json.loads(line)["body"] == body
