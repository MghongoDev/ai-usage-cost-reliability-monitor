.PHONY: install test lint typecheck up down migrate backfill collect run demo keepalive weekly-report

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

collect:
	uv run monitor collect

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
