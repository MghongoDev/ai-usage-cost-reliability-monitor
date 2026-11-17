"""The OpenAI admin API takes Unix-second timestamps, never RFC 3339 strings."""

from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx

from monitor.collectors.openai import OpenAIUsageSource, to_unix_seconds

START = datetime(2026, 11, 4, tzinfo=UTC)
END = datetime(2026, 11, 5, tzinfo=UTC)


def _recording_source(seen: list[httpx.Request]) -> OpenAIUsageSource:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"object": "page", "data": [], "has_more": False})

    return OpenAIUsageSource(
        base_url="http://sim/openai", admin_key="k", transport=httpx.MockTransport(handler)
    )


def test_usage_request_sends_unix_seconds_for_iso_window() -> None:
    seen: list[httpx.Request] = []
    _recording_source(seen).fetch_usage((START.isoformat(), END.isoformat()))

    query = parse_qs(seen[0].url.query.decode())
    assert query["start_time"] == [str(int(START.timestamp()))]
    assert query["end_time"] == [str(int(END.timestamp()))]


def test_costs_request_sends_unix_seconds_for_iso_window() -> None:
    seen: list[httpx.Request] = []
    _recording_source(seen).fetch_costs((START.isoformat(), END.isoformat()))

    query = parse_qs(seen[0].url.query.decode())
    assert query["start_time"] == [str(int(START.timestamp()))]


def test_unix_seconds_pass_through() -> None:
    assert to_unix_seconds(1_700_000_000) == 1_700_000_000
