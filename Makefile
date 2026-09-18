.PHONY: help setup lint fmt test ingest backfill dbt-run dbt-test docs build serve clean

DBT_DIR := dbt
DIST    := dist

help:  ## lista os alvos
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## cria o ambiente e instala os hooks
	uv sync
	uv run pre-commit install

lint:  ## ruff + black --check
	uv run ruff check .
	uv run black --check .

fmt:  ## formata
	uv run ruff check --fix .
	uv run black .

test:  ## pytest
	uv run pytest

ingest:  ## carga incremental (ultimo split)
	uv run python -m ingestion.collectors --incremental

backfill:  ## backfill historico local (roda uma vez, demora)
	uv run python -m ingestion.collectors --backfill --since 2022

dbt-run:  ## roda os models
	cd $(DBT_DIR) && uv run dbt build

dbt-test:  ## roda so os testes do dbt
	cd $(DBT_DIR) && uv run dbt test

docs:  ## gera o dbt docs em dist/lineage
	cd $(DBT_DIR) && uv run dbt docs generate

build: dbt-run docs  ## reconstroi o projeto do zero -> dist/
	uv run python -m pipeline.build_site

serve: ## serve dist/ em localhost:8000
	uv run python -m http.server 8000 --directory $(DIST)

clean:  ## remove artefatos de build
	rm -rf $(DIST) $(DBT_DIR)/target $(DBT_DIR)/*.duckdb .pytest_cache
