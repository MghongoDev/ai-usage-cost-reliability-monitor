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

## Status

**Completed (Tracers 01-07, issues #8-#14):**

| Tracer | Title | State |
|--------|-------|-------|
| 01 | Normalized schema and migrations | ✅ Done |
| 02 | Anthropic usage, end to end | ✅ Done |
| 03 | OpenAI usage, end to end | ✅ Done |
| 04 | Key and scope inventory, both providers | ✅ Done |
| 05 | Price table and per-key cost estimation | ✅ Done |
| 06 | Reconciliation and budgets | ✅ Done |
| 07 | Probe runner and availability | ✅ Done |

**In progress (Tracers 08-16, issues #15-#23):**

| Tracer | Title | State |
|--------|-------|-------|
| 08 | SLOs and error-budget burn | 💻 In progress |
| 09 | Scenario injection on the simulator | 💻 In progress |
| 10 | Alert lifecycle plus budget-projection rule | 💻 In progress |
| 11 | Usage-anomaly rule | 💻 In progress |
| 12 | Remaining rules (new entity, absence, SLO burn, governance) | 💻 In progress |
| 13 | Backtest harness | ⏳ Deferred |
| 14 | Grafana provisioning | ⏳ Deferred |
| 15 | Deploy (Render) | ⏳ Deferred |
| 16 | Ops hardening (dumps, keepalive, weekly report, runbooks) | ⏳ Deferred |

## Layout

- `src/monitor/` — the monitor package
- `migrations/` — Alembic migrations
- `docs/` — API research notes, ADRs, agent configuration, Grafana provisioning
- `GLOSSARY.md` — domain vocabulary

## Issue tracker

See the [tracer-bullet plan on GitHub](https://github.com/MghongoDev/ai-usage-cost-reliability-monitor/issues).
