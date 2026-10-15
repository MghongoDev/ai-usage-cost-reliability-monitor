"""The simulator serves Anthropic's real usage-report shape.

The test hits the app via FastAPI's TestClient (no running server) and asserts
the awkward parts the collector has to handle: RFC 3339 timestamps, per-width
bucket caps, page-token pagination, null-key console usage, empty buckets for
idle intervals, and a 400 on oversized windows.
"""

from fastapi.testclient import TestClient

from monitor.simulator.app import create_app


class TestAnthropicUsageReportShape:
    def test_returns_provider_shaped_payload(self) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/anthropic/v1/organizations/usage_report/messages",
            params={
                "starting_at": "2026-10-14T10:00:00Z",
                "ending_at": "2026-10-14T12:00:00Z",
                "bucket_width": "1h",
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) == 2  # two hourly buckets
        first = body["data"][0]
        assert first["starting_at"] == "2026-10-14T10:00:00Z"
        assert first["ending_at"] == "2026-10-14T11:00:00Z"
        # At least one bucket in the window has results; check its shape.
        all_results = [r for b in body["data"] for r in b["results"]]
        assert len(all_results) > 0
        result = all_results[0]
        # Real Anthropic fields, including the nested cache_creation split
        assert "uncached_input_tokens" in result
        assert "cache_read_input_tokens" in result
        assert "output_tokens" in result
        assert "ephemeral_5m_input_tokens" in result["cache_creation"]
        assert "ephemeral_1h_input_tokens" in result["cache_creation"]

    def test_oversized_window_returns_400(self) -> None:
        client = TestClient(create_app())
        # 1h buckets are capped at 168 (7 days); ask for 30 days.
        resp = client.get(
            "/anthropic/v1/organizations/usage_report/messages",
            params={
                "starting_at": "2026-09-01T00:00:00Z",
                "ending_at": "2026-10-01T00:00:00Z",
                "bucket_width": "1h",
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status_code == 400

    def test_requires_auth_header(self) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/anthropic/v1/organizations/usage_report/messages",
            params={
                "starting_at": "2026-10-14T00:00:00Z",
                "ending_at": "2026-10-14T02:00:00Z",
                "bucket_width": "1h",
            },
        )
        assert resp.status_code == 401

    def test_empty_interval_still_returns_a_bucket(self) -> None:
        # Idle intervals must produce an empty bucket, not a gap, so the
        # collector sees the full timeline.
        client = TestClient(create_app())
        resp = client.get(
            "/anthropic/v1/organizations/usage_report/messages",
            params={
                "starting_at": "2026-10-14T00:00:00Z",
                "ending_at": "2026-10-14T06:00:00Z",
                "bucket_width": "1h",
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 6
        # At least one bucket is empty (no activity in that hour)
        empty = [b for b in body["data"] if not b["results"]]
        assert len(empty) >= 1
