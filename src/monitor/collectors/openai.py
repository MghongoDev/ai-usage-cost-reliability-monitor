"""The OpenAI collector: same UsageSource interface, OpenAI's shape.

The design test: adding this provider required zero changes to the
UsageSource interface. Only the auth header, endpoint path, and normalize
function differ from Anthropic.
"""

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from monitor.collectors.anthropic import ReadOnlyTransport
from monitor.collectors.constants import BUCKET_LIMITS
from monitor.collectors.normalize_openai import normalize_openai_usage


class OpenAIUsageSource:
    """Implements UsageSource against the OpenAI Admin API (or the simulator)."""

    def __init__(
        self, base_url: str, admin_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self._transport = transport
        self.last_raw_response: dict[str, Any] | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport or ReadOnlyTransport(),
            headers={
                "Authorization": f"Bearer {self.admin_key}",
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
            self.last_raw_response = result
            return result

    def fetch_usage(
        self, window: tuple[str | int, str | int], bucket_width: str = "1h"
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch usage rows for [start, end), paginated via next_page."""
        if bucket_width not in BUCKET_LIMITS:
            raise ValueError(f"bucket_width must be one of {list(BUCKET_LIMITS)}")
        start, end = window

        all_rows: list[dict[str, Any]] = []
        total_unknown = 0
        page: str | None = None
        while True:
            params: dict[str, Any] = {
                "start_time": start,
                "end_time": end,
                "bucket_width": bucket_width,
                "group_by": ["project_id", "api_key_id", "model"],
            }
            if page:
                params["page"] = page
            payload = self._get("/v1/organization/usage/completions", params)
            page_rows, unknown = normalize_openai_usage(payload, bucket_width=bucket_width)
            all_rows.extend(page_rows)
            total_unknown += unknown
            if not payload.get("has_more"):
                break
            page = payload.get("next_page")
            if not page:
                break
        return all_rows, total_unknown

    def fetch_costs(self, window: tuple[str, str]) -> list[dict[str, Any]]:
        """Fetch cost rows. Stub: cost collection is Tracer 05."""
        return []

    def list_keys(self) -> list[dict[str, Any]]:
        """Fetch key inventory. Stub: inventory is Tracer 04."""
        return []
