# Configuration reference

The monitor reads its settings from the environment, in
`src/monitor/config.py`, which loads a `.env` file when present. Copy
`.env.example` to `.env` before your first `make up` and edit the values.

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| DATABASE_URL | `postgresql://monitor:***@localhost:55432/monitor` | Postgres connection string. Local runs use the compose Postgres; deployed runs use the Render connection string. |
| ANTHROPIC_BASE_URL | `http://localhost:8001/anthropic` | Base URL for the Anthropic provider or simulator. |
| OPENAI_BASE_URL | `http://localhost:8001/openai` | Base URL for the OpenAI provider or simulator. |
| ANTHROPIC_ADMIN_KEY | (empty) | Admin key for Anthropic. The simulator ignores it; a real run sets it. |
| OPENAI_ADMIN_KEY | (empty) | Admin key for OpenAI. |
| SLACK_WEBHOOK_URL | (empty) | Where alerts are posted. Defined but not yet wired to a sink. |
| HEALTHCHECKS_PING_URL | (empty) | Dead-man's switch ping URL. Defined but not yet wired to a sink. |
| SEED | 42 | Simulator seed, so generated data is reproducible. |

## Environment file

- Copy `.env.example` to `.env` before your first `make up`.
- `.env` is gitignored. Never commit real keys.
- The deployed instance gets its secrets from GitHub Actions repository
  secrets; the workflow sets `DATABASE_URL`, `SIMULATOR_URL`, and
  `HEALTHCHECKS_IO_URL` for the jobs.

## Where the settings are used

- The collector, probe, and rules commands use `DATABASE_URL`,
  `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`, and the two admin keys.
- The scheduler's notify job pings healthchecks via the repository secret
  `HEALTHCHECKS_IO_URL` (`/ok` on success, `/fail` on failure). The
  `HEALTHCHECKS_PING_URL` config setting is defined but not consumed by
  monitor code yet.
- The slack webhook (`SLACK_WEBHOOK_URL`) and healthchecks (`HEALTHCHECKS_PING_URL`)
  fields are configured but currently unread by monitor code; they are wiring
  points for a future sink.

## Related

- Build and entrypoints are declared in the Makefile and pyproject.toml;
  the `monitor` CLI subcommand runs the collector, probe, rules, and
  control plane.
