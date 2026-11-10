"""Test fixtures: an in-process GigSim and in-memory MCP client sessions (no servers needed)."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("GIGSIM_DB", os.path.join(tempfile.mkdtemp(), "gigsim_test.sqlite"))
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RATE_LIMIT", "100000")
os.environ.setdefault("MCP_STATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("DEFAULT_ACCOUNT", "ml_engineer")

import httpx  # noqa: E402
import pytest  # noqa: E402

ADMIN = {"X-Admin-Token": "gigsim-admin"}


@pytest.fixture()
def gigsim_client():
    from fastapi.testclient import TestClient

    from gigsim.app import app

    c = TestClient(app)
    c.post("/admin/reset", headers=ADMIN)
    c.post("/admin/chaos", json={"error_rate": 0, "outage": False}, headers=ADMIN)
    return c


@pytest.fixture()
def marketplace_mcp(gigsim_client):
    """Marketplace MCP server wired to an in-process GigSim through httpx's ASGI transport."""
    from gigsim.app import app as gs_app
    from mcp_servers.marketplace import server
    from mcp_servers.marketplace.adapters.gigsim import GigSimBackend

    server.backend = GigSimBackend(client=httpx.AsyncClient(transport=httpx.ASGITransport(app=gs_app), base_url="http://gigsim"),
                                   max_retries=1)
    return server.mcp
