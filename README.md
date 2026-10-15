# AI Usage, Cost, and Reliability Monitor

A self-hosted monitor for an organization's AI platforms. It pulls usage, cost, and key inventory from the Anthropic and OpenAI admin APIs, runs its own canary probes to measure availability and latency (which the billing APIs don't report), attributes cost down to the API-key level, and alerts when spend, usage, or reliability looks wrong, with every alert linked to a runbook.

**Simulator-first.** No vendor admin keys are required. A bundled simulator mimics both providers' admin and message endpoints, including their awkward behaviors, so the whole system runs from a fresh clone.

## Quick start

```bash
make install     # uv sync
make up          # Postgres via docker compose
make migrate     # alembic upgrade head
```

The simulator, collectors, and dashboards are under construction; see the
issue tracker for the tracer-bullet plan.

## Layout

- `src/monitor/` — the monitor package
- `migrations/` — Alembic migrations
- `docs/` — API research notes, ADRs, agent configuration
- `GLOSSARY.md` — domain vocabulary

## Status

Under construction. See the issue tracker for the tracer-bullet plan.
