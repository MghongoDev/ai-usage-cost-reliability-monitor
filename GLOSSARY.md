# AI Usage Monitor

One system that reads the Anthropic and OpenAI admin APIs, stores normalized
usage and cost, probes both providers for availability and latency, and raises
alerts when spend, usage, or reliability looks wrong.

## Words to use

**Collector**
The component that reads one provider's admin API into normalized database
rows. It never writes to the provider.

**Probe**
A tiny live request to a provider's message API that measures availability and
latency. The admin APIs report neither, which is why probes exist.

**Scope**
The organizational unit a vendor groups usage by: an Anthropic workspace or an
OpenAI project.

**Key**
A provider API key tracked in the inventory, with an owner, a status, and a
last-used date. Do not call it a credential or a token.

**Bucket**
One row of time-bucketed usage, fixed by a start time and a width of 1 minute,
1 hour, or 1 day.

**Window**
The time range one collector run re-fetches. Every run re-pulls the trailing
two days.

**Simulator**
The FastAPI service that mimics both providers' admin and message endpoints and
injects the scenarios. It is the system's data source whenever real admin keys
are absent. Do not call it a mock or a fake API.

**Scenario**
A labelled fault the simulator injects, written in `scenarios.yaml` with a
start, a duration, and ground truth. Do not call it a test case or a
simulation.

**Cycle**
One full pass of collect, probe, and rule evaluation. Locally a cycle runs
every 15 minutes under the scheduler; in the deployed instance a scheduled
workflow triggers it.

**Incident**
The window in generated data where a scenario is active. One scenario can
produce many incident windows across a backtest. Do not call it an outage or
an event.

**Token class**
One billing category of tokens: uncached input, cached input, cache creation,
or output. Each carries its own price.

**Fingerprint**
The rule plus subject identity of an alert. Deduplication, cooldowns, and
resolve notices key off it. Do not call it an alert id or a hash.

**Backtest**
Running the rule engine over simulator data with known ground truth to measure
detection delay and false alerts. Do not call it a replay or a dry run.

**Unpriced**
A model with no row in the price table. Its estimated cost shows as unpriced,
never as zero.

**Stale**
A collector whose newest run is older than its expected interval. Stale data
counts as unknown, never as zero usage.

**Heartbeat**
An outbound ping sent on every healthy monitor cycle. An external service
alerts when the pings stop. Do not call it a watchdog.

**Reconciliation**
Comparing estimated per-scope cost against billed cost, reported as a
percentage error. Do not call it an audit or a cross-check.

**SLO**
The availability target for one provider, measured over a fast window and a
slow window. Do not call it an uptime goal.

**Runbook**
The document an alert links to, telling an operator what to check and what to
do. Do not call it a playbook.

**Control plane**
The HTTP API that serves collected data, probes, and metrics. It is a
separate process from the collectors and is what Grafana and the weekly report
read. Do not call it the UI or an endpoint.

**Digest**
The Prometheus text emitted at GET /metrics. Do not call it a metrics page or
a summary.

**Alert state**
Open alerts are `firing`; resolved alerts are `resolved`. Do not call it
open/closed or active/inactive.

**Rule**
A named condition evaluated over recent state that can fire an alert. Do not
call it a check, a test, or a monitor.

**Dataset**
A named slice of a table served by the control plane (`usage`, `cost`,
`inventory`, `probes`, `slo`, `alerts`). Do not call it an endpoint or a
route.

**Runner**
The component that executes one probe and returns the raw outcome. Do not
call it a worker or a job.
