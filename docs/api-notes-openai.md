# OpenAI Admin APIs — Usage, Costs, Project/Key Inventory (research notes)

Research date: 2026-10-14
Sources (all official OpenAI docs):
- Administration API reference: https://developers.openai.com/api/reference/administration/overview (mirror: https://platform.openai.com/docs/api-reference/administration)
- Admin APIs guide: https://developers.openai.com/api/docs/guides/admin-apis
- Usage/Costs reference: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage
- Cookbook "How to use the Usage API and Cost API to monitor your OpenAI usage": https://developers.openai.com/cookbook/examples/completions_usage_api (also at github.com/openai/openai-cookbook/examples/completions_usage_api.ipynb)
- Pricing: https://developers.openai.com/api/docs/pricing.md (mirror https://platform.openai.com/docs/pricing/)
- Rate limits: https://developers.openai.com/api/docs/guides/rate-limits

Notes on doc accessibility: `platform.openai.com/docs/...` HTML pages resolve to short stubs; the
richer, machine-readable versions live on `developers.openai.com` (append `.md` to a URL for the
markdown version). No login walls were hit for anything above. `platform.openai.com/login` (the
dashboard itself) is not accessible and was not needed.

---

## 0. Shared conventions

### Base URL
```
https://api.openai.com/v1
```

### Auth header (all endpoints in this document)
```
Authorization: Bearer $OPENAI_ADMIN_KEY
```
Plus `Content-Type: application/json` on every documented curl example (harmless/no-op on GETs).

- Requires an **Admin API key** created at `https://platform.openai.com/settings/organization/admin-keys`.
- Docs state explicitly: "Admin API keys cannot be used for non-administration endpoints", and
  conversely a normal project API key cannot call these (the ellmer wrapper docs, a third party,
  confirm the same: "This endpoint requires an OpenAI Organization Admin API key. It does not accept
  the ordinary project API key used for model requests.").
- Admin keys are created with **scoped permissions** (help.openai.com article 9687866). Some
  Groups/Roles endpoints need scopes outside "Organization Administration"; a missing scope yields a
  missing-scope error. UNVERIFIED: the exact scope strings required for the usage/costs endpoints.
- Admin keys carry the `sk-admin-...` prefix shape (see `redacted_value` in list responses).

### Timestamps
All times are **Unix seconds** (integer). Every endpoint in the Usage/Costs family takes
`start_time` (required, inclusive) and `end_time` (optional, exclusive). The cookbook converts with
`pd.to_datetime(x, unit='s')`. Nothing in these APIs accepts ISO-8601 or milliseconds.

### Two distinct pagination styles (do not mix them up)

**(A) Usage/Costs "page" style** — `/organization/usage/*` and `/organization/costs`:
- Query param `page` = opaque cursor, taken from the previous response's `next_page`.
- Response envelope: `{ "object": "page", "data": [...], "has_more": bool, "next_page": string|null }`.
- `limit` means **number of buckets** per page (not records).
- Cookbook loop: `while True: page_cursor = json.get("next_page"); if not page_cursor: break`.
- Example cursor from docs: `"next_page": "page_AAAAAGdGxdEiJdKOAAAAAGcqsYA="`.

**(B) Inventory "list" style** — `/organization/projects`, `.../api_keys`, `/organization/admin_api_keys`:
- Query param `after` = an object ID (e.g. `proj_abc`, `key_abc`), not an opaque cursor.
- Response envelope: `{ "object": "list", "data": [...], "has_more": bool, "first_id": ..., "last_id": ... }`.
- `limit` means **number of objects**, range 1–100, default 20.
- Some of these also accept `order: "asc" | "desc"` (creation time).

### Documented rate limits for these Admin endpoints
**None published.** The rate-limits guide (developers.openai.com/api/docs/guides/rate-limits)
documents RPM/TPM/RPD/TPD/IPM for *model-serving* requests, defined at organization and project
level, varying by model, with `x-ratelimit-*` response headers. It says nothing about the
Administration/Usage/Costs endpoints. **UNVERIFIED — do not invent a number; treat admin API
throttling as undocumented and back off conservatively.** Practical note: pagination is the real
constraint (see per-endpoint `limit` maxima).

### How far back / how wide a single request may be
What OpenAI actually documents is a **per-page bucket count**, not a calendar span:
- `bucket_width=1d`: default 7 buckets/page, **max 31** → ≈31 days/page
- `bucket_width=1h`: default 24, **max 168** → ≈7 days/page
- `bucket_width=1m`: default 60, **max 1440** → ≈1 day/page
- Costs (`1d` only): default 7, **max 180** → ≈180 days/page

Any longer range must be fetched by following `next_page` (which is exactly what the cookbook does
for 30 days at `limit=7`). **UNVERIFIED: OpenAI publishes no "max time span per request" or
"retention horizon" for these endpoints.** (A third-party gateway, stdapi.ai, advertises "1m buckets
for 15 days, 1h and 1d for 455 days" and a 92-day max range — that is *their* product's config, NOT
OpenAI's documented behaviour. Do not cite it as OpenAI policy.)

Also unverified/undocumented: data freshness/latency for the current day (the docs are silent;
Anthropic's analogous cookbook warns "designed for historical analysis, not real-time monitoring" —
do not assume that applies to OpenAI).

---

## 1. GET /organization/usage/completions — Completions usage

The flagship endpoint. Covers chat/responses/completions/messages/realtime token usage.

**Query parameters**
| Param | Req | Type | Notes |
|---|---|---|---|
| `start_time` | **yes** | int | Unix seconds, inclusive |
| `end_time` | no | int | Unix seconds, **exclusive** |
| `bucket_width` | no | `"1m"` \| `"1h"` \| `"1d"` | default `1d` |
| `limit` | no | int | buckets/page: 1d→7 (max 31), 1h→24 (max 168), 1m→60 (max 1440) |
| `group_by` | no | array | `project_id`, `user_id`, `api_key_id`, `model`, `batch`, `service_tier`, `api_source` — any combination |
| `project_ids` | no | array[string] | filter |
| `user_ids` | no | array[string] | filter |
| `api_key_ids` | no | array[string] | filter |
| `models` | no | array[string] | filter |
| `batch` | no | bool | `true`=batch only, `false`=non-batch only, omitted=both |
| `page` | no | string | cursor from previous `next_page` |

**`api_source`**: `agents_api` for attributed Agents API activity, `unlabeled` for everything else;
`null` when not grouping by it.

**Response** — `object:"page"`, `data[]` of buckets `{object:"bucket", start_time, end_time, results[]}`.
Result object `"organization.usage.completions.result"`:
- `input_tokens` — aggregated input tokens **including cached and cache-write tokens** (text+audio+image; includes Scale Tier tokens)
- `output_tokens` — output tokens across text/audio/image outputs
- `input_cached_tokens` — cached input tokens (text, audio, image)
- `input_cache_write_tokens` — tokens written to cache
- `input_uncached_tokens` — uncached input tokens **excluding cache-write tokens**
- `input_text_tokens` / `input_audio_tokens` / `input_image_tokens` — uncached per modality
- `input_cached_text_tokens` / `input_cached_audio_tokens` / `input_cached_image_tokens`
- `output_text_tokens` / `output_audio_tokens` / `output_image_tokens`
- `num_model_requests`
- Grouping echo fields, `null` unless requested: `project_id`, `user_id`, `api_key_id`, `model`, `batch`, `service_tier`, `api_source`

**Response does NOT contain:**
- Any dollar amount / price / cost field. (Costs live only in `/organization/costs`.)
- Per-request records, prompts, request IDs, timestamps finer than the bucket, or latency/error data.
- `organization_id` (despite appearing in older cookbook *cost* output).
- Batch vs non-batch split unless you group/filter on `batch`.
- Service tier unless grouped by `service_tier`.
- API key *names* — only opaque `api_key_id` (`key_...`).
- Non-request metrics (vector-store bytes, image counts, characters, minutes).
- Cache-write vs cache-read cost distinction — only token counts; cache-write tokens are folded into `input_tokens`.
- Image *output* tokens are inside `output_tokens` but there is no per-image price to apply from here.
- Fine-tuned vs base distinction (fine-tunes appear as `ft:gpt-4o-2024-08-06:org:tag` in `model`).
- Empty buckets are still returned with `"results": []` — treat as zero, not missing.

---

## 2. GET /organization/costs — Costs (billed amounts)

**Query parameters**
| Param | Req | Type | Notes |
|---|---|---|---|
| `start_time` | **yes** | int | Unix seconds, inclusive |
| `end_time` | no | int | Unix seconds, exclusive |
| `bucket_width` | no | `"1d"` **only** | "Currently only `1d` is supported, default to `1d`" |
| `limit` | no | int | buckets/page, 1–180, default 7 |
| `group_by` | no | array | `project_id`, `user_id`, `line_item`, `api_key_id`, `api_source` |
| `project_ids` | no | array[string] | |
| `api_key_ids` | no | array[string] | |
| `line_items` | no | array[string] | **exact full match**, e.g. `"gpt-6-astra, input_tokens"` |
| `page` | no | string | cursor |

**Combination restrictions (documented):** combining `user_id` with `project_id` grouping, or the
`project_ids` filter, "depends on the organization and requested time range. Unsupported
combinations return HTTP 400."

**Response** — `object:"page"`, buckets, result object `"organization.costs.result"`:
- `amount`: `{ "value": number, "currency": "usd" }` (lowercase ISO-4217; docs example shows `usd`)
- `line_item` (when grouped) — e.g. `gpt-6-astra, input_tokens`
- `quantity` (when grouped by `line_item`)
- `project_id`, `api_key_id` (when grouped)
- Older cookbook output also shows `organization_id` on the result object — **UNVERIFIED whether
  that field is current; it is absent from the present reference schema.**

**Response does NOT contain:**
- Token counts. There is **no `input_tokens`/`output_tokens`** here — that is the whole reason you
  must reconcile `/usage/completions` (tokens) against `/costs` (dollars) yourself.
- Model name as a standalone field (model is embedded inside `line_item` strings only).
- `model` grouping support (not in the `group_by` enum for costs).
- Cached-vs-uncached split at the line-item level is only whatever OpenAI's line items happen to be;
  the API does not expose a schema for them. **UNVERIFIED: the full list of possible `line_item`
  values** — only the two examples `gpt-6-astra, input_tokens` and the general `"<model>, <class>"`
  shape are documented.
- Sub-daily granularity (daily buckets only).
- Remaining prepaid credit / balance. (Third-party docs: "OpenAI does not currently document an API
  endpoint for remaining prepaid credit. That balance remains available in the organization Billing
  page." Consistent with the official reference — no such endpoint exists.)
- Credits, refunds, taxes, discounts, or invoice-level items (unless they surface as line items — unverified).
- Any estimate — `amount` is "the amount charged", not derived from token counts.

---

## 3. Other Usage endpoints (same page/bucket conventions)

All: `start_time` required, `end_time` optional, `page` cursor pagination, `limit` = buckets with the
same 1d/1h/1m defaults and maxima (31/168/1440) where bucket_width is accepted.

| Endpoint | `bucket_width` | `group_by` | Extra query params | Result object | Key metric |
|---|---|---|---|---|---|
| `/organization/usage/embeddings` | 1m/1h/1d | `project_id`, `user_id`, `api_key_id`, `model` | `project_ids`, `user_ids`, `api_key_ids`, `models` | `organization.usage.embeddings.result` | `input_tokens`, `num_model_requests` |
| `/organization/usage/moderations` | 1m/1h/1d | `project_id`, `user_id`, `api_key_id`, `model` | same as embeddings | `organization.usage.moderations.result` | `input_tokens`, `num_model_requests` |
| `/organization/usage/images` | 1m/1h/1d | `project_id`, `user_id`, `api_key_id`, `model`, `size`, `source` | `project_ids`, `user_ids`, `api_key_ids`, `models` | `organization.usage.images.result` | `images`, `num_model_requests`; `source` ∈ `image.generation`/`image.edit`/`image.variation` |
| `/organization/usage/audio_speeches` | 1m/1h/1d | `project_id`, `user_id`, `api_key_id`, `model` | `project_ids`, `user_ids`, `api_key_ids`, `models` | `organization.usage.audio_speeches.result` | `characters`, `num_model_requests` |
| `/organization/usage/audio_transcriptions` | 1m/1h/1d | `project_id`, `user_id`, `api_key_id`, `model` | same as speeches | `organization.usage.audio_transcriptions.result` | `seconds`, `num_model_requests` |
| `/organization/usage/vector_stores` | 1m/1h/1d | `project_id` **only** | `project_ids` | `organization.usage.vector_stores.result` | `usage_bytes` (bytes, not tokens). No `api_key_ids`/`user_ids`/`models` params. |
| `/organization/usage/code_interpreter_sessions` | not shown on the page extracted | `project_id` only (per response shape) | `project_ids` | `organization.usage.code_interpreter_sessions.result` | `num_sessions` |
| `/organization/usage/file_search_calls` | not shown | `project_id`, `user_id`, `api_key_id`, `vector_store_id` (per response shape) | — | `organization.usage.file_searches.result` | `num_requests` (file search calls) |
| `/organization/usage/web_search_calls` | not shown | `project_id`, `user_id`, `api_key_id`, `model`, `context_level`, `api_source` (per response shape) | — | `organization.usage.web_searches.result` | `num_requests` (web search calls) + `num_model_requests` |

**UNVERIFIED / gaps for the last four rows:** the reference pages for `code_interpreter_sessions`,
`file_search_calls`, `web_search_calls`, `vector_stores` rendered only partially through the
extractor (nav chrome + example responses, no parameter table), and the `.md` variants returned
CRAWL_NOT_FOUND. Bucket widths for those four are assumed to follow the shared 1m/1h/1d pattern
(`vector_stores` explicitly lists 1m/1h/1d), but confirm before relying on them. Also note the
`file_search_calls` response `object` string is `...file_searches.result` (plural) — a mismatch with
the endpoint name; and per third-party docs there is **no `models` filter** on `file_search_calls`.

**These endpoints do NOT contain** (any of them): costs, per-request detail, sub-bucket timestamps,
API key names, or any cross-endpoint aggregate. Each is a separate query; totals must be summed
client-side. `/usage/completions` covers several product surfaces at once, so beware double counting
(e.g. `web_search_calls` reports its own `num_model_requests`).

---

## 4. Inventory endpoints

### 4.1 GET /organization/projects — List projects
| Param | Req | Notes |
|---|---|---|
| `after` | no | object ID cursor (`proj_...`) |
| `limit` | no | 1–100, default 20 |
| `include_archived` | no | bool; archived projects **excluded by default** |

Response `object:"list"`, `data[]` of `organization.project`:
`id`, `created_at` (unix sec), `object`, `name` ("appears in reporting"), `status`
(`active`|`archived`), `archived_at`, `external_key_id`, plus `has_more`, `first_id`, `last_id`.

**Does NOT contain:** spend/budget, usage, member list, rate limits, model permissions, or
certificates (those are separate sub-resources), nor any cost figure. Project names are the only
human-readable label you get — map `project_id` → `name` from here to make usage/cost reports
readable.

Related sub-resources under `/organization/projects/{project_id}`: `users`, `service_accounts`,
`api_keys`, `rate_limits`, `groups`, `model_permissions`, `certificates`, `spend_alerts`,
`data_retention`.

### 4.2 GET /organization/projects/{project_id}/api_keys — List project API keys
| Param | Req | Notes |
|---|---|---|
| `project_id` | **path** | |
| `after` | no | object ID cursor |
| `limit` | no | 1–100, default 20 |
| `owner_project_access` | no | `active` \| `inactive` \| `any`. Omitted → "existing membership-based visibility rules, which may exclude some enabled keys." |

Response `object:"list"` of `organization.project.api_key`:
`id`, `created_at` (unix sec), `last_used_at` (unix sec or null), `name`, `object`,
`owner` (`{type: "user"|"service_account", user{id,email,name,role} | service_account{id,name,role}}`),
`owner_project_access` (`active`|`inactive`), `redacted_value`, `expires_at` (unix sec or null).

**Does NOT contain:** the key's secret value (only `redacted_value`), its scopes/permissions, its
associated spend, or its usage. Note `last_used_at` is present here — useful for orphan detection,
but it is the *only* freshness signal. There is **no single "list all API keys across all projects"**
endpoint other than `admin_api_keys` (below), which lists admin keys; per-project keys require one
call per project.

### 4.3 GET /organization/admin_api_keys — List all organization and project API keys
(Despite the SDK label "List all organization and project API keys", the reference title is
"List organization API keys" — see the UNVERIFIED note.)

| Param | Req | Notes |
|---|---|---|
| `after` | no | key ID cursor |
| `limit` | no | max keys to return (no range stated) |
| `order` | no | `asc` \| `desc` by creation time |

Response `object:"list"` of `organization.admin_api_key`:
`id`, `created_at`, `expires_at` (or null), `object`, `owner` (`{type, object, id, name, role:"owner"}`),
`redacted_value` (e.g. `"sk-admin...def"`), `last_used_at` (or null), `name`; plus `has_more`,
`first_id`, `last_id`.

**UNVERIFIED:** whether this endpoint also returns *project* (non-admin) API keys — the SDK method
name says "all organization and project API keys" while the reference page title says "List
organization API keys". The schema is admin-key-shaped (`sk-admin...`). Verify empirically before
using it as your key inventory.

### 4.4 Other admin endpoints worth knowing
- `POST /organization/spend_limit` — body `{threshold_amount (cents), currency, interval:"month"}`; replaces the org's monthly hard cap. Hitting it returns `429` on affected requests.
- `GET /organization/audit_logs` — `limit` etc.; recent user actions/config changes.
- `POST /organization/invites`, `/organization/users`, projects CRUD, project `spend_alerts`
  (thresholds in cents), `data_retention`, `model_permissions` (`allow_list`/`deny_list`).
- SDK minimum versions for Admin APIs: Node `6.36.0`, Python `2.34.0`, Go `3.34.0`, Ruby `0.61.0`, Java `4.34.0`.

**No admin endpoint returns:** token usage, per-model cost, prepaid balance, or invoice totals.
Cost reconciliation is entirely a client-side job over `/usage/*` + `/costs`.

---

## 5. Pricing (USD per 1M tokens), as published on developers.openai.com/api/docs/pricing

Retrieved 2026-10-14. **No effective dates are published on the pricing page** — no "prices
effective <date>" line exists in the extracted content. UNVERIFIED/unknown: effective dates. Prices
can change without notice; snapshot this table with a retrieval date in your repo.

Columns below: **uncached input / cached input / output**. OpenAI's real table has 8 columns
(short-context input, cached, cache-write, output; long-context input, cached, cache-write, output).
Short context = ≤272K input tokens; long context = >272K. Where the row is only shown with a
`(<272K context length)` qualifier, that qualifier is preserved. `-` = not published / not applicable.

### 5.1 Standard pricing
| Model | Input | Cached input | Cache write | Output | Long-ctx input | Long-ctx cached | Long-ctx cache write | Long-ctx output |
|---|---|---|---|---|---|---|---|---|
| gpt-6-astra | $10.00 | $1.00 | $12.50 | $50.00 | $20.00 | $2.00 | $25.00 | $75.00 |
| gpt-6.1-sol | $2.00 | $0.10 | $2.50 | $10.00 | $4.00 | $0.20 | $5.00 | $15.00 |
| gpt-6-luna | $0.10 | $0.01 | $0.125 | $0.50 | $0.20 | $0.02 | $0.25 | $0.75 |
| gpt-6-sol | $2.00 | $0.20 | $2.50 | $10.00 | $4.00 | $0.40 | $5.00 | $15.00 |
| gpt-5.6-sol | $4.00 | $0.40 | $5.00 | $20.00 | $8.00 | $0.80 | $10.00 | $30.00 |
| gpt-5.6-terra | $2.00 | $0.20 | $2.50 | $12.00 | $4.00 | $0.40 | $5.00 | $18.00 |
| gpt-5.6-luna | $0.20 | $0.02 | $0.25 | $1.20 | $0.40 | $0.04 | $0.50 | $1.80 |
| gpt-5.5 (<272K) | $5.00 | $0.50 | - | $30.00 | $10.00 | $1.00 | - | $45.00 |
| gpt-5.2 | $1.75 | $0.175 | - | $14.00 | - | - | - | - |
| gpt-5.2-pro | $21.00 | - | - | $168.00 | - | - | - | - |
| gpt-5.1 | $1.25 | $0.125 | - | $10.00 | - | - | - | - |
| gpt-5 | $1.25 | $0.125 | - | $10.00 | - | - | - | - |
| gpt-5-mini | $0.25 | $0.025 | - | $2.00 | - | - | - | - |
| gpt-5-nano | $0.05 | $0.005 | - | $0.40 | - | - | - | - |
| gpt-5-pro | $15.00 | - | - | $120.00 | - | - | - | - |
| gpt-4.1 | $2.00 | $0.50 | - | $8.00 | - | - | - | - |
| gpt-4.1-mini | $0.40 | $0.10 | - | $1.60 | - | - | - | - |
| gpt-4.1-nano | $0.10 | $0.025 | - | $0.40 | - | - | - | - |
| gpt-4o | $2.50 | $1.25 | - | $10.00 | - | - | - | - |
| gpt-4o-2024-05-13 | $5.00 | - | - | $15.00 | - | - | - | - |
| gpt-4o-mini | $0.15 | $0.075 | - | $0.60 | - | - | - | - |
| o1 | $15.00 | $7.50 | - | $60.00 | - | - | - | - |
| o1-pro | $150.00 | - | - | $600.00 | - | - | - | - |
| o3-pro | $20.00 | - | - | $80.00 | - | - | - | - |
| o3 | $2.00 | $0.50 | - | $8.00 | - | - | - | - |
| o4-mini | $1.10 | $0.275 | - | $4.40 | - | - | - | - |
| o3-mini | $1.10 | $0.55 | - | $4.40 | - | - | - | - |
| gpt-4-turbo-2024-04-09 | $10.00 | - | - | $30.00 | - | - | - | - |
| gpt-4-0613 | $30.00 | - | - | $60.00 | - | - | - | - |

### 5.2 Batch pricing (50% of standard for most rows)
| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-5.5 (<272K) | $2.50 | $0.25 | $15.00 |
| gpt-5.5-pro (<272K) | $15.00 | - | $90.00 |
| gpt-5.4 (<272K) | $1.25 | $0.13 | $7.50 |
| gpt-5.4-mini | $0.375 | $0.0375 | $2.25 |
| gpt-5.4-nano | $0.10 | $0.01 | $0.625 |
| gpt-5.4-pro (<272K) | $15.00 | - | $90.00 |
| gpt-5.2 | $0.875 | $0.0875 | $7.00 |
| gpt-5.2-pro | $10.50 | - | $84.00 |
| gpt-5.1 | $0.625 | $0.0625 | $5.00 |
| gpt-5 | $0.625 | $0.0625 | $5.00 |
| gpt-5-mini | $0.125 | $0.0125 | $1.00 |
| gpt-5-nano | $0.025 | $0.0025 | $0.20 |
| gpt-5-pro | $7.50 | - | $60.00 |
| gpt-4.1 | $1.00 | - | $4.00 |
| gpt-4.1-mini | $0.20 | - | $0.80 |
| gpt-4.1-nano | $0.05 | - | $0.20 |
| gpt-4o | $1.25 | - | $5.00 |
| gpt-4o-2024-05-13 | $2.50 | - | $7.50 |
| gpt-4o-mini | $0.075 | - | $0.30 |
| o1 | $7.50 | - | $30.00 |
| o1-pro | $75.00 | - | $300.00 |
| o3-pro | $10.00 | - | $40.00 |
| o3 | $1.00 | - | $4.00 |
| o4-mini | $0.55 | - | $2.20 |
| o3-mini | $0.55 | - | $2.20 |
| gpt-4-turbo-2024-04-09 | $5.00 | - | $15.00 |
| gpt-4-0613 | $15.00 | - | $30.00 |
| gpt-3.5-turbo-0125 | $0.25 | - | $0.75 |
| gpt-3.5-turbo-1106 | $1.00 | - | $2.00 |
| davinci-002 | $1.00 | - | $1.00 |

(Note: the batch table on the page lists gpt-6-*/gpt-5.6-* rows too, at exactly half of standard —
gpt-6-astra $5.00/$0.50/$25.00, gpt-6.1-sol $1.00/$0.05/$5.00, gpt-6-luna $0.05/$0.005/$0.25,
gpt-6-sol $1.00/$0.10/$5.00, gpt-5.6-sol $2.00/$0.20/$10.00, gpt-5.6-terra $1.00/$0.10/$6.00,
gpt-5.6-luna $0.10/$0.01/$0.60 — omitted above for brevity.)

**Important:** batch rows show **no cached-input price** for the gpt-4.x/o-series — treat cached-input
discount as unavailable on Batch for those, or verify.

### 5.3 Flex pricing
Identical to Batch for every model listed (gpt-6-astra $5.00/$0.50/$25.00, gpt-6.1-sol
$1.00/$0.05/$5.00, gpt-6-luna $0.05/$0.005/$0.25, gpt-6-sol $1.00/$0.10/$5.00, gpt-5.6-sol
$2.00/$0.20/$10.00, gpt-5.6-terra $1.00/$0.10/$6.00, gpt-5.6-luna $0.10/$0.01/$0.60, gpt-5.5
$2.50/$0.25/$15.00, gpt-5.5-pro $15.00/-/$90.00).

### 5.4 Fast pricing (premium tier)
| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-6-astra | $20.00 | $2.00 | $100.00 |
| gpt-6.1-sol | $4.00 | $0.20 | $20.00 |
| gpt-6-luna | $0.20 | $0.02 | $1.00 |
| gpt-6-sol | $4.00 | $0.40 | $20.00 |
| gpt-5.4-mini | $1.50 | $0.15 | $9.00 |
| gpt-5.2 | $3.50 | $0.35 | $28.00 |
| gpt-5.1 | $2.50 | $0.25 | $20.00 |
| gpt-5 | $2.50 | $0.25 | $20.00 |
| gpt-5-mini | $0.45 | $0.045 | $3.60 |
| gpt-4.1 | $3.50 | $0.875 | $14.00 |
| gpt-4.1-mini | $0.70 | $0.175 | $2.80 |
| gpt-4.1-nano | $0.20 | $0.05 | $0.80 |
| gpt-4o | $4.25 | $2.125 | $17.00 |
| gpt-4o-2024-05-13 | $8.75 | - | $26.25 |
| gpt-4o-mini | $0.25 | $0.125 | $1.00 |
| o3 | $3.50 | $0.875 | $14.00 |
| o4-mini | $2.00 | $0.50 | $8.00 |

### 5.5 Ultrafast pricing
Only two rows published: gpt-6-astra $60.00/$6.00/$300.00 (short ctx; $120/$12/$450 long ctx),
gpt-6.1-sol $12.00/$0.60/$60.00 (short; $24/$1.20/$90 long).

### 5.6 Grouped / special models
| Model | Input | Cached input | Cache write | Output |
|---|---|---|---|---|
| gpt-5.6-sol | $4.00 | $0.40 | $5.00 | $20.00 |
| gpt-5.6-cyber | $12.50 | $1.25 | $15.625 | $75.00 |
| gpt-5.5-cyber | $12.50 | $1.25 | - | $75.00 |

### 5.7 Realtime / audio (per 1M tokens; some per minute)
| Model | Modality | Input | Cached input | Output |
|---|---|---|---|---|
| gpt-realtime-2.1 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-2.1 | Text | $4.00 | $0.40 | $24.00 |
| gpt-realtime-2.1 | Image | $5.00 | $0.50 | - |
| gpt-realtime-2.1-mini | Audio | $10.00 | $0.30 | $20.00 |
| gpt-realtime-2.1-mini | Text | $0.60 | $0.06 | $2.40 |
| gpt-realtime-2.1-mini | Image | $0.80 | $0.08 | - |
| gpt-realtime-2 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-2 | Text | $4.00 | $0.40 | $24.00 |
| gpt-realtime-2 | Image | $5.00 | $0.50 | - |
| gpt-realtime-1.5 | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime-1.5 | Text | $4.00 | $0.40 | $16.00 |
| gpt-realtime-mini | Audio | $10.00 | $0.30 | $20.00 |
| gpt-realtime-mini | Text | $0.60 | $0.06 | $2.40 |
| gpt-realtime | Audio | $32.00 | $0.40 | $64.00 |
| gpt-realtime | Text | $4.00 | $0.40 | $16.00 |
| gpt-realtime | Image | $5.00 | $0.50 | - |
| gpt-audio-1.5 | Audio | $32.00 | - | $64.00 |
| gpt-audio-1.5 | Text | $2.50 | - | $10.00 |
| gpt-audio-mini | Audio | $10.00 | - | $20.00 |
| gpt-audio-mini | Text | $0.60 | - | $2.40 |
| gpt-audio | Audio | $32.00 | - | $64.00 |
| gpt-audio | Text | $2.50 | - | $10.00 |
| gpt-4o-mini-tts | Text | $0.60 | - | (output $12.00) |
| tts-1 | Text | $15.00 / 1M characters | - | - |
| tts-1-hd | Text | $30.00 / 1M characters | - | - |

Per-minute audio: gpt-realtime-translate $0.034/min; gpt-live-transcribe $0.017/min;
gpt-realtime-whisper $0.017/min; gpt-transcribe $0.0045/min; gpt-4o-transcribe $0.006/min
(text $2.50/$10.00); gpt-4o-mini-transcribe $0.003/min (text $1.25/$5.00);
gpt-4o-transcribe-diarize $0.006/min; Whisper $0.006/min.

### 5.8 Image models
| Model | Modality | Input | Cached input | Output |
|---|---|---|---|---|
| gpt-image-2.5-sunburst | Image | $8.00 | $2.00 | $30.00 |
| gpt-image-2.5-sunburst | Text | $5.00 | $1.25 | - |
| gpt-image-2.5-flare | Image | $8.00 | $2.00 | $30.00 |
| gpt-image-2.5-flare | Text | $5.00 | $1.25 | - |
| gpt-image-2 | Image | $8.00 | $2.00 | $30.00 |
| gpt-image-2 | Text | $5.00 | $1.25 | - |
| gpt-image-1.5 | Image | $8.00 | $2.00 | $32.00 |
| gpt-image-1.5 | Text | $5.00 | $1.25 | $10.00 |
| gpt-image-1-mini | Image | $2.50 | $0.25 | $8.00 |
| gpt-image-1-mini | Text | $2.00 | $0.20 | - |
| gpt-image-1 | Image | $10.00 | $2.50 | $40.00 |
| gpt-image-1 | Text | $5.00 | $1.25 | - |
| chatgpt-image-latest | Image | $8.00 | $2.00 | $32.00 |
| chatgpt-image-latest | Text | $5.00 | $1.25 | $10.00 |

(A second, cheaper image table on the page appears to be the batch/50% variant: gpt-image-2
$4.00/$1.00/$15.00, gpt-image-1.5 $4.00/$1.00/$16.00, gpt-image-1-mini $1.25/$0.13/$4.00,
gpt-image-1 $5.00/$1.25/$20.00, chatgpt-image-latest $4.00/$1.00/$16.00.)

### 5.9 ChatGPT-branded / Codex
| Category | Model | Input | Cached input | Output |
|---|---|---|---|---|
| ChatGPT | chat-latest | $5.00 | $0.50 | $30.00 |
| Codex | gpt-5.3-codex | $1.75 | $0.175 | $14.00 |

### 5.10 Tools & non-token pricing
| Tool | Detail | Price |
|---|---|---|
| Web search | all models | $10.00 / 1k calls + search content tokens billed at model rates |
| Web search | Image web search (all models) | $10.00 / 1k calls + content tokens at model rates |
| Web search | preview, reasoning models (`gpt-5`, `o-series`) | $10.00 / 1k calls + content at model rates |
| Web search | preview, non-reasoning models | $25.00 / 1k calls, content tokens free |
| Web search | `gpt-4o-mini` / `gpt-4.1-mini` non-preview tool | content billed as a fixed block of **8,000 input tokens per call** |
| Containers | Hosted Shell / Code Interpreter | 1 GB $0.03, 4 GB $0.12, 16 GB $0.48, 64 GB $1.92 per **20-minute session** per container; 5-minute minimum per session |
| File search | Storage | $0.10 / GB per day (1 GB free) |
| File search | Tool call | $2.50 / 1k calls |
| Agent Kit | ChatKit file/image upload storage | $0.10 / GB-day after 1 GB free per account per month |

"Responses API, Chat Completions API, Realtime API, Batch API, and Assistants API are not priced
separately. Tokens are billed at the chosen model's input and output rates." File search tool-call
pricing applies to the Responses API only.

### 5.11 Fine-tuning (per-model)
Standard: o4-mini-2025-04-16 $100.00/hour, $4.00/$1.00/$16.00; with data sharing $100.00/hour,
$2.00/$0.50/$8.00; gpt-4.1-2025-04-14 $25.00, $3.00/$0.75/$12.00; gpt-4.1-mini-2025-04-14 $5.00,
$0.80/$0.20/$3.20; gpt-4.1-nano-2025-04-14 $1.50, $0.20/$0.05/$0.80; gpt-4o-2024-08-06 $25.00,
$3.75/$1.875/$15.00; gpt-4o-mini-2024-07-18 $3.00, $0.30/$0.15/$1.20; gpt-3.5-turbo (legacy) $8.00,
$3.00/-/$6.00; davinci-002 (legacy) $6.00, $12.00/-/$12.00; babbage-002 (legacy) $0.40, $1.60/-/$1.60.
Data-sharing variant is roughly half for input/cached/output.

---

## 6. Implications for a cost-estimation monitor (derived, flagged as inference)

- Per-key cost cannot be read from any single endpoint. The workable recipe:
  `GET /organization/usage/completions?group_by=["model","api_key_id","project_id"]` for tokens,
  `GET /organization/costs?group_by=["line_item","api_key_id","project_id"]` for billed dollars,
  `GET /organization/projects` + `GET /organization/projects/{id}/api_keys` for the id→name map.
- Estimating cost from tokens requires deciding a price per (model, token class, service tier,
  batch flag). The Usage API gives you `input_uncached_tokens`, `input_cached_tokens`,
  `input_cache_write_tokens`, `output_tokens`, `batch`, `service_tier` — i.e. enough to apply the
  4-way price split (uncached / cached / cache-write / output) for most models. **Gap: OpenAI
  publishes no cache-write price for gpt-4.x and o-series (shown as `-`), and no cached-input price
  for batch on those models. Those combinations will not reconcile exactly.**
- Long-context models (>272K input) have a *different* price table, but the Usage API does not tell
  you whether a bucket's requests exceeded 272K context. **Reconciliation for gpt-5.5 / gpt-6-astra /
  gpt-5.6-* will be approximate unless you bucket by model and accept the blended error.** UNVERIFIED
  whether any Usage field exposes context length.
- Realtime/audio usage appears in `/usage/completions` as audio text/audio tokens, but realtime
  per-minute pricing (e.g. gpt-realtime-translate) cannot be derived from token counts at all —
  for those, trust `/organization/costs` line items rather than estimating.
- Fine-tune training hours appear nowhere in Usage; only as cost line items.
- Service tiers ("standard", "batch", "flex", "fast", "ultrafast") are groupable via
  `service_tier`, which is exactly what you need to pick the right price column — but the documented
  enum values for `service_tier` are **UNVERIFIED** (not enumerated in the reference).
