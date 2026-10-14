.PHONY: install test lint typecheck up down migrate backfill collect run demo

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

backfill:
	uv run monitor backfill --days 90

collect:
	uv run monitor collect

run:
	uv run monitor run

demo:
	$(MAKE) up
	$(MAKE) migrate
	$(MAKE) backfill
