# Quick start

A fifteen-minute walkthrough that brings the whole system up from a fresh
clone and shows the control plane serving rows. No vendor admin keys are
needed; the bundled simulator supplies the data.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) installed and on `PATH`.
- Docker and Docker Compose, for the database and the simulator.

## Step 1: Clone and install

```bash
git clone https://github.com/MghongoDev/ai-usage-cost-reliability-monitor
cd ai-usage-cost-reliability-monitor
make install
```

`make install` runs `uv sync` and creates a `.venv` with the package and its
dependencies.

## Step 2: Start the stack

```bash
make up
```

This starts two services:

- `postgres`, an Alpine Postgres 18 image, published on host port 55432.
- `simulator`, the bundled provider simulator, published on host port 8001.

Postgres has a health check, so the compose stack does not start the
simulator until Postgres is ready.

## Step 3: Create the database

```bash
make migrate
```

This applies the Alembic migrations to the database named in `.env`. The
default `DATABASE_URL` points at the compose Postgres on port 55432.

## Step 4: Collect the data

The simulator supplies the data when the collector asks for it, so no seed
step is needed. The data is reproducible because `SEED` defaults to `42`.

To change the data, set `SEED` in `.env` and restart the simulator:

```bash
# .env
SEED=43
```

```bash
make up
```

## Step 5: Run the control plane

```bash
make run
```

`monitor run` starts the HTTP API on `127.0.0.1:8001`. Check that it is up:

```bash
curl http://127.0.0.1:8001/health
```

A healthy call returns `{"status": "ok", "database": "reachable"}`.

## What to look at next

- `GET /usage`, `GET /cost`, `GET /probes` return the collected rows.
- `GET /alerts?state=firing` returns the alerts raised in the current cycle.
- `GET /metrics` returns the Prometheus digest Grafana reads.

See [First collection cycle](first-collection-cycle.md) for a single cycle
from start to finish.
