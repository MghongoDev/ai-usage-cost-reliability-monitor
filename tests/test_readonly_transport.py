"""The admin client is read-only by construction.

The guide demands a test that proves the transport refuses a non-GET/HEAD
method. This is the security boundary: the admin key can remove users and
disable keys, so the collector must never be able to issue a write.
"""

from unittest.mock import patch

import httpx
import pytest

from monitor.collectors.anthropic import ReadOnlyTransport


def _dummy_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, request=request)


def test_get_passes_through() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("GET", "http://example.com/v1/organizations/usage_report/messages")
    with patch.object(httpx.HTTPTransport, "handle_request", return_value=_dummy_response(request)):
        resp = transport.handle_request(request)
    assert resp.status_code == 200


def test_head_passes_through() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("HEAD", "http://example.com/v1/organizations/usage_report/messages")
    with patch.object(httpx.HTTPTransport, "handle_request", return_value=_dummy_response(request)):
        resp = transport.handle_request(request)
    assert resp.status_code == 200


def test_post_is_refused() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("POST", "http://example.com/v1/organizations/usage_report/messages")
    with pytest.raises(RuntimeError, match="read-only"):
        transport.handle_request(request)


def test_put_is_refused() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("PUT", "http://example.com/v1/organizations/api_keys")
    with pytest.raises(RuntimeError, match="read-only"):
        transport.handle_request(request)


def test_delete_is_refused() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("DELETE", "http://example.com/v1/organizations/api_keys/apikey_01")
    with pytest.raises(RuntimeError, match="read-only"):
        transport.handle_request(request)


def test_patch_is_refused() -> None:
    transport = ReadOnlyTransport()
    request = httpx.Request("PATCH", "http://example.com/v1/organizations/api_keys/apikey_01")
    with pytest.raises(RuntimeError, match="read-only"):
        transport.handle_request(request)
