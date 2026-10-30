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
| 01 | Normalized schema and migrations | [x] Done |
| 02 | Anthropic usage, end to end | [x] Done |
| 03 | OpenAI usage, end to end | [x] Done |
| 04 | Key and scope inventory, both providers | [x] Done |
| 05 | Price table and per-key cost estimation | [x] Done |
| 06 | Reconciliation and budgets | [x] Done |
| 07 | Probe runner and availability | [x] Done |

**In progress (Tracers 08-16, issues #15-#23):**

| Tracer | Title | State |
|--------|-------|-------|
| 08 | SLOs and error-budget burn | [x] Done |
| 09 | Scenario injection on the simulator | [x] Done |
| 10 | Alert lifecycle plus budget-projection rule | [x] Done |
| 11 | Usage-anomaly rule | [x] Done |
| 12 | Remaining rules (new entity, absence, SLO burn, governance) | [x] Done |
| 13 | Backtest harness | [x] Done |
| 14 | Grafana provisioning | [x] Done |
| 15 | Deploy (Render) | [x] Done |
| 16 | Ops hardening (dumps, keepalive, weekly report, runbooks) | [x] Done |

**In progress (Tracers 17-23, issues #24-#32):**

| Tracer | Title | State |
|--------|-------|-------|
| 17 | Deployment — GitHub Actions scheduler, Render services, healthchecks, pg_dump, keepalive, weekly report | [in progress] |
| 18 | Phase 6 — CI/CD pipeline, Trivy, complete documentation | [in progress] |
| 19 | CI/CD pipeline — GitHub Actions workflow steps | [in progress] |
| 20 | CI quality gates — ruff, mypy, pytest | [in progress] |
| 21 | Documentation set — API notes, ADR log, glossary, deployment guide, runbooks | [in progress] |
| 22 | Security — dependency map, read-only Grafana role, audit | [in progress] |
| 23 | Alerting — runbooks, Slack sink, alert resolve behavior | [in progress] |
| 24 | Operations — keepalive commit, weekly report, demo mode | [in progress] |
| 25 | Alerting quality — backtest evaluation report, known misses | [in progress] |

## Layout

- `src/monitor/` — the monitor package
- `migrations/` — Alembic migrations
- `docs/` — API research notes, ADRs, agent configuration, Grafana provisioning
- `GLOSSARY.md` — domain vocabulary

## Monitoring cost

The deployed instance runs on Render free tiers and GitHub Actions; the approximate
monthly cost is **$0** (free tier). The README states this because the guide asks
for a rough monthly cost figure.

## Issue tracker

See the [tracer-bullet plan on GitHub](https://github.com/MghongoDev/ai-usage-cost-reliability-monitor/issues).
