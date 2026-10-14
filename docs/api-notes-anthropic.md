# Anthropic Admin API, Usage & Cost API — Research Notes

Source: platform.claude.com official docs (English). Pages consulted:
- https://platform.claude.com/docs/en/manage-claude/usage-cost-api (Usage and Cost API guide)
- https://platform.claude.com/docs/en/api/beta/organization/usage_report/retrieve_messages (Get Messages Usage Report)
- https://platform.claude.com/docs/en/api/beta/organization/cost_report/retrieve (Get Cost Report)
- https://platform.claude.com/docs/en/api/beta/organization/api_keys/list (List API Keys)
- https://platform.claude.com/docs/en/api/beta/organization/users/list (List Users / members)
- https://platform.claude.com/docs/en/api/beta/organization/workspaces/list (List Workspaces)
- https://platform.claude.com/docs/en/about-claude/pricing (Pricing)
- https://platform.claude.com/docs/en/manage-claude/workspaces (Workspaces guide, for default-workspace semantics)

All docs accessible; nothing paywalled or blocked.

---

## 0. Global facts

### Authentication
- All these endpoints are part of the **Admin API**, base `https://api.anthropic.com`.
- Accepted credentials: an **Admin API key** (`sk-ant-admin01-...`) in the `x-api-key` header, an **OAuth token** with `org:admin` scope in `authorization: Bearer`, or a **personal/service-account key not scoped to a workspace** in `x-api-key`.
- **Workspace-scoped API keys do NOT work** for the Admin API.
- Always send header `anthropic-version: 2023-06-01`.
- Optional header `anthropic-beta: fast-mode-2026-02-01` for speed dimension (usage endpoint only).
- Recommended: set a `User-Agent` header, e.g. `User-Agent: YourApp/1.0.0 (https://yourapp.com)`.

### Which API / key per org type
| Organization | API | Key |
|---|---|---|
| Claude Console (Claude Platform) | Usage & Cost Admin API (this doc) | Admin API key |
| Claude Enterprise (claude.ai) | Claude Enterprise Analytics API | Analytics API key |

- **Claude Platform on AWS: the Usage & Cost endpoints are NOT available.** Only workspaces + external_keys endpoints work there.

### Data freshness & polling
- Data typically appears within **5 minutes** of API request completion; delays can be longer.
- Recommended polling: **once per minute for sustained use**; short bursts (e.g., paginating) may poll more often. Cache results for dashboards.

### Rate limits (documented)
- Admin API endpoints: **100 requests per minute per organization** (per org). Invite creation has a separate limit of 1,200 req/hour. (Source: User management / Admin API guide.)
- Note: the Usage & Cost API doc itself does not state a numeric rate limit beyond the polling recommendation above. Anything beyond that: UNVERIFIED.

### Timestamps
- All request params and response fields use **RFC 3339** timestamps (e.g., `2025-08-01T00:00:00Z`), UTC.
- Time buckets are snapped to the start of the minute/hour/day in UTC.

### Pagination styles (two distinct styles in play!)
- **Usage report & Cost report**: page-token style. Response has `has_more` (bool) and `next_page` (string token, e.g. `page_MjAyNS0wNS0xNFQwMDowMDowMFo=`). Next request passes `page=<next_page token>`. Plus a `limit` on number of buckets.
- **List API Keys / List Users / List Workspaces**: cursor style. Query params `after_id` / `before_id`; response has `first_id`, `last_id`, `has_more`. Pass `after_id=<last_id>` for the next page.

---

## 1. GET /v1/organizations/usage_report/messages — Get Messages Usage Report

**URL path:** `/v1/organizations/usage_report/messages`
**Method:** GET
**Purpose:** Token-consumption report by time bucket, filterable/groupable by many dimensions. The per-key usage inventory endpoint.

### Query parameters
| Param | Required | Type | Notes |
|---|---|---|---|
| `starting_at` | **Required** | string (RFC 3339) | Buckets starting on/after this timestamp; snapped to bucket start (UTC) |
| `ending_at` | Optional | string (RFC 3339) | Buckets ending before this timestamp |
| `bucket_width` | Optional, default `1d` | `"1m" \| "1h" \| "1d"` | Time granularity |
| `group_by` | Optional | array of `account_id, api_key_id, context_window, inference_geo, model, service_account_id, service_tier, speed, workspace_id` (9 total) | Grouping dimensions. `speed` requires beta header `fast-mode-2026-02-01` |
| `api_key_ids` | Optional | array of string | Filter to specific API key IDs |
| `workspace_ids` | Optional | array of string | Filter to specific workspace IDs |
| `account_ids` | Optional | array of string | Filter to user account IDs |
| `service_account_ids` | Optional | array of string | Filter to service account IDs |
| `models` | Optional | array of string | Filter to specific models |
| `service_tiers` | Optional | array of `batch, flex, flex_discount, ...` (others not enumerated in doc; likely `standard`, `priority`) | Filter by service tier |
| `context_window` | Optional | array of `"0-200k", "200k-1M"` | Filter by context window |
| `inference_geos` | Optional | array of `global, us, not_available` | `not_available` for pre-Feb-2026 models |
| `speeds` | Optional | array of `standard, fast` | Requires beta header `fast-mode-2026-02-01` (research preview) |
| `limit` | Optional | number | Max time buckets per page; default & max depend on `bucket_width` (see below) |
| `page` | Optional | string | `next_page` token from previous response |

### Bucket widths & span limits
| bucket_width | Default limit | Maximum limit |
|---|---|---|
| `1m` | 60 buckets | **1,440 buckets (24h)** |
| `1h` | 24 buckets | **168 buckets (7 days)** |
| `1d` | 7 buckets | **31 buckets (31 days)** |

Note: a single request's `starting_at`→`ending_at` range is limited by `limit` buckets, so e.g. 1h buckets can cover at most 168h per page; paginate with `page=` to go further back.

### Response schema (200)
```
{
  "data": [
    {
      "starting_at": "<RFC3339>",
      "ending_at": "<RFC3339>",
      "results": [
        {
          "api_key_id": "apikey_01...",          // null for playground usage / default workspace? see notes
          "account_id": "user_01...",
          "service_account_id": "svac_01...",
          "workspace_id": "wrkspc_01...",
          "model": "claude-opus-5-5",
          "context_window": "0-200k",
          "inference_geo": "global",
          "service_tier": "standard",
          "uncached_input_tokens": 1500,
          "cache_read_input_tokens": 200,
          "output_tokens": 500,
          "cache_creation": {
            "ephemeral_5m_input_tokens": 0,
            "ephemeral_1h_input_tokens": 0
          },
          "server_tool_use": {
            "web_search_requests": 10
          }
        }
      ]
    }
  ],
  "has_more": true,
  "next_page": "page_MjAyNS0wNS0xNFQwMDowMDowMFo="
}
```

### What it does NOT contain
- **No cost fields** — token counts only; you must compute cost from the pricing table.
- **No code-execution usage** — code execution is excluded from the usage endpoint (tracked only in the cost endpoint).
- **`api_key_id` is `null`** for playground/Workbench (Claude Console) usage, even when grouping by `api_key_id`.
- **`workspace_id` is `null`** for the Default Workspace (and for all-workspaces API keys), even when grouping by workspace.
- No per-request granularity, no latency, no error/request counts.
- Priority Tier appears only as `service_tier=priority` here — its **cost is not in the cost endpoint**.
- `inference_geo` is `"not_available"` for models released before Feb 2026 (pre-Opus 4.6/Sonnet 4.6).

---

## 2. GET /v1/organizations/cost_report — Get Cost Report

**URL path:** `/v1/organizations/cost_report`
**Method:** GET
**Purpose:** Service-level cost breakdown in **USD**.

### Key concepts
- All costs in USD, as **decimal strings in lowest units (cents)** (e.g., `"123.78912"` — the example shows a string with fractional digits; the doc says "decimal strings in lowest units (cents)"). Treat as a decimal string; do not assume 2-dp.
- Cost types tracked: **token usage, web search, code execution**.
- Grouping: `workspace_id` or `description` only (see below).
- **Time buckets: daily (`1d`) only.**

### Query parameters
| Param | Required | Type | Notes |
|---|---|---|---|
| `starting_at` | **Required** | string (RFC 3339) | Same snapping semantics as usage endpoint |
| `ending_at` | Optional | string (RFC 3339) | |
| `bucket_width` | Optional, only value `"1d"` | `"1d"` | Daily granularity only |
| `group_by` | Optional | array of `"description", "workspace_id"` | When grouping by `description`, response rows include parsed fields `model` and `inference_geo` |
| `limit` | Optional, default 7 | number | Min 1, **max 31** (buckets per page) |
| `page` | Optional | string | `next_page` token |

Note: there is **no** `group_by=api_key_id` here — cost does **NOT** break down per API key via this endpoint. (Per-user/per-key cost requires the separate Claude Enterprise Analytics API or the Claude Code Analytics API.)

### Response schema (200)
```
{
  "data": [
    {
      "starting_at": "2025-08-01T00:00:00Z",
      "ending_at": "2025-08-02T00:00:00Z",
      "results": [
        {
          "amount": "123.78912",
          "currency": "USD",
          "cost_type": "tokens",              // also: web_search, code_execution
          "description": "Claude Opus 5.5 Usage - Input Tokens",
          "model": "claude-opus-5-5",          // present when grouped by description
          "inference_geo": "global",           // present when grouped by description
          "service_tier": "standard",
          "context_window": "0-200k",
          "token_type": "cache_creation.ephemeral_1h_input_tokens",  // for cost_type=tokens
          "workspace_id": "wrkspc_01..."
        }
      ]
    }
  ],
  "has_more": true,
  "next_page": "page_MjAyNS0wNS0xNFQwMDowMDowMFo="
}
```

### What it does NOT contain
- **No per-API-key cost breakdown** (group_by only supports `workspace_id` and `description`).
- **No Priority Tier costs** — excluded; track priority usage via the usage endpoint instead.
- **No code-execution usage in the usage endpoint** (inverse relationship; code execution appears here under `description` "Code Execution Usage").
- `workspace_id` is `null` for the Default Workspace.
- No hourly granularity; no batch processing discount is computed by you (cost here is post-discount as billed by Anthropic — the doc says costs are "reported... in USD" and FAQ says it reconciles with billing; exact discount/pre-credit semantics of `amount` beyond that: UNVERIFIED).

---

## 3. GET /v1/organizations/api_keys — List API Keys (key inventory)

**URL path:** `/v1/organizations/api_keys`
**Method:** GET
**Purpose:** Inventory the organization's API keys (needed to map usage `api_key_id`s to human metadata).

### Query parameters
| Param | Required | Type | Notes |
|---|---|---|---|
| `after_id` / `before_id` | Optional | string | Cursor pagination (after/before an object ID) |
| `created_by_user_id` | Optional | string | Filter by creator user ID |
| `workspace_id` | Optional | string | Filter by workspace |
| `status` | Optional | `active, archived, expired, inactive` | Filter by status |
| `limit` | Optional | number | Items per page |

### Response (200)
```
{
  "data": [
    {
      "id": "apikey_01...",
      "type": "api_key",
      "name": "Developer Key",
      "partial_key_hint": "***...igAA",
      "status": "active",
      "created_at": "<RFC3339>",
      "expires_at": "<RFC3339>",
      "created_by": { "id": "user_01...", "type": "user" },
      "principal": { "type": "user_actor", "user_id": "user_01..." },
      "scope": { "type": "workspace", "workspace_id": "wrkspc_01..." },
      "workspace_id": "wrkspc_01..."
    }
  ],
  "first_id": "...", "last_id": "...", "has_more": true
}
```

### What it does NOT contain
- **Never returns the secret key value** — only `partial_key_hint`.
- No usage or cost figures — inventory metadata only.
- There is also `GET /v1/organizations/api_keys/{api_key_id}` to retrieve a single key. The Admin API can only **read, rename, and change the status** of existing keys (cannot create/rotate via Admin API).

---

## 4. GET /v1/organizations/workspaces — List Workspaces

**URL path:** `/v1/organizations/workspaces`
**Method:** GET

### Query parameters
| Param | Required | Type | Notes |
|---|---|---|---|
| `after_id` / `before_id` | Optional | string | Cursor pagination |
| `include_archived` | Optional, default `false` | boolean | Include archived workspaces |
| `include_default` | Optional, default `false` | boolean | Include the organization's Default Workspace |
| `limit` | Optional, default 20 | number | 1–1000 |

### Response highlights
- `data[].id` (`wrkspc_...`), `name`, `type: "workspace"`, `archived_at`, `created_at`, `display_color`, `tags` (map), `data_residency` (allowed_inference_geos, default_inference_geo, workspace_geo), `external_key_id` (CMEK), `compartment_id`.
- Pagination: `first_id`, `last_id`, `has_more`.

### Important default-workspace semantics (from Workspaces guide)
- The **Default Workspace has a real `wrkspc_` ID** and is returned by Get Workspace, but **appears in List Workspaces only with `include_default=true`**.
- API keys, usage reports, and cost reports show **`null` for its `workspace_id`**.
- All-workspaces API keys also show `null` `workspace_id` in reports; an API key's `scope` field distinguishes them (a key bound to the Default Workspace carries the real ID).

---

## 5. GET /v1/organizations/users — List Users (members)

**URL path:** `/v1/organizations/users`
**Method:** GET
**Purpose:** List organization members (for per-user cost attribution context).

### Query parameters
| Param | Required | Type | Notes |
|---|---|---|---|
| `after_id` / `before_id` | Optional | string | Cursor pagination |
| `email` | Optional | string | Filter by email (case-insensitive, variant-tolerant) |
| `roles` | Optional | array of string | Filter by role (OR'ed) |
| `limit` | Optional | number | Items per page |

### Response (200)
```
{
  "data": [
    { "id": "user_01...", "type": "user", "name": "Jane Doe",
      "email": "user@emaildomain.com", "role": "admin", "added_at": "<RFC3339>" }
  ],
  "first_id": "...", "last_id": "...", "has_more": true
}
```
Members returned **most recently added first**. Requires `read:members` scope (for Claude Enterprise key types; org-scoped Admin keys fine for Console orgs — exact scope mapping: UNVERIFIED).

Also: `GET /v1/organizations/users/{user_id}`, `POST /v1/organizations/users/{user_id}` (role change), `DELETE /v1/organizations/users/{user_id}`.

---

## 6. Related endpoints (admin-relevant, brief)
- `GET /v1/organizations/workspaces/{workspace_id}` — Get Workspace.
- `GET /v1/organizations/workspaces/{workspace_id}/rate_limits` — List a workspace's rate limits.
- `GET /v1/organizations/rate_limits` (Rate Limits API) — org-wide rate limits (exists in Admin > Monitoring; full reference not extracted here — UNVERIFIED details).
- Spend Limits API, Analytics APIs (Claude Code Analytics API for per-user Claude Code cost; Claude Enterprise Analytics API `cost_report`/`user_cost_report` for Claude Enterprise orgs) — different products, different keys.
- On Claude Platform on AWS only the workspace and external_keys (CMEK) endpoints are available.

---

## 7. Model pricing (USD per million tokens, standard pricing, Claude API first-party, global)

From https://platform.claude.com/docs/en/about-claude/pricing (accessed 2026-10-14). All prices USD per 1M tokens. No single effective date stated on the page; the page is "current" pricing and notes the Sonnet 5 price stabilization. (See footnote 3 below for the only dated item.)

| Model | Base input | 5m cache write | 1h cache write | Cache hits/refreshes | Output |
|---|---|---|---|---|---|
| Claude Fable 5.1 | $10 | $12.50 | $20 | $0.25 (0.025x) | $50 |
| Claude Mythos 5.1 (limited) | $10 | $12.50 | $20 | $0.25 (0.025x) | $50 |
| Claude Fable 5 | $10 | $12.50 | $20 | $1.00 (0.1x) | $50 |
| Claude Mythos 5 (limited) | $10 | $12.50 | $20 | $1.00 (0.1x) | $50 |
| Claude Opus 5.5 | $4 | $5 | $8 | $0.20 (0.05x) | $20 |
| Claude Opus 5 | $5 | $6.25 | $10 | $0.50 (0.1x) | $25 |
| Claude Opus 4.8 | $5 | $6.25 | $10 | $0.50 (0.1x) | $25 |
| Claude Opus 4.7 | $5 | $6.25 | $10 | $0.50 (0.1x) | $25 |
| Claude Opus 4.6 | $5 | $6.25 | $10 | $0.50 (0.1x) | $25 |
| Claude Opus 4.5 | $5 | $6.25 | $10 | $0.50 (0.1x) | $25 |
| Claude Opus 4.1 (retired) | $15 | $18.75 | $30 | $1.50 (0.1x) | $75 |
| Claude Opus 4 (retired) | $15 | $18.75 | $30 | $1.50 (0.1x) | $75 |
| Claude Sonnet 5.5 | $2 | $2.50 | $4 | $0.10 (0.05x) | $10 |
| Claude Sonnet 5 | $2 | $2.50 | $4 | $0.20 (0.1x) | $10 |
| Claude Sonnet 4.6 | $3 | $3.75 | $6 | $0.30 (0.1x) | $15 |
| Claude Sonnet 4.5 | $3 | $3.75 | $6 | $0.30 (0.1x) | $15 |
| Claude Sonnet 4 (retired) | $3 | $3.75 | $6 | $0.30 (0.1x) | $15 |
| Claude Haiku 5.5 (prompt ≤100k) | $0.10 | $0.125 | $0.20 | $0.01 (0.1x) | $0.50 |
| Claude Haiku 5.5 (prompt >100k) | $0.50 | $0.625 | $1.00 | $0.05 (0.1x) | $2.50 |
| Claude Haiku 4.5 | $1 | $1.25 | $2 | $0.10 (0.1x) | $5 |
| Claude Haiku 3.5 (retired) | $0.80 | $1 | $1.60 | $0.08 (0.1x) | $4 |

### Cache pricing multipliers
- 5-minute cache write: **1.25x** base input price.
- 1-hour cache write: **2x** base input price.
- Cache read (hit): **0.1x** base input (0.025x on Fable 5.1 / Mythos 5.1; 0.05x on Opus 5.5 / Sonnet 5.5).
- These map to the usage endpoint's `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` / `cache_read_input_tokens`, and the cost endpoint's `token_type` values like `cache_creation.ephemeral_1h_input_tokens`.

### Pricing modifiers
- **Batch processing: 50% discount** on input and output (e.g., Opus 5.5 batch $2/$10; Sonnet 5.5 batch $1/$5; Fable 5.1 batch $5/$25).
- **Data residency:** `inference_geo: "us"` on Claude 4.6+ models adds **1.1x** on all token categories (incl. cache reads/writes). Global = standard.
- **Fast mode** (research preview; Opus 5.5/5/4.8 only): Opus 5.5 $8/$40, Opus 5 & 4.8 $10/$50 per MTok. Requires beta header `fast-mode-2026-02-01`. Not available with Batch API; caching/residency multipliers stack on top.
- **Long context:** Claude 4.6+ (except Haiku 5.5) include the full 1M context window at standard rates — a 900k-token request costs the same per-token as a 9k one.
- **Web search:** $10 per 1,000 searches, plus standard tokens for search-generated content.
- **Code execution:** free when bundled with web search/web fetch; otherwise billed by execution time (1,550 free org-hours/month, then $0.05/hour/container). Tracked in cost endpoint, not usage endpoint.
- **Effective dates:** The only dated note on the page: "The $2/$10 per million input/output pricing for Claude Sonnet 5, announced at launch as introductory pricing through August 31, 2026, is now the standard price. The previously scheduled increase to $3/$15 on September 1, 2026 will not occur." No other effective dates given on this page. (Anthropic also publishes dated "List Prices" PDF rate cards — e.g. effective 2026-07-24, 2026-06-30 — but those are supplementary; the docs page is authoritative for current pricing.)
- For most-current pricing the page defers to claude.com/pricing.

---

## 8. Key takeaways for the monitor project
- Usage (`usage_report/messages`) gives per-key **token** counts with `api_key_id` grouping — this is how you estimate per-key cost: join with the pricing table above by `model` + token classes, applying cache multipliers.
- Cost (`cost_report`) gives org-level **USD** costs but **only groupable by workspace/description — not per API key** — so per-key cost must be *estimated from usage × pricing*, then reconciled against the cost_report total.
- Watch for `null` `api_key_id` (playground usage) and `null` `workspace_id` (default workspace / all-workspaces keys) when doing per-key attribution.
- Priority Tier: tokens in usage endpoint (service_tier=priority), cost NOT in cost endpoint — reconciliation must account for this gap.
- Code execution: cost only in cost endpoint, not usage endpoint.
- `amount` in cost_report is a decimal string in cents-lowest-units; usage gives raw token counts. To reconcile, sum(usage × price) should approximate the cost_report total, with differences expected from Priority Tier, any discounts applied by Anthropic, and code execution/web search charges not derivable from token usage alone.
