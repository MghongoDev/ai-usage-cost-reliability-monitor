"""Normalization: OpenAI usage payload to usage_fact rows.

Pure functions, unit-tested against fixtures. The OpenAI shape differs from
Anthropic: Unix-second timestamps, a page envelope with next_page cursor,
and input_cache_write_tokens as a separate field (not nested).
"""

from monitor.collectors.normalize_openai import normalize_openai_usage


class TestNormalizeOpenAIUsage:
    def test_full_row_maps_every_token_class(self) -> None:
        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 1729003600,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": "key_01",
                            "model": "gpt-4o",
                            "input_uncached_tokens": 1000,
                            "input_cached_tokens": 200,
                            "input_cache_write_tokens": 50,
                            "output_tokens": 500,
                            "num_model_requests": 10,
                        }
                    ],
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        rows, unknown = normalize_openai_usage(payload, bucket_width="1h")
        assert len(rows) == 1
        row = rows[0]
        assert row["provider"] == "openai"
        assert row["bucket_start"] == "2024-10-15T13:46:40+00:00"
        assert row["bucket_width"] == "1h"
        assert row["scope_id"] == "proj_01"
        assert row["api_key_id"] == "key_01"
        assert row["model"] == "gpt-4o"
        assert row["input_uncached"] == 1000
        assert row["input_cached"] == 200
        assert row["cache_creation"] == 50
        assert row["output_tokens"] == 500
        assert row["requests"] == 10

    def test_null_api_key_for_unattributed_usage(self) -> None:
        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 1729003600,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": None,
                            "model": "gpt-4o",
                            "input_uncached_tokens": 10,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 0,
                            "output_tokens": 5,
                            "num_model_requests": 1,
                        }
                    ],
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        rows, _ = normalize_openai_usage(payload, bucket_width="1h")
        assert rows[0]["api_key_id"] is None

    def test_multiple_buckets_produce_multiple_rows(self) -> None:
        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 1729003600,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": "key_01",
                            "model": "gpt-4o",
                            "input_uncached_tokens": 100,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 0,
                            "output_tokens": 50,
                            "num_model_requests": 5,
                        }
                    ],
                },
                {
                    "start_time": 1729003600,
                    "end_time": 1729007200,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": "key_01",
                            "model": "gpt-4o",
                            "input_uncached_tokens": 200,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 0,
                            "output_tokens": 80,
                            "num_model_requests": 8,
                        }
                    ],
                },
            ],
            "has_more": False,
            "next_page": None,
        }
        rows, _ = normalize_openai_usage(payload, bucket_width="1h")
        assert len(rows) == 2
        assert rows[0]["bucket_start"] == "2024-10-15T13:46:40+00:00"
        assert rows[1]["bucket_start"] == "2024-10-15T14:46:40+00:00"

    def test_missing_required_field_raises(self) -> None:
        import pytest
        from pydantic import ValidationError

        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 1729003600,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": "key_01",
                            # model is missing
                            "input_uncached_tokens": 100,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 0,
                            "output_tokens": 50,
                            "num_model_requests": 5,
                        }
                    ],
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        with pytest.raises(ValidationError):
            normalize_openai_usage(payload, bucket_width="1h")

    def test_unknown_fields_are_counted(self) -> None:
        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 1729003600,
                    "results": [
                        {
                            "project_id": "proj_01",
                            "api_key_id": "key_01",
                            "model": "gpt-4o",
                            "input_uncached_tokens": 100,
                            "input_cached_tokens": 0,
                            "input_cache_write_tokens": 0,
                            "output_tokens": 50,
                            "num_model_requests": 5,
                            "some_new_field": "value",
                        }
                    ],
                }
            ],
            "has_more": False,
            "next_page": None,
        }
        rows, unknown = normalize_openai_usage(payload, bucket_width="1h")
        assert unknown > 0
        assert rows[0]["extra"]["some_new_field"] == "value"
