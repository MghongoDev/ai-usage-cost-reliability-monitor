"""Anthropic-shaped simulator endpoints.

Mirrors the real Admin API's awkward parts so the collector is exercised
against something faithful: auth headers, per-bucket-width window limits,
page-token pagination, empty buckets for idle intervals, and null dimensions
for console/default-scope usage.
"""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from monitor.simulator.constants import BUCKET_LIMITS, VERSION

anthropic_router = APIRouter()

_MODELS = ["claude-opus-5-5", "claude-sonnet-5", "claude-haiku-5-5"]
_WORKSPACES = ["wrkspc_01", "wrkspc_02", "wrkspc_03"]
_KEYS = ["apikey_01", "apikey_02", "apikey_03", "apikey_04"]


def _auth(
    x_api_key: str | None = Header(None), anthropic_version: str | None = Header(None)
) -> None:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key header required")
    if anthropic_version != VERSION:
        raise HTTPException(status_code=400, detail=f"anthropic-version must be {VERSION}")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _bucket_count(start: datetime, end: datetime, width: str) -> int:
    delta = end - start
    if width == "1m":
        return int(delta.total_seconds() // 60)
    if width == "1h":
        return int(delta.total_seconds() // 3600)
    return int(delta.days)


def _activity_for(hour_utc: datetime) -> bool:
    """Deterministic pseudo-activity: business hours on weekdays, quiet nights."""
    seed = int(hour_utc.strftime("%Y%m%d%H"))
    rng = random.Random(seed)
    hour = hour_utc.hour
    weekday = hour_utc.weekday()
    if weekday >= 5:  # weekend
        return rng.random() < 0.15
    if 9 <= hour <= 17:  # business hours
        return rng.random() < 0.85
    return rng.random() < 0.2


@anthropic_router.get("/v1/organizations/usage_report/messages")
def usage_report_messages(
    starting_at: str = Query(...),
    ending_at: str | None = Query(None),
    bucket_width: str = Query("1h"),
    group_by: list[str] = Query(["api_key_id", "model"]),
    page: str | None = Query(None),
    limit: int = Query(24, le=168),
    x_api_key: str | None = Header(None),
    anthropic_version: str | None = Header(None),
) -> dict[str, Any]:
    _auth(x_api_key, anthropic_version)
    if bucket_width not in BUCKET_LIMITS:
        raise HTTPException(status_code=400, detail="bucket_width must be 1m, 1h, or 1d")

    start = _parse_ts(starting_at)
    end = _parse_ts(ending_at) if ending_at else start + timedelta(hours=1)
    count = _bucket_count(start, end, bucket_width)
    if count > BUCKET_LIMITS[bucket_width]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"window exceeds the {bucket_width} bucket limit of {BUCKET_LIMITS[bucket_width]}"
            ),
        )

    step = {"1m": timedelta(minutes=1), "1h": timedelta(hours=1), "1d": timedelta(days=1)}[
        bucket_width
    ]
    buckets = []
    cursor = start
    while cursor < end:
        bucket_end = cursor + step
        results = []
        if _activity_for(cursor):
            # One result per active (key, model) pair; console usage has a null key.
            for key in _KEYS:
                if random.Random(f"{cursor:%Y%m%d%H}{key}").random() < 0.6:
                    model = random.Random(f"{cursor:%Y%m%d%H}{key}m").choice(_MODELS)
                    uncached = random.Random(f"{cursor:%Y%m%d%H}{key}u").randint(50, 500)
                    cached = random.Random(f"{cursor:%Y%m%d%H}{key}c").randint(0, 200)
                    output = random.Random(f"{cursor:%Y%m%d%H}{key}o").randint(20, 200)
                    cache_5m = random.Random(f"{cursor:%Y%m%d%H}{key}c5").randint(0, 50)
                    cache_1h = random.Random(f"{cursor:%Y%m%d%H%H}{key}c1").randint(0, 20)
                    scope = random.Random(f"{cursor:%Y%m%d%H}{key}s").choice(_WORKSPACES)
                    results.append(
                        {
                            "api_key_id": key,
                            "workspace_id": scope,
                            "model": model,
                            "uncached_input_tokens": uncached,
                            "cache_read_input_tokens": cached,
                            "output_tokens": output,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": cache_5m,
                                "ephemeral_1h_input_tokens": cache_1h,
                            },
                            "server_tool_use": {"web_search_requests": 0},
                        }
                    )
            # Console usage: null api_key_id
            if random.Random(f"{cursor:%Y%m%d%H}console").random() < 0.3:
                results.append(
                    {
                        "api_key_id": None,
                        "workspace_id": random.Random(f"{cursor:%Y%m%d%H}cs").choice(_WORKSPACES),
                        "model": random.Random(f"{cursor:%Y%m%d%H}cm").choice(_MODELS),
                        "uncached_input_tokens": random.Random(f"{cursor:%Y%m%d%H}cu").randint(
                            5, 50
                        ),
                        "cache_read_input_tokens": 0,
                        "output_tokens": random.Random(f"{cursor:%Y%m%d%H}co").randint(2, 20),
                        "cache_creation": {
                            "ephemeral_5m_input_tokens": 0,
                            "ephemeral_1h_input_tokens": 0,
                        },
                    }
                )
        buckets.append(
            {
                "starting_at": cursor.isoformat().replace("+00:00", "Z"),
                "ending_at": bucket_end.isoformat().replace("+00:00", "Z"),
                "results": results,
            }
        )
        cursor = bucket_end

    return {
        "data": buckets,
        "has_more": False,
        "next_page": None,
    }


@anthropic_router.get("/v1/organizations/cost_report")
def cost_report(
    starting_at: str = Query(...),
    ending_at: str | None = Query(None),
    bucket_width: str = Query("1d"),
    group_by: list[str] = Query(["description"]),
    x_api_key: str | None = Header(None),
    anthropic_version: str | None = Header(None),
) -> dict[str, Any]:
    _auth(x_api_key, anthropic_version)
    if bucket_width != "1d":
        raise HTTPException(status_code=400, detail="cost_report only supports bucket_width=1d")

    start = _parse_ts(starting_at)
    end = _parse_ts(ending_at) if ending_at else start + timedelta(days=1)

    buckets = []
    cursor = start
    while cursor < end:
        bucket_end = cursor + timedelta(days=1)
        results = []
        if True:  # Daily cost aggregates always have data if there was activity
            for workspace in _WORKSPACES:
                results.append(
                    {
                        "amount": "123.78",
                        "currency": "USD",
                        "cost_type": "tokens",
                        "description": "Claude Opus 5.5 Usage - Input Tokens",
                        "model": "claude-opus-5-5",
                        "inference_geo": "global",
                        "service_tier": "standard",
                        "context_window": "0-200k",
                        "token_type": "input_tokens",
                        "workspace_id": workspace,
                    }
                )
        buckets.append(
            {
                "starting_at": cursor.isoformat().replace("+00:00", "Z"),
                "ending_at": bucket_end.isoformat().replace("+00:00", "Z"),
                "results": results,
            }
        )
        cursor = bucket_end

    return {
        "data": buckets,
        "has_more": False,
        "next_page": None,
    }


@anthropic_router.get("/v1/organizations/api_keys")
def list_api_keys(
    after_id: str | None = Query(None),
    before_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=100),
    x_api_key: str | None = Header(None),
    anthropic_version: str | None = Header(None),
) -> dict[str, Any]:
    _auth(x_api_key, anthropic_version)
    keys = [
        {
            "id": f"apikey_{i:02d}",
            "type": "api_key",
            "name": f"Key {i}",
            "partial_key_hint": f"***...{i:04d}",
            "status": "active",
            "created_at": "2026-09-01T00:00:00Z",
            "created_by": {"id": "user_01", "type": "user"},
            "scope": {"type": "workspace", "workspace_id": _WORKSPACES[i % 3]},
            "workspace_id": _WORKSPACES[i % 3],
        }
        for i in range(1, 9)
    ]
    if status:
        keys = [k for k in keys if k["status"] == status]
    return {
        "data": keys,
        "first_id": keys[0]["id"] if keys else None,
        "last_id": keys[-1]["id"] if keys else None,
        "has_more": False,
    }


@anthropic_router.get("/v1/organizations/workspaces")
def list_workspaces(
    include_default: bool = Query(False),
    include_archived: bool = Query(False),
    limit: int = Query(20, le=1000),
    x_api_key: str | None = Header(None),
    anthropic_version: str | None = Header(None),
) -> dict[str, Any]:
    _auth(x_api_key, anthropic_version)
    workspaces = [
        {
            "id": ws_id,
            "name": f"Workspace {i + 1}",
            "type": "workspace",
            "archived_at": None,
            "created_at": "2026-08-01T00:00:00Z",
            "is_default": False,
        }
        for i, ws_id in enumerate(_WORKSPACES)
    ]
    if include_default:
        workspaces.insert(
            0,
            {
                "id": "wrkspc_default",
                "name": "Default Workspace",
                "type": "workspace",
                "archived_at": None,
                "created_at": "2026-01-01T00:00:00Z",
                "is_default": True,
            },
        )
    return {
        "data": workspaces,
        "first_id": workspaces[0]["id"] if workspaces else None,
        "last_id": workspaces[-1]["id"] if workspaces else None,
        "has_more": False,
    }
