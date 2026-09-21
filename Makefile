.PHONY: install db-up db-down db-init load harvest test lint fmt itest

install:
	python -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

db-init:
	askarxiv db-init

harvest:
	askarxiv harvest --months 6 --category cs.AI --out data/papers.jsonl

load:
	askarxiv load --path data/papers.jsonl

test:
	pytest -q -m "not integration"

itest:
	docker compose up -d --wait && pytest -q -m integration

lint:
	ruff check . && mypy askarxiv

fmt:
	ruff check --fix . && ruff format .
