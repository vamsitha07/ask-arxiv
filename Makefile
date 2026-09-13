.PHONY: install db-up db-down harvest test lint fmt

install:
	python -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

harvest:
	askarxiv harvest --months 6 --category cs.AI --out data/papers.jsonl

test:
	pytest -q

lint:
	ruff check . && mypy askarxiv

fmt:
	ruff check --fix . && ruff format .
