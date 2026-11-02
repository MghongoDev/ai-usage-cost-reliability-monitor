# AI Usage, Cost, and Reliability Monitor

A self-hosted monitor for an organization's AI platforms. It pulls usage, cost,
and key inventory from the Anthropic and OpenAI admin APIs, runs its own canary
probes to measure availability and latency, attributes cost down to the API-key
level, and raises alerts when spend, usage, or reliability looks wrong. Each
alert links to a runbook.

**Simulator-first.** No vendor admin keys are required. A bundled simulator
imitates both providers' admin and usage endpoints, including their awkward
behaviors, so the system runs from a fresh clone.

## Quick start

```bash
make install     # uv sync
make up          # Postgres via docker compose
make migrate     # alembic upgrade head
```

Then run the loop end to end:

```bash
make demo        # up, migrate, collect, run the control plane
```

`make demo` serves the HTTP control plane on `http://127.0.0.1:8001`. See the
[Quick start](docs/tutorials/quickstart.md) tutorial for a step-by-step
walkthrough, and [First collection cycle](docs/tutorials/first-collection-cycle.md)
for a working example.

## What it does

| Concern | Source |
| --- | --- |
| Usage and token counts | Anthropic / OpenAI usage reports |
| Cost, in USD | Anthropic / OpenAI cost reports |
| Key and scope inventory | Admin API key and workspace listings |
| Availability and latency | Canary probes against each provider |
| Per-key cost estimate | Usage x the price table, reconciled against cost reports |
| Alerts on spend, usage, or reliability | Rule set evaluated on a rolling window |

## Architecture

- `src/monitor/` — the monitor package: CLI, database, collectors, probes, rules,
  and the HTTP control plane.
- `src/monitor/simulator/` — the bundled provider simulator.
- `migrations/` — Alembic migrations for the database schema.
- `docs/` — this documentation set (tutorials, how-to guides, reference, explanation).
- `GLOSSARY.md` — domain vocabulary.

The GitHub Actions scheduler runs `collect`, `probe`, and `rules` on a cron. A
separate free Render service hosts Grafana and reads the control plane. The
scheduler also pings a dead-man's switch when a cycle completes without error.

## Configuration

Copy `.env.example` to `.env` and edit the values. The fields that matter most:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Postgres connection string | `postgresql://monitor:***@localhost:55432/monitor` |
| `ANTHROPIC_ADMIN_KEY` / `OPENAI_ADMIN_KEY` | Admin keys; the simulator ignores them | empty |
| `SLACK_WEBHOOK_URL` | Where alerts are posted; empty means the console sink | empty |
| `HEALTHCHECKS_PING_URL` | Dead-man's switch ping URL | empty |
| `SEED` | Simulator seed for reproducible data | `42` |

See [Configuration reference](docs/reference/config.md) for the full list and the
environment file.

## Project status

Tracers 01 through 32 and Phase 1 through 6 are complete. The tracker's only open
item is issue #1 (Spec), the originating spec for the monitor's control-plane
HTTP API. See the
[tracer-bullet plan on GitHub](https://github.com/MghongoDev/ai-usage-cost-reliability-monitor/issues).

## Monitoring cost

The deployed instance runs on Render free tiers and GitHub Actions, so the
approximate monthly cost is $0.
