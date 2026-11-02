# Debug a probe

A probe failure is stored, not raised. This guide shows how to read what a
probe reported and decide what to do about it.

## What a probe records

`monitor probe` sends one canary request to each provider and stores the
outcome in `probe_result`. The control plane reads it back:

```bash
curl http://127.0.0.1:8001/probes?limit=5
```

Each row carries:

| Column | Meaning |
| --- | --- |
| provider | anthropic or openai |
| probed_at | when the probe ran (RFC 3339) |
| outcome | ok, rate_limited, server_error, overloaded, timeout, auth_error, bad_request, network |
| latency_ms | the measured latency |
| status_code | the HTTP status returned |
| model | the model probed |
| input_tokens / output_tokens | tokens returned by the model |
| attempt_count | how many attempts were made |

## Common outcomes

**ok, low latency.** The provider answered promptly. Nothing to do.

**error, status_code 401 or 403.** The admin key was rejected. With the
simulator any non-empty key passes; with a real key check that the key is
set, unexpired, and scoped to organization administration.

**error, another status.** The provider rejected the request. Check the
base URL, the model, and the endpoint. A probe against a real provider
needs the correct path (`/v1/messages` for Anthropic, `/v1/chat/completions`
for OpenAI).

**timeout.** The request did not return before the timeout. Check the base
URL for a typo, and check for network or load-balancer issues between the
simulator and the collector.

## What to do

1. Confirm the simulator is up: `curl http://127.0.0.1:8001/health`.
2. Read the probe rows and look at `outcome`, `status_code`, and
   `attempt_count`.
3. If the base URL points at the wrong service, fix `.env` and restart the
   collector.
4. Wait for the next cycle and re-read `/probes` to confirm the outcome
   clears.

## Related

- The control-plane reference documents the `/probes` and `/health`
  endpoints.
- The security posture explains how admin keys are handled.
