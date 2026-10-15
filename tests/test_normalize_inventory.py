"""Inventory normalization: provider payloads to key_inventory rows.

Pure functions, unit-tested against fixtures. Maps both providers' inventory
shapes to a common key_inventory row shape.
"""

from monitor.collectors.normalize_inventory import (
    normalize_anthropic_key,
    normalize_anthropic_keys_payload,
    normalize_openai_key,
    normalize_openai_keys_payload,
)


class TestAnthropicKeyNormalization:
    def test_full_key_maps_every_field(self) -> None:
        key = {
            "id": "apikey_01",
            "name": "Key 1",
            "status": "active",
            "created_at": "2026-09-01T00:00:00Z",
            "created_by": {"id": "user_01", "type": "user"},
            "scope": {"type": "workspace", "workspace_id": "wrkspc_01"},
            "workspace_id": "wrkspc_01",
        }
        row = normalize_anthropic_key(key)
        assert row["provider"] == "anthropic"
        assert row["api_key_id"] == "apikey_01"
        assert row["name"] == "Key 1"
        assert row["status"] == "active"
        assert row["owner"] == "user_01"
        assert row["scope_id"] == "wrkspc_01"
        assert row["created_at"] == "2026-09-01T00:00:00Z"

    def test_payload_produces_rows(self) -> None:
        payload = {
            "data": [
                {
                    "id": "apikey_01",
                    "name": "Key 1",
                    "status": "active",
                    "created_at": "2026-09-01T00:00:00Z",
                    "created_by": {"id": "user_01", "type": "user"},
                    "scope": {"type": "workspace", "workspace_id": "wrkspc_01"},
                    "workspace_id": "wrkspc_01",
                }
            ]
        }
        rows = normalize_anthropic_keys_payload(payload)
        assert len(rows) == 1
        assert rows[0]["api_key_id"] == "apikey_01"


class TestOpenAIKeyNormalization:
    def test_full_key_maps_every_field(self) -> None:
        key = {
            "id": "key_01",
            "name": "Key 1",
            "status": "active",
            "owner_project_access": True,
            "redacted_value": "sk-...0001",
            "last_used_at": "2026-10-14T00:00:00Z",
            "expires_at": None,
            "owner": {"type": "user", "id": "user_01"},
        }
        row = normalize_openai_key(key, project_id="proj_01")
        assert row["provider"] == "openai"
        assert row["api_key_id"] == "key_01"
        assert row["name"] == "Key 1"
        assert row["status"] == "active"
        assert row["owner"] == "user_01"
        assert row["scope_id"] == "proj_01"
        assert row["last_used_at"] == "2026-10-14T00:00:00Z"

    def test_payload_produces_rows(self) -> None:
        payload = {
            "data": [
                {
                    "id": "key_01",
                    "name": "Key 1",
                    "status": "active",
                    "owner_project_access": True,
                    "redacted_value": "sk-...0001",
                    "last_used_at": "2026-10-14T00:00:00Z",
                    "expires_at": None,
                    "owner": {"type": "user", "id": "user_01"},
                }
            ]
        }
        rows = normalize_openai_keys_payload(payload, project_id="proj_01")
        assert len(rows) == 1
        assert rows[0]["api_key_id"] == "key_01"
