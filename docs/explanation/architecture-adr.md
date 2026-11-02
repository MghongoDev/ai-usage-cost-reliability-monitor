# Architecture decision records

The deployment and data flow are governed by the ADRs below.

## ADR 0001: GitHub Actions cron drives collection, Render serves Grafana

- Source: `docs/adr/0001-gh-actions-cron-render-grafana.md`

GitHub Actions is the scheduler and CI runner. A cron workflow runs every
15 minutes and executes `collect`, `probe`, and `rules` as separate jobs,
each against a service container running PostgreSQL. A separate free Render
service runs Grafana and reads the control plane.

The extra cost is the database and network hops per cycle.

## ADR 0002: Deployment architecture

- Source: `docs/adr/0002-deployment-architecture.md`

The system is split into two free-service tiers: GitHub Actions for the
scheduler, Render for Grafana. The database is a Postgres 18 container
started by compose locally and a managed Postgres on Render for Grafana.

The database stays in the workflow container so the cycle is fast and the
blast radius is small. Grafana runs where it is read, not where the data is
written.

## Index

| ADR | Decision |
| --- | --- |
| 0001 | GitHub Actions cron drives collection; Render serves Grafana |
| 0002 | Deployment architecture: GitHub Actions scheduler + Render free services |

## Related

- The README describes the components at a glance.
- The control-plane reference documents the HTTP API Grafana reads.
