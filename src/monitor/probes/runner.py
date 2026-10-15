"""Probe runner: sends tiny prompts, classifies outcomes, stores results.

Uses httpx directly (no SDK auto-retries), sends a tiny canned prompt to the
cheapest suitable model, classifies the outcome, and stores it in probe_result
with latency, status, and tokens. Any retry records the attempt count.
"""

import time
from typing import Any

import httpx
from sqlalchemy import Connection, text

from monitor.probes.classify import classify_outcome

# Tiny canned prompt — just enough to exercise the API
CANNED_PROMPT = "Reply with the word 'ok'."
MAX_TOKENS = 5  # small to minimize cost


class ProbeRunner:
    """Runs canary probes against a provider's message endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 0,
        timeout: float = 30.0,
        conn: Connection | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport
        self.max_retries = max_retries
        self.timeout = timeout
        self._conn = conn

    def probe_once(self) -> dict[str, Any]:
        """Send one probe, classify the outcome, and store it."""
        headers = self._auth_headers()
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": CANNED_PROMPT}],
        }

        attempts = 0
        start = time.monotonic()
        last_status: int | None = None
        last_error: str | None = None
        input_tokens = None
        output_tokens = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                with self._client() as client:
                    resp = client.post(
                        f"{self.base_url}{self._message_path()}",
                        headers=headers,
                        json=payload,
                        timeout=self.timeout,
                    )
                last_status = resp.status_code
                if 200 <= resp.status_code < 300:
                    body = resp.json()
                    usage = body.get("usage", body)
                    input_tokens = usage.get("input_tokens")
                    output_tokens = usage.get("output_tokens")
                    break
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.ConnectError:
                last_error = "connection"
            except httpx.HTTPError:
                last_error = "network"

        latency_ms = int((time.monotonic() - start) * 1000)
        outcome = classify_outcome(last_status, last_error)

        result = {
            "provider": self._provider(),
            "probed_at": "now()",
            "outcome": outcome,
            "latency_ms": latency_ms,
            "status_code": last_status,
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "attempt_count": attempts,
        }

        if self._conn is not None:
            self._store(result)

        return result

    def _client(self) -> httpx.Client:
        return httpx.Client(transport=self._transport, timeout=self.timeout)

    def _auth_headers(self) -> dict[str, str]:
        if self._provider() == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        return {
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _message_path(self) -> str:
        if self._provider() == "anthropic":
            return "/v1/messages"
        return "/v1/chat/completions"

    def _provider(self) -> str:
        return "anthropic" if "anthropic" in self.base_url else "openai"

    def _store(self, result: dict[str, Any]) -> None:
        assert self._conn is not None
        self._conn.execute(
            text(
                """
                INSERT INTO probe_result (
                    provider, probed_at, outcome, latency_ms, status_code,
                    model, input_tokens, output_tokens, attempt_count
                ) VALUES (
                    :provider, :probed_at, :outcome, :latency_ms, :status_code,
                    :model, :input_tokens, :output_tokens, :attempt_count
                )
                """
            ),
            result,
        )
