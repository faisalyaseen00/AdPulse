PY := .venv/bin/python
ADP := .venv/bin/adpulse

.PHONY: install db setup ui test lint report docker

install:            ## create venv and install AdPulse (+ dev tools)
	python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -e ".[dev]"

install-airbyte:    ## add PyAirbyte for real Airbyte connectors
	.venv/bin/pip install -e ".[airbyte]"

db:                 ## start ClickHouse only
	docker compose up -d clickhouse

setup:              ## demo data -> ClickHouse -> models -> first recommendations
	$(ADP) setup

ui:                 ## run the Streamlit app on :8501
	$(ADP) ui

test:               ## unit + integration tests (integration needs ClickHouse with data)
	$(PY) -m pytest -q

lint:
	.venv/bin/ruff check src app tests

report:             ## build and send the weekly report
	$(ADP) report --send

docker:             ## full stack in Docker
	docker compose up -d --build
