## Problem Statement

An organization running AI platforms on Anthropic and OpenAI has no single view of what it spends, how much it uses, or whether the providers are healthy. The billing APIs report usage and cost but not error rates or latency, cost does not break down per API key, and nothing watches whether the monitoring itself is alive. An AI platform engineer needs one dashboard covering spend, usage, and provider health across both vendors, with alerts linked to runbooks when any of those three looks wrong, and proof that the alerts actually work.

## Solution

A self-hosted monitor that pulls usage, cost, and key inventory from both vendors' admin APIs, estimates per-key cost from a versioned price table and reconciles it against billed totals, runs its own canary probes for availability and latency, and raises deduplicated alerts through a rule engine that is backtested against known injected incidents. Because real admin keys are not available, the system runs against a simulator that mimics both providers' admin and message endpoints, including their awkward behaviors (window limits, pagination, null dimensions). The whole thing deploys on free tiers: GitHub Actions as the scheduler, Render for Postgres and Grafana, healthchecks.io as the dead-man's switch.

## User Stories

1. As an AI platform admin, I want one dashboard showing spend, usage, and provider health across Anthropic and OpenAI, so that I don't switch between two vendor consoles.
2. As an AI platform admin, I want a Slack alert (or console alert in demo mode) with a runbook link when spend looks wrong, so that I know what to check and what to do.
3. As an AI platform admin, I want a deduplicated alert when one API key's usage spikes abnormally, so that a runaway loop is caught without a flood of messages.
4. As an AI platform admin, I want alerts when spend is projected to exceed budget, so that I can act before the month closes.
5. As an AI platform admin, I want to know the estimated cost per key and per workspace, so that cost can be attributed even though the vendor's cost report has no per-key breakdown.
6. As an AI platform admin, I want a reconciliation view comparing estimated against billed cost per scope per day, so that I know how far my estimate drifts from the bill and why.
7. As an AI platform admin, I want models missing from the price table to show as unpriced, never as silent zero, so that a pricing gap is visible instead of hidden.
8. As an AI platform admin, I want availability and latency percentiles measured by my own probes, so that I know provider health independently of the billing APIs.
9. As an AI platform admin, I want error-budget burn per provider over a fast and a slow window, so that a slow degradation is caught before it becomes an outage.
10. As an AI platform admin, I want intervals with no probe data counted as unknown, not as 100% available, so that a dead probe doesn't look like a healthy provider.
11. As an AI platform admin, I want an alert when a collector's data goes stale, so that a quiet dashboard is not mistaken for a quiet day.
12. As an AI platform admin, I want an alert when a key that was dormant starts being used, so that unexpected access is caught.
13. As an AI platform admin, I want an alert when a new key or new model appears, so that inventory changes are noticed.
14. As an AI platform admin, I want alerts when a key violates naming or ownership conventions, so that governance rules are enforced without manual audits.
15. As an operator, I want every alert to carry what happened, where (provider, scope, key), how much, since when, a dashboard link, and a runbook link, so that I can act without hunting for context.
16. As an operator, I want alerts to resolve when the condition clears, so that a recovered incident doesn't leave a stale firing alert.
17. As an operator, I want an alert state that survives a worker restart without resending, so that a redeploy doesn't spam me.
18. As an operator, I want to be told when the monitor itself breaks, via an external heartbeat that stops pinging, so that a dead monitor is distinguishable from a quiet system.
19. As a maintainer, I want a backtest table showing, per injected incident, whether it alerted, the detection delay, and which rule caught it, so that the alerting quality is measured, not asserted.
20. As a maintainer, I want thresholds tuned on one simulator seed and results reported on a different seed, so that the backtest isn't graded on the data it was tuned against.
21. As a maintainer, I want a pre-committed false-alert budget on clean data, so that the noise level is judged against a number set before looking.
22. As a maintainer, I want every injected incident to either alert with a measured delay or be documented as a known miss with the rule that would catch it, so that coverage gaps are explicit.
23. As a reviewer of this portfolio project, I want the repo to run end-to-end from a fresh clone with no vendor keys, so that the project is demonstrable without secrets.
24. As a reviewer, I want dashboards provisioned from JSON in git, so that dashboard changes are reviewable in pull requests.
25. As a reviewer, I want the admin client to be read-only by construction, with a test that proves it refuses a POST, so that the credential blast radius is demonstrably controlled.
26. As a reviewer, I want a dependency map listing each integration, its credential, and its privilege level, so that the security posture is legible.
27. As a reviewer, I want the deployed demo reachable at a public URL, so that the dashboard and simulator can be inspected without setup.
28. As a developer, I want backfill and collect commands with idempotent upserts, so that re-running a window produces identical row counts.
29. As a developer, I want every pipeline run re-pulling a trailing window, so that late-arriving and revised billing data is captured.
30. As a developer, I want raw payloads stored with a retention policy, so that schema drift can be investigated after the fact.
30. As a developer, I want unknown response fields counted and logged, not silently dropped, so that provider schema drift is visible.
31. As a developer, I want strict parsing that fails loudly on missing required fields, so that a bad response never poisons the database quietly.
32. As a developer, I want a read-only database role for Grafana, so that a dashboard compromise can't write.
33. As a developer, I want nightly database dumps preserved as CI artifacts, so that the free-tier database's 30-day expiry doesn't lose history.
34. As a developer, I want the weekly keepalive commit, so that GitHub doesn't disable the scheduled workflow after 60 idle days.
35. As a developer, I want a weekly report committed as Markdown, so that the results block stays current without manual work.
36. As a developer, I want a demo that runs the full stack locally in simulator mode, so that development doesn't depend on the deploy.

## Implementation Decisions

**Stack.** Python 3.12 managed by uv. httpx with tenacity for HTTP (official SDKs retry by default, which would hide probe failures). Pydantic v2 for payload parsing. PostgreSQL 18 with Alembic migrations. FastAPI for the simulator. APScheduler inside one worker container for local cycles. Grafana with provisioned dashboards. typer for the CLI. ruff, mypy, pytest, GitHub Actions, Docker Compose, Render, healthchecks.io.

**Local execution.** Docker Compose brings up Postgres and the simulator. The worker runs locally via the CLI. The daemon is available on the dev machine, so the guide's compose-first approach holds locally.

**Deployed execution (see ADR-0001).** Render's free tier cannot run always-on compute, so the scheduler is a GitHub Actions cron workflow (every 15 minutes; free on the now-public repo). The simulator is a second Render free web service, always available. The workflow runs collectors, probes, and rules against Render's free Postgres, then pings healthchecks.io. Grafana is a third free web service, anonymous read-only. Nightly pg_dump runs as a CI artifact (Render free Postgres expires after 30 days). A weekly keepalive commit prevents GitHub's 60-day workflow disable. The weekly report is committed as Markdown.

**Provider clients.** One `UsageSource` interface with `fetch_usage(window)`, `fetch_costs(window)`, and `list_keys()`, implemented once per provider, base URL from config so the same code runs against simulator or real API. The admin client wraps httpx with a `ReadOnlyTransport` that raises on any non-GET/HEAD method, tested directly. Retries with exponential backoff and jitter on 429 and 5xx, honoring Retry-After; timeouts on every call. Pagination and window chunking respect each provider's per-bucket-width bucket limits (both vendors cap buckets per page: Anthropic 1m→1440/24h, 1h→168/7d, 1d→31/31d; OpenAI 1d→31, 1h→168, 1m→1440 for usage, 1d→180 for costs).

**Provider shapes (from docs/api-notes-*.md, researched 2026-10-14).** Anthropic: admin key in `x-api-key` plus `anthropic-version` header; RFC 3339 timestamps; usage report groups by api_key_id among others, with null key for console usage and null workspace for the default workspace; cost report is daily only, grouped by workspace or description, amount as decimal string in lowest units, no per-key breakdown. OpenAI: admin key in `Authorization: Bearer`; Unix-second timestamps; usage endpoints group by project_id, api_key_id, model and more; costs endpoint is daily, grouped by project/line item/api_key_id but carries no token counts. Both are mirrored by the simulator, including the rejection of oversized windows with a 400.

**Schema.** One fact table `usage_fact` keyed by (provider, bucket_start, bucket_width, dims_key) where dims_key is a generated column coalescing scope, key, and model so nullable dimensions survive the primary key; token columns per class including cache creation (split 5m/1h for Anthropic, single cache-write for OpenAI, normalized into one column plus an extra jsonb for provider-specific counters). Also `cost_fact` (daily, per scope and line item, amount USD), `key_inventory` (daily snapshots), `price_table` (model, token class, USD per million, effective_from/effective_to), `budget` (scope, month, USD), `probe_result`, `collector_run`, `alert_event`, and `raw_payload` (provider, endpoint, params, fetched_at, body jsonb, with retention). Upserts are `INSERT ... ON CONFLICT ... DO UPDATE` on the fact table's primary key. Every run re-pulls the trailing 48 hours.

**Pricing and budgets are data, not code.** Prices live in the versioned price table seeded from the researched pricing (recorded in the API notes), never hardcoded in Python. Estimated cost per key and scope derives from usage times price; a model with no price row shows as unpriced in a visible panel. Reconciliation compares estimated against billed per scope per day with a `recon_error_pct` metric; residuals are expected from batch discounts, tiered pricing, priority-tier gaps, and provider rounding.

**Probes.** A dedicated low-privilege key separate from admin keys, tiny canned prompt to the cheapest suitable model, small max_tokens, low frequency with jitter. SDK auto-retries are disabled or the API is called with httpx directly; if a retry happens, the attempt count is recorded. Every outcome is classified (ok, rate_limited, server_error, overloaded, timeout, auth_error, bad_request, network) and stored with latency, status, and tokens. A daily probe-spend cap stops probing and raises an alert when exceeded. Availability views over 1h/24h/30d, latency p50/p95/p99, error mix, and SLO burn rate over a fast and a slow window; no-data intervals count as unknown.

**Rules.** Defined in YAML, implemented as pure functions over database state, unit-testable. Rule types: `sql_threshold` (budget projection, error rate), `robust_z` (usage anomaly, median/MAD score so one past spike doesn't hide the next, evaluated on completed hourly buckets only, against the same hour of week, with a minimum-volume floor), `new_entity` (new key or model), `absence` (collector staleness, dormant key), `slo_burn`. Plus governance rules from inventory: key unused for N days, naming or owner violations. Alert lifecycle: a fingerprint per rule and subject, `for_evaluations` before firing, a cooldown, a resolve notice after the condition clears for several evaluations, and reminders at an interval; state persists in `alert_event` so a restart doesn't resend.

**Alerting sinks.** Console sink for tests and the deployed demo; Slack webhook path implemented and tested against a recorded fixture but unconfigured (the URL, when set, lives only in a GitHub Actions secret). Each message states what happened, where, how much, since when, a dashboard link, and the runbook link.

**Simulator.** FastAPI with a fixed seed, generating usage with daily and weekly rhythms across a few workspaces, keys, and models, serving provider-shaped payloads from `/anthropic/...` and `/openai/...`. It behaves like the real APIs on the awkward parts: fake admin key required, oversized windows rejected with 400, pagination when results exceed the limit, empty buckets for idle intervals, null key for console usage, and a message endpoint per provider with injectable latency, 429s, and 5xx errors driven by `scenarios.yaml`.

**Scenarios.** Seven labelled incidents in `scenarios.yaml`, each with start, duration, and ground truth: runaway loop on one key (~10x tokens for a few hours), new model appearing on a key, slow drift upward (~1.5x over two weeks), provider outage window (probe 5xx and timeouts), collector outage (stale data), usage from a dormant key, and a cache-hit collapse after a prompt change.

**Backtest harness.** Runs each scenario through the engine, plus 30 clean days, recording per incident whether it alerted, detection delay, and which rule caught it. Thresholds tune on one seed; results report on a different seed. The table lands in `docs/alert-eval.md`. Every incident either alerts with a measured delay or is documented as a known miss with the rule that would catch it. The false-alert count on the clean period must fall within a budget committed before looking.

**Deployed alert quality.** Because the deployed instance runs on free tiers, detection delay in the deployed demo is bounded by cycle cadence; the backtest table is the honest measurement of alert quality, produced locally at fine granularity.

## Testing Decisions

A good test exercises external behavior only: the alert table a scenario produces, the rows a collect cycle writes, the refusal of a read-only client, never internal function calls or private state.

**Primary seam: the backtest harness.** Given `scenarios.yaml` and a fresh database, the full pipeline (simulator, collectors, probes, rules) produces a specific alert table with measured detection delays, and 30 clean days produce at most the pre-committed number of false alerts. This one seam covers simulator fidelity, collector correctness, normalization, pricing, probe classification, rule firing, deduplication, and resolve behavior, because every one of those shows up in the alert table or it doesn't work.

**Secondary seam: pure-function unit tests.** Normalization (provider payload to rows, against fixtures), robust_z (including the flat-history and no-data cases), availability math (including unknown intervals and 429-versus-5xx classification), window chunking (limits respected), read-only transport (POST refused), price lookup with effective dates, and the probe budget cap. These are cheap, deterministic, and the guide's checkpoints demand them.

**Prior art.** None in this repo yet; this is the first test suite. The backtest harness doubles as the integration test the CI job needs (full collect cycle plus alert dry run against Postgres and the simulator).

## Out of Scope

Request-level telemetry through a gateway or proxy. A third provider. Auto-remediation (disabling keys). A custom UI beyond Grafana. ML anomaly models. SSO. A Databricks port. Real vendor admin keys and any real usage data (simulator-first by assumption; the README will state exactly which parts were validated against real APIs). Terraform. The demo video. Alerting on the Render free Postgres 30-day expiry itself.

## Further Notes

- The research pass (Q12) is done: both vendors' admin APIs are documented in `docs/api-notes-anthropic.md` and `docs/api-notes-openai.md`, including pricing tables and the explicit "what each response does NOT contain" lists. The per-key cost gap is confirmed for both vendors: cost reports don't break down per key, so estimation plus reconciliation is the design, not a workaround.
- Two build-time schema refinements, flagged rather than silent: `usage_fact` gains a `cache_creation` column (the guide's DDL omits it, but Phase 3 prices cache writes), and `probe_result`, `collector_run`, and `raw_payload` use identity primary keys where the guide's natural keys are shaky.
- The deployed instance's constraints are recorded in ADR-0001: free web services spin down after 15 idle minutes, background workers have no free tier, free Postgres expires after 30 days, and scheduled workflows disable after 60 idle days. The keepalive and pg_dump artifacts exist because of that list.
- Stopping line for this build: through Phase 5 including the backtest table. Phase 6 (full CI/CD polish, Trivy, complete doc set) follows once the core works.
- The monitor's own running cost is roughly $0 on free tiers; the guide asks for a rough monthly cost figure in the README, which will say so.
