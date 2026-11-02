# Security posture

The monitor handles admin keys for two AI platforms and stores normalized
data, profiles, and alerts. This page describes the controls and the open
wiring points.

## Keys

- Admin keys are only needed for the admin-scoped API endpoints the
  collector calls.
- Keys are held in environment variables and in the `.env` file, which is
  gitignored. The deployed instance reads them from GitHub Actions
  repository secrets.
- With the simulator any non-empty key passes the auth check, so a fresh
  clone can run without keys.

## Network

- The control plane binds to `127.0.0.1` by default and is meant to be
  read only by Grafana and the weekly report locally.
- The GitHub Actions jobs run on `ubuntu-latest` and reach the database on
  a service container named `postgres` on port 5432.
- Grafana is read-only for anonymous users and is served by a free Render
  service.

## Data

- The `raw_payload` table keeps the raw API bodies for schema-drift
  investigation. Retention is a policy decision, not a table default.
- The `alert_event` table is indexed on fingerprint and state for fast
  reads.

## Credential hygiene

- All secrets are GitHub Actions repository secrets, referenced via
  `${{ secrets.X }}` in the workflow YAML.
- No secrets are committed to git. The `.env` file is gitignored.
- Admin keys are created on the provider console, imported into GitHub
  Actions secrets, and never stored in the repo.
- The collector wraps the admin key in a read-only transport that raises
  on any non-GET or non-HEAD method.

## Open wiring points

- `SLACK_WEBHOOK_URL` and `HEALTHCHECKS_PING_URL` are defined in
  `config.py` but no code reads them yet. The scheduler pings
  healthchecks through the repository secret `HEALTHCHECKS_IO_URL` in the
  notify job.
