"""Pure normalization: provider inventory payloads to key_inventory rows.

No I/O, no database, no HTTP. Maps both providers' inventory shapes to a
common key_inventory row shape. The provider-specific differences:
- Anthropic: created_by.id -> owner, workspace_id -> scope_id
- OpenAI: owner.id -> owner, project_id passed in -> scope_id
"""

from typing import Any


def normalize_anthropic_key(key: dict[str, Any]) -> dict[str, Any]:
    """Map one Anthropic API key to a key_inventory row."""
    created_by = key.get("created_by", {})
    return {
        "provider": "anthropic",
        "api_key_id": key["id"],
        "scope_id": key.get("workspace_id"),
        "name": key.get("name"),
        "status": key.get("status"),
        "owner": created_by.get("id"),
        "created_at": key.get("created_at"),
        "last_used_at": key.get("last_used_at"),
        "extra": {"partial_key_hint": key.get("partial_key_hint")},
    }


def normalize_anthropic_keys_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an Anthropic api_keys payload to key_inventory rows."""
    return [normalize_anthropic_key(k) for k in payload.get("data", [])]


def normalize_openai_key(key: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """Map one OpenAI API key to a key_inventory row."""
    owner = key.get("owner", {})
    return {
        "provider": "openai",
        "api_key_id": key["id"],
        "scope_id": project_id,
        "name": key.get("name"),
        "status": key.get("status"),
        "owner": owner.get("id"),
        "created_at": key.get("created_at"),
        "last_used_at": key.get("last_used_at"),
        "extra": {"redacted_value": key.get("redacted_value")},
    }


def normalize_openai_keys_payload(
    payload: dict[str, Any], project_id: str | None = None
) -> list[dict[str, Any]]:
    """Map an OpenAI project api_keys payload to key_inventory rows."""
    return [normalize_openai_key(k, project_id=project_id) for k in payload.get("data", [])]
