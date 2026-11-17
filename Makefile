.PHONY: install test lint typecheck up down migrate backfill collect probe rules cycle run demo keepalive weekly-report

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

typecheck:
	uv run mypy

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

backfill:
	uv run monitor backfill

collect:
	uv run monitor collect --provider $(or $(PROVIDER),all)

probe:
	uv run monitor probe

rules:
	uv run monitor rules

# One full cycle: collect, probe, then evaluate rules.
cycle: collect probe rules

run:
	uv run monitor run

demo:
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) collect
	$(MAKE) run

keepalive:
	uv run scripts/keepalive.py

weekly-report:
	uv run scripts/weekly_report.py
