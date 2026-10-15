"""The simulator: a FastAPI app that mimics both providers' admin and message endpoints.

It exists so the whole system runs from a fresh clone with no vendor keys. It
behaves like the real APIs on the awkward parts the collector has to handle:
auth headers, per-bucket-width window limits, page-token pagination, empty
buckets for idle intervals, and null dimensions for console/default-scope usage.
"""

from fastapi import FastAPI

from monitor.simulator.anthropic import anthropic_router
from monitor.simulator.openai import openai_router

__all__ = ["create_app"]


def create_app() -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI(title="AI Usage Monitor Simulator")
    app.include_router(anthropic_router, prefix="/anthropic")
    app.include_router(openai_router, prefix="/openai")
    return app
