"""OpenAI-shaped simulator endpoints.

Mirrors the real Admin API's shape: Unix-second timestamps, page envelope with
next_page cursor, limit counted in buckets, grouping by project_id and
api_key_id. Costs endpoint is daily-only with amount+currency and line_item
grouping.
"""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from monitor.simulator.constants import BUCKET_LIMITS

openai_router = APIRouter()

_MODELS = ["gpt-4o", "gpt-4o-mini", "o3-mini"]
_PROJECTS = ["proj_01", "proj_02", "proj_03"]
_KEYS = ["key_01", "key_02", "key_03", "key_04"]


def _auth(authorization: str | None = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization: Bearer <key> required")


def _parse_ts(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=UTC)


def _activity_for(hour_utc: datetime) -> bool:
    """Deterministic pseudo-activity: business hours on weekdays, quiet nights."""
    seed = int(hour_utc.strftime("%Y%m%d%H"))
    rng = random.Random(seed)
    hour = hour_utc.hour
    weekday = hour_utc.weekday()
    if weekday >= 5:
        return rng.random() < 0.15
    if 9 <= hour <= 17:
        return rng.random() < 0.85
    return rng.random() < 0.2


@openai_router.get("/v1/organization/usage/completions")
def usage_completions(
    start_time: int = Query(...),
    end_time: int | None = Query(None),
    bucket_width: str = Query("1h"),
    group_by: list[str] = Query(["project_id", "api_key_id", "model"]),
    page: str | None = Query(None),
    limit: int = Query(24, le=168),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _auth(authorization)
    if bucket_width not in BUCKET_LIMITS:
        raise HTTPException(status_code=400, detail="bucket_width must be 1m, 1h, or 1d")

    start = _parse_ts(start_time)
    end = _parse_ts(end_time) if end_time else start + timedelta(hours=1)

    step = {"1m": timedelta(minutes=1), "1h": timedelta(hours=1), "1d": timedelta(days=1)}[
        bucket_width
    ]
    buckets = []
    cursor = start
    while cursor < end:
        bucket_end = cursor + step
        results = []
        if _activity_for(cursor):
            for key in _KEYS:
                if random.Random(f"{cursor:%Y%m%d%H}{key}").random() < 0.6:
                    model = random.Random(f"{cursor:%Y%m%d%H}{key}m").choice(_MODELS)
                    uncached = random.Random(f"{cursor:%Y%m%d%H}{key}u").randint(50, 500)
                    cached = random.Random(f"{cursor:%Y%m%d%H}{key}c").randint(0, 200)
                    cache_write = random.Random(f"{cursor:%Y%m%d%H}{key}cw").randint(0, 50)
                    output = random.Random(f"{cursor:%Y%m%d%H}{key}o").randint(20, 200)
                    requests = random.Random(f"{cursor:%Y%m%d%H}{key}r").randint(1, 20)
                    project = random.Random(f"{cursor:%Y%m%d%H}{key}p").choice(_PROJECTS)
                    results.append(
                        {
                            "project_id": project,
                            "api_key_id": key,
                            "model": model,
                            "input_uncached_tokens": uncached,
                            "input_cached_tokens": cached,
                            "input_cache_write_tokens": cache_write,
                            "output_tokens": output,
                            "num_model_requests": requests,
                        }
                    )
            # Unattributed usage: null api_key_id
            if random.Random(f"{cursor:%Y%m%d%H}unattr").random() < 0.3:
                results.append(
                    {
                        "project_id": random.Random(f"{cursor:%Y%m%d%H}up").choice(_PROJECTS),
                        "api_key_id": None,
                        "model": random.Random(f"{cursor:%Y%m%d%H}um").choice(_MODELS),
                        "input_uncached_tokens": random.Random(f"{cursor:%Y%m%d%H}uu").randint(
                            5, 50
                        ),
                        "input_cached_tokens": 0,
                        "input_cache_write_tokens": 0,
                        "output_tokens": random.Random(f"{cursor:%Y%m%d%H}uo").randint(2, 20),
                        "num_model_requests": 1,
                    }
                )
        buckets.append(
            {
                "start_time": int(cursor.timestamp()),
                "end_time": int(bucket_end.timestamp()),
                "results": results,
            }
        )
        cursor = bucket_end

    return {
        "object": "page",
        "data": buckets,
        "has_more": False,
        "next_page": None,
    }


@openai_router.get("/v1/organization/costs")
def costs(
    start_time: int = Query(...),
    end_time: int | None = Query(None),
    bucket_width: str = Query("1d"),
    group_by: list[str] = Query(["project_id", "line_item"]),
    page: str | None = Query(None),
    limit: int = Query(7, le=180),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _auth(authorization)
    if bucket_width != "1d":
        raise HTTPException(status_code=400, detail="costs only supports bucket_width=1d")

    start = _parse_ts(start_time)
    end = _parse_ts(end_time) if end_time else start + timedelta(days=1)

    buckets = []
    cursor = start
    while cursor < end:
        bucket_end = cursor + timedelta(days=1)
        results = []
        if True:  # Daily cost aggregates always have data if there was activity
            for project in _PROJECTS:
                results.append(
                    {
                        "project_id": project,
                        "line_item": "GPT-4o Usage",
                        "amount": {"value": "1.25", "currency": "USD"},
                        "quantity": 1000,
                    }
                )
        buckets.append(
            {
                "start_time": int(cursor.timestamp()),
                "end_time": int(bucket_end.timestamp()),
                "results": results,
            }
        )
        cursor = bucket_end

    return {
        "object": "page",
        "data": buckets,
        "has_more": False,
        "next_page": None,
    }


@openai_router.get("/v1/organization/projects")
def list_projects(
    after: str | None = Query(None),
    limit: int = Query(100, le=100),
    include_archived: bool = Query(False),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _auth(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": project_id,
                "name": f"Project {i + 1}",
                "status": "active",
                "created_at": 1729000000,
                "archived": False,
            }
            for i, project_id in enumerate(_PROJECTS)
        ],
        "first_id": _PROJECTS[0],
        "last_id": _PROJECTS[-1],
    }


@openai_router.get("/v1/organization/projects/{project_id}/api_keys")
def list_project_api_keys(
    project_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _auth(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": f"key_{i:02d}",
                "name": f"Key {i}",
                "status": "active",
                "owner_project_access": True,
                "redacted_value": f"sk-...{i:04d}",
                "last_used_at": "2026-10-14T00:00:00Z",
                "expires_at": None,
                "owner": {"type": "user", "id": "user_01"},
            }
            for i in range(1, 5)
        ],
        "first_id": "key_01",
        "last_id": "key_04",
    }
