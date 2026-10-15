"""Probe runner: sends tiny prompts, classifies outcomes, stores results.

The probe runner uses httpx directly (no SDK auto-retries), sends a tiny
canned prompt to the cheapest suitable model, classifies the outcome, and
stores it in probe_result with latency, status, and tokens.
"""

import httpx
import pytest
from sqlalchemy import create_engine, text

from monitor.config import settings
from monitor.probes.runner import ProbeRunner


class TestProbeRunner:
    def test_probe_stores_ok_result(self, db) -> None:
        # Mock transport returns 200
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"input_tokens": 10, "output_tokens": 5},
                request=request,
            )

        with db.connect() as conn:
            runner = ProbeRunner(
                base_url="http://testserver/anthropic",
                api_key="probe-key",
                model="claude-haiku-5-5",
                transport=httpx.MockTransport(handler),
                conn=conn,
            )
            runner.probe_once()

            rows = conn.execute(text("SELECT * FROM probe_result")).fetchall()
        assert len(rows) == 1
        assert rows[0].outcome == "ok"
        assert rows[0].latency_ms is not None
        assert rows[0].input_tokens == 10
        assert rows[0].output_tokens == 5

    def test_probe_classifies_5xx_as_server_error(self, db) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, request=request)

        with db.connect() as conn:
            runner = ProbeRunner(
                base_url="http://testserver/anthropic",
                api_key="probe-key",
                model="claude-haiku-5-5",
                transport=httpx.MockTransport(handler),
                conn=conn,
            )
            runner.probe_once()

            rows = conn.execute(text("SELECT * FROM probe_result")).fetchall()
        assert len(rows) == 1
        assert rows[0].outcome == "server_error"

    def test_probe_classifies_429_as_rate_limited(self, db) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, request=request)

        with db.connect() as conn:
            runner = ProbeRunner(
                base_url="http://testserver/anthropic",
                api_key="probe-key",
                model="claude-haiku-5-5",
                transport=httpx.MockTransport(handler),
                conn=conn,
            )
            runner.probe_once()

            rows = conn.execute(text("SELECT * FROM probe_result")).fetchall()
        assert len(rows) == 1
        assert rows[0].outcome == "rate_limited"

    def test_probe_records_attempt_count(self, db) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, request=request)
            return httpx.Response(
                200,
                json={"input_tokens": 10, "output_tokens": 5},
                request=request,
            )

        with db.connect() as conn:
            runner = ProbeRunner(
                base_url="http://testserver/anthropic",
                api_key="probe-key",
                model="claude-haiku-5-5",
                transport=httpx.MockTransport(handler),
                max_retries=1,
                conn=conn,
            )
            runner.probe_once()

            rows = conn.execute(text("SELECT * FROM probe_result")).fetchall()
        assert len(rows) == 1
        assert rows[0].outcome == "ok"
        assert rows[0].attempt_count == 2


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE probe_result"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE probe_result"))
    engine.dispose()
