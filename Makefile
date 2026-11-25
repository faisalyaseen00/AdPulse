PY := .venv/bin/python
ADP := .venv/bin/adpulse

.PHONY: install db setup ui api web web-install web-build test lint report docker

install:            ## create venv and install AdPulse (+ dev tools)
	python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev,api]"

install-airbyte:    ## add PyAirbyte for real Airbyte connectors
	.venv/bin/pip install -e ".[airbyte]"

db:                 ## start ClickHouse only
	docker compose up -d clickhouse

setup:              ## demo data -> ClickHouse -> models -> first recommendations
	$(ADP) setup

ui:                 ## run the Streamlit app on :8501
	$(ADP) ui

api:                ## run the HTTP API for the web app on :8000 (reloads on change)
	.venv/bin/uvicorn api.main:app --reload --reload-dir api --port 8000

web-install:        ## install the web app's packages
	cd web && npm ci

web:                ## run the web app on :5173 (expects `make api` in another terminal)
	cd web && npm run dev

web-build:          ## type-check and build the web app into web/dist
	cd web && npm run build

test:               ## unit + integration tests (integration needs ClickHouse with data)
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check src app api tests

report:             ## build and send the weekly report
	$(ADP) report --send

docker:             ## full stack in Docker
	docker compose up -d --build
