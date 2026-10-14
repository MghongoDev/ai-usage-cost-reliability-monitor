# AI Usage Monitor

One system that reads the Anthropic and OpenAI admin APIs, stores normalized usage and cost, probes both providers for availability and latency, and raises alerts when spend, usage, or reliability looks wrong.

## Language

**Provider**:
Anthropic or OpenAI. The two vendors whose admin APIs this system reads.
_Avoid_: vendor, platform

**Collector**:
The component that reads one provider's admin API into normalized database rows. It never writes to the provider.
_Avoid_: scraper, importer

**Probe**:
A tiny live request to a provider's message API that measures availability and latency. The admin APIs report neither, which is why probes exist.
_Avoid_: health check, ping, canary

**Scope**:
The organizational unit a vendor groups usage by: an Anthropic workspace or an OpenAI project.
_Avoid_: account, org, team, tenant

**Key**:
A provider API key tracked in the inventory, with an owner, a status, and a last-used date.
_Avoid_: credential, token

**Bucket**:
One row of time-bucketed usage, fixed by a start time and a width of 1 minute, 1 hour, or 1 day.
_Avoid_: interval, bin, datapoint

**Window**:
The time range one collector run re-fetches. Every run re-pulls the trailing 48 hours.
_Avoid_: range, period, span

**Simulator**:
The FastAPI service that mimics both providers' admin and message endpoints and injects the scenarios. It is the system's data source whenever real admin keys are absent.
_Avoid_: mock, fake API

**Scenario**:
A labelled fault the simulator injects, written in `scenarios.yaml` with a start, a duration, and ground truth.
_Avoid_: test case, simulation

**Cycle**:
One full pass of collect, probe, and rule evaluation. Locally a cycle runs every 15 minutes under the scheduler; in the deployed instance a scheduled workflow triggers it.
_Avoid_: run, tick

**Incident**:
The window in generated data where a scenario is active. One scenario can produce many incident windows across a backtest.
_Avoid_: outage, event

**Token class**:
One billing category of tokens: uncached input, cached input, cache creation, or output. Each carries its own price.
_Avoid_: token type

**Fingerprint**:
The rule plus subject identity of an alert. Deduplication, cooldowns, and resolve notices key off it.
_Avoid_: alert id, hash

**Backtest**:
Running the rule engine over simulator data with known ground truth to measure detection delay and false alerts.
_Avoid_: replay, dry run

**Unpriced**:
A model with no row in the price table. Its estimated cost shows as unpriced, never as zero.
_Avoid_: missing price

**Stale**:
A collector whose newest run is older than its expected interval. Stale data counts as unknown, never as zero usage.
_Avoid_: late, missing

**Heartbeat**:
An outbound ping sent on every healthy monitor cycle. An external service alerts when the pings stop.
_Avoid_: watchdog

**Reconciliation**:
Comparing estimated per-scope cost against billed cost, reported as a percentage error.
_Avoid_: audit, cross-check

**SLO**:
The availability target for one provider, measured over a fast window and a slow window.
_Avoid_: uptime goal

**Runbook**:
The document an alert links to, telling an operator what to check and what to do.
_Avoid_: playbook
