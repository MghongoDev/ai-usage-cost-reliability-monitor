# ADR-0002: Deployment architecture — GitHub Actions scheduler + Render free services

Date: 2026-10-30

## Context

The monitor must be deployed on free tiers with the following constraints:

- Render free web services spin down after 15 idle minutes
- Free Postgres expires after 30 days
- Scheduled workflows disable after 60 idle days
- Background workers have no free tier

## Decision

We use a three-part deployment:

1. **GitHub Actions** as the scheduler: a scheduled workflow (every 15 minutes) runs
   collectors, probes, and rules against Postgres. This avoids always-on compute.
2. **Render free web services** for the simulator (always available) and Grafana
   (anonymous read-only). The simulator serves provider-shaped payloads for the
   backtest harness; Grafana provides dashboards.
3. **healthchecks.io** as the dead-man's switch: if the monitor breaks, the
   scheduled workflow stops pinging, triggering an alert.

Nightly pg_dump runs as a CI artifact (Render free Postgres expires after 30 days).
A weekly keepalive commit prevents GitHub's 60-day workflow disable.

## Consequences

- Zero monthly cost for the core pipeline
- No always-on compute required
- Demo mode runs the full stack locally with no vendor keys
- README documents the approximate monthly cost (~$0 on free tiers)
