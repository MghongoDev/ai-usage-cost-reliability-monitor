"""Normalization: Anthropic usage-report payload to usage_fact rows.

Pure functions, unit-tested against fixtures. The simulator serves payloads in
this exact shape; the collector parses them here. Keeping this pure means the
mapping is testable without a database or a running simulator.
"""

from monitor.collectors.normalize import normalize_anthropic_usage


class TestNormalizeAnthropicUsage:
    def test_full_row_maps_every_token_class(self) -> None:
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": "apikey_01",
                            "workspace_id": "wrkspc_01",
                            "model": "claude-opus-5-5",
                            "uncached_input_tokens": 1000,
                            "cache_read_input_tokens": 200,
                            "output_tokens": 500,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 50,
                                "ephemeral_1h_input_tokens": 10,
                            },
                            "server_tool_use": {"web_search_requests": 3},
                        }
                    ],
                }
            ]
        }
        rows, unknown = normalize_anthropic_usage(payload, bucket_width="1h")
        assert len(rows) == 1
        row = rows[0]
        assert row["provider"] == "anthropic"
        assert row["bucket_start"] == "2026-10-14T10:00:00Z"
        assert row["bucket_width"] == "1h"
        assert row["scope_id"] == "wrkspc_01"
        assert row["api_key_id"] == "apikey_01"
        assert row["model"] == "claude-opus-5-5"
        assert row["input_uncached"] == 1000
        assert row["input_cached"] == 200
        # cache creation is the sum of the 5m and 1h buckets
        assert row["cache_creation"] == 60
        assert row["output_tokens"] == 500
        assert row["extra"]["server_tool_use"]["web_search_requests"] == 3

    def test_console_usage_has_null_api_key(self) -> None:
        # Playground/Console usage reports api_key_id as null even when
        # grouping by api_key_id. The row must store, not crash.
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": None,
                            "workspace_id": "wrkspc_01",
                            "model": "claude-sonnet-5",
                            "uncached_input_tokens": 10,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 5,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        }
                    ],
                }
            ]
        }
        rows, unknown = normalize_anthropic_usage(payload, bucket_width="1h")
        assert rows[0]["api_key_id"] is None

    def test_default_workspace_has_null_scope(self) -> None:
        # The Default Workspace reports workspace_id as null.
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": "apikey_01",
                            "workspace_id": None,
                            "model": "claude-haiku-5-5",
                            "uncached_input_tokens": 5,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 2,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        }
                    ],
                }
            ]
        }
        rows, unknown = normalize_anthropic_usage(payload, bucket_width="1h")
        assert rows[0]["scope_id"] is None

    def test_multiple_results_produce_multiple_rows(self) -> None:
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": "apikey_01",
                            "workspace_id": "wrkspc_01",
                            "model": "claude-opus-5-5",
                            "uncached_input_tokens": 100,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 50,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        },
                        {
                            "api_key_id": "apikey_02",
                            "workspace_id": "wrkspc_01",
                            "model": "claude-sonnet-5",
                            "uncached_input_tokens": 200,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 80,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        },
                    ],
                }
            ]
        }
        rows, unknown = normalize_anthropic_usage(payload, bucket_width="1h")
        assert len(rows) == 2
        assert rows[0]["api_key_id"] == "apikey_01"
        assert rows[1]["api_key_id"] == "apikey_02"

    def test_missing_required_field_raises(self) -> None:
        # Strict parsing: a payload missing a required field must fail loudly,
        # not silently produce a bad row.
        import pytest
        from pydantic import ValidationError

        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": "apikey_01",
                            "workspace_id": "wrkspc_01",
                            # model is missing
                            "uncached_input_tokens": 100,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 50,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                        }
                    ],
                }
            ]
        }
        with pytest.raises(ValidationError):
            normalize_anthropic_usage(payload, bucket_width="1h")

    def test_unknown_fields_are_counted(self) -> None:
        # Schema drift: a field the model doesn't define is captured in extra
        # and counted, not silently dropped.
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T10:00:00Z",
                    "ending_at": "2026-10-14T11:00:00Z",
                    "results": [
                        {
                            "api_key_id": "apikey_01",
                            "workspace_id": "wrkspc_01",
                            "model": "claude-opus-5-5",
                            "uncached_input_tokens": 100,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 50,
                            "cache_creation": {
                                "ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 0,
                            },
                            "some_new_field": "value",
                        }
                    ],
                }
            ]
        }
        rows, unknown = normalize_anthropic_usage(payload, bucket_width="1h")
        assert unknown > 0
        assert rows[0]["extra"]["some_new_field"] == "value"
