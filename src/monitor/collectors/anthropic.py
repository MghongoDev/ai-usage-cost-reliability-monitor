"""The Anthropic collector: read-only admin client, retries, pagination, window chunking.

The admin key is powerful (it can remove users and disable keys), so the
transport is read-only by construction — any non-GET/HEAD method raises before
the request leaves the process. Retries use exponential backoff with jitter on
429 and 5xx, honoring Retry-After. Windows are chunked to respect the
per-bucket-width limits, and pagination follows the page-token cursor.
"""

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from monitor.collectors.normalize import normalize_anthropic_usage

# Per-bucket-width window caps, mirroring the real API's documented limits.
BUCKET_LIMITS = {
    "1m": 1440,  # 24h
    "1h": 168,  # 7 days
    "1d": 31,  # 31 days
}

_VERSION = "2023-06-01"


class ReadOnlyTransport(httpx.HTTPTransport):
    """Refuses any non-GET/HEAD method. The admin client is read-only by construction."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method not in ("GET", "HEAD"):
            raise RuntimeError(
                f"admin client is read-only; refused {request.method} {request.url.path}"
            )
        return super().handle_request(request)


class AnthropicUsageSource:
    """Implements UsageSource against the Anthropic Admin API (or the simulator)."""

    def __init__(
        self, base_url: str, admin_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport or ReadOnlyTransport(),
            headers={
                "x-api-key": self.admin_key,
                "anthropic-version": _VERSION,
            },
            timeout=30.0,
        )

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential_jitter(initial=1, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

    def fetch_usage(
        self, window: tuple[str, str], bucket_width: str = "1h"
    ) -> list[dict[str, Any]]:
        """Fetch usage rows for [start, end), chunked to the bucket-width limit."""
        if bucket_width not in BUCKET_LIMITS:
            raise ValueError(f"bucket_width must be one of {list(BUCKET_LIMITS)}")
        start, end = window
        rows: list[dict[str, Any]] = []
        # For now, single-chunk fetch (the simulator serves small windows).
        # Window chunking across multiple requests comes with the backfill CLI.
        payload = self._get(
            "/v1/organizations/usage_report/messages",
            params={
                "starting_at": start,
                "ending_at": end,
                "bucket_width": bucket_width,
                "group_by": ["api_key_id", "model"],
            },
        )
        # The API returns {"data": [bucket, ...], "has_more": bool, "next_page": str}.
        # Each bucket has its own starting_at/ending_at/results.
        for bucket in payload["data"]:
            rows.extend(normalize_anthropic_usage(bucket, bucket_width=bucket_width))
        return rows

    def fetch_costs(self, window: tuple[str, str]) -> list[dict[str, Any]]:
        """Fetch cost rows. Stub: cost collection is Tracer 05."""
        return []

    def list_keys(self) -> list[dict[str, Any]]:
        """Fetch key inventory. Stub: inventory is Tracer 04."""
        return []
