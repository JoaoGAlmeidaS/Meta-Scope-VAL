.PHONY: help setup lint fmt test events backfill ingest lake-push lake-pull fixture-lake \
        dbt-deps dbt-parse seed dbt-build dbt-test build build-fixtures docs dagster-dev serve \
        clean

DBT_DIR       := dbt
DIST          := dist
DAGSTER       := uv run dagster
DEFS          := -m dagster_defs.definitions

# O dbt roda de dentro de dbt/ e o Python da raiz: o lake vai por caminho absoluto, em LAKE_DIR,
# que os dois leem. AS_OF_DATE vazio = hoje (data de referência da janela, macros/window.sql).
LAKE_DIR      ?= $(CURDIR)/data/lake
AS_OF_DATE    ?=
SEASON        ?= $(shell date +%Y)
export LAKE_DIR AS_OF_DATE

# Trilho de CI sem segredo: lake gerado dos fixtures, com a data de referência deles fixa.
FIXTURE_LAKE  := $(CURDIR)/data/fixture_lake
FIXTURE_AS_OF := 2026-09-29

help:  ## lista os alvos
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## cria o ambiente e instala os hooks
	uv sync
	uv run pre-commit install

lint:  ## ruff + black --check
	uv run ruff check .
	uv run black --check .

fmt:  ## formata
	uv run ruff check --fix .
	uv run black .

test:  ## pytest (fixtures, sem rede; os testes do Dagster pedem `make dbt-deps` antes)
	uv run pytest

# --- coleta -------------------------------------------------------------------------------

events:  ## indice de eventos, listagens de partidas e gabarito (D5)
	uv run python -m ingestion.collectors events

backfill:  ## backfill local desde 2025, do mais recente ao mais antigo (horas: rode no tmux)
	mkdir -p logs
	uv run python -m ingestion.collectors backfill 2>&1 | tee -a logs/backfill.log

ingest: dbt-parse  ## coleta uma temporada pelo Dagster (SEASON=2026 por padrao: a corrente)
	$(DAGSTER) asset materialize $(DEFS) --select 'group:lake' --partition $(SEASON)

lake-push:  ## envia data/lake ao dataset privado no Hugging Face
	uv run python -m ingestion.lake push

lake-pull:  ## baixa o lake do Hugging Face para data/lake
	uv run python -m ingestion.lake pull

fixture-lake:  ## recria o lake de fixtures em data/fixture_lake (CI sem segredo)
	uv run python -m ingestion.fixture_lake --lake $(FIXTURE_LAKE)

# --- warehouse ----------------------------------------------------------------------------

dbt-deps:  ## pacotes do dbt (dbt_utils)
	cd $(DBT_DIR) && uv run dbt deps --quiet

dbt-parse: dbt-deps  ## manifest do dbt, que o Dagster le ao carregar as definicoes
	cd $(DBT_DIR) && uv run dbt parse --quiet

seed: dbt-deps  ## carrega e testa os seeds (patches, overrides, excecoes de validacao)
	cd $(DBT_DIR) && uv run dbt build --select resource_type:seed

dbt-build: dbt-deps  ## dbt build direto, sem o Dagster (depuracao)
	cd $(DBT_DIR) && uv run dbt build

dbt-test:  ## so os testes do dbt
	cd $(DBT_DIR) && uv run dbt test

build: dbt-parse  ## reconstroi o warehouse do zero pelo Dagster (dbt + checks) e gera a linhagem
	rm -f $(DBT_DIR)/metascope.duckdb $(DBT_DIR)/metascope.duckdb.wal
	$(DAGSTER) job execute $(DEFS) -j build
	$(MAKE) docs

build-fixtures: fixture-lake  ## o mesmo build sobre o lake de fixtures (trilho 1 do CI)
	$(MAKE) build LAKE_DIR=$(FIXTURE_LAKE) AS_OF_DATE=$(FIXTURE_AS_OF)

docs:  ## dbt docs estatico em dist/lineage (a linhagem publica)
	cd $(DBT_DIR) && uv run dbt docs generate --static --quiet
	mkdir -p $(DIST)/lineage
	cp $(DBT_DIR)/target/static_index.html $(DIST)/lineage/index.html

dagster-dev: dbt-parse  ## UI local do Dagster, com historico em .dagster/
	mkdir -p .dagster
	DAGSTER_HOME=$(CURDIR)/.dagster $(DAGSTER) dev $(DEFS)

serve:  ## serve dist/ em localhost:8000
	uv run python -m http.server 8000 --directory $(DIST)

clean:  ## remove artefatos de build (o lake real e o cache da API ficam)
	find $(DIST) -mindepth 1 ! -name .gitkeep -delete
	rm -rf $(DBT_DIR)/target $(DBT_DIR)/metascope.duckdb* $(FIXTURE_LAKE) .pytest_cache
