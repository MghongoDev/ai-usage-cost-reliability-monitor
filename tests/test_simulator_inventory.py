"""The simulator serves inventory endpoints for both providers.

Anthropic: cursor pagination with after_id, status filter, include_default.
OpenAI: list-style with after cursor, limit, include_archived.
"""

from fastapi.testclient import TestClient

from monitor.simulator.app import create_app


class TestAnthropicInventory:
    def test_api_keys_returns_cursor_pagination(self) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/anthropic/v1/organizations/api_keys",
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) > 0
        key = body["data"][0]
        assert "id" in key
        assert "name" in key
        assert "status" in key
        assert "partial_key_hint" in key
        assert "first_id" in body
        assert "has_more" in body

    def test_api_keys_requires_auth(self) -> None:
        client = TestClient(create_app())
        resp = client.get("/anthropic/v1/organizations/api_keys")
        assert resp.status_code == 401

    def test_workspaces_includes_default_when_requested(self) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/anthropic/v1/organizations/workspaces",
            params={"include_default": "true"},
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        # Default workspace has a real ID but null workspace_id in reports
        default = [w for w in body["data"] if w.get("is_default")]
        assert len(default) >= 1


class TestOpenAIInventory:
    def test_projects_returns_list_envelope(self) -> None:
        client = TestClient(create_app())
        resp = client.get(
            "/openai/v1/organization/projects",
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert "data" in body
        assert len(body["data"]) > 0
        project = body["data"][0]
        assert "id" in project
        assert "name" in project

    def test_project_api_keys_returns_keys(self) -> None:
        client = TestClient(create_app())
        # First get a project ID
        projects = client.get(
            "/openai/v1/organization/projects",
            headers={"Authorization": "Bearer test-key"},
        ).json()
        project_id = projects["data"][0]["id"]

        resp = client.get(
            f"/openai/v1/organization/projects/{project_id}/api_keys",
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) > 0
        key = body["data"][0]
        assert "id" in key
        assert "name" in key
        assert "last_used_at" in key

    def test_projects_requires_auth(self) -> None:
        client = TestClient(create_app())
        resp = client.get("/openai/v1/organization/projects")
        assert resp.status_code == 401
