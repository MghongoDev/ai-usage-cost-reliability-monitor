# Security — dependency map, read-only Grafana role, audit

Date: 2026-10-30

## Dependency map

| Integration | Credential | Privilege level | Direction |
|------------|------------|----------------|-----------|
| Anthropic admin API | `ANTHROPIC_ADMIN_KEY` (GitHub Actions secret) | Read-only (admin key, ReadOnlyTransport) | Collector → Provider |
| OpenAI admin API | `OPENAI_ADMIN_KEY` (GitHub Actions secret) | Read-only (admin key, ReadOnlyTransport) | Collector → Provider |
| Render Postgres | `POSTGRES_URL` (GitHub Actions secret) | Read-write (app role) for collector; read-only (grafana role) for dashboards | App → Database |
| Grafana read-only DB role | Database user with SELECT only | Read-only | Grafana → Database |
| healthchecks.io | `HEALTHCHECKS_IO_URL` (GitHub Actions secret) | Unauthenticated HTTP | App → External |
| Simulator (Render) | No credentials (internal service) | Internal | Workflow → Simulator |

## Privilege model

- **Admin keys** (Anthropic, OpenAI): wrapped with `ReadOnlyTransport` that
  raises on any non-GET/HEAD method. The collector can never issue a write.
  Tested in `tests/test_readonly_transport.py`.
- **Database**: collector uses a read-write role; Grafana uses a separate
  read-only role so a dashboard compromise cannot write to the database.
  See `migrations/versions/0003_grafana_readonly_role.py`.
- **Secrets**: stored in GitHub Actions repository secrets (GitHub Secrets
  feature). Never committed to git. The `.env` file is gitignored.

## Credential hygiene

- All secrets are GitHub Actions repository secrets, accessed via
  `${{ secrets.X }}` in workflow YAML.
- No secrets are committed to git. The `.env` file is gitignored and
  never committed.
- Admin keys are created on the provider console and imported into
  GitHub Actions secrets only. They are never stored in the repo.
- The Grafana read-only role has no write privileges by design.
