"""OpenAI-shaped simulator endpoints.

Added in Tracer 03; the router is a stub here so the app imports cleanly.
"""

from typing import Any

from fastapi import APIRouter

openai_router = APIRouter()


@openai_router.get("/v1/organization/usage/completions")
def usage_completions() -> dict[str, Any]:
    return {"object": "page", "data": [], "has_more": False, "next_page": None}
