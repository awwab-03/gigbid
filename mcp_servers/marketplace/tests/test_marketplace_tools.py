"""Marketplace MCP tools through an in-memory MCP client (A7)."""

from __future__ import annotations

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

ADMIN = {"X-Admin-Token": "gigsim-admin"}

pytestmark = pytest.mark.asyncio


async def _first_job(s):
    r = await s.call_tool("search_jobs", {"query": "dashboard", "limit": 1})
    assert not r.isError
    return r.structuredContent["jobs"][0]


async def test_tools_have_annotations_and_output_schemas(marketplace_mcp):
    async with connect(marketplace_mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    assert {"search_jobs", "create_proposal_draft", "submit_proposal", "send_message"} <= set(tools)
    for t in tools.values():
        assert t.outputSchema, t.name
        assert t.annotations is not None
    assert tools["search_jobs"].annotations.readOnlyHint is True
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["submit_proposal"].annotations.idempotentHint is True
    assert "idempotency_key" in tools["submit_proposal"].inputSchema["required"]


async def test_dry_run_previews_cost_without_writing(marketplace_mcp, gigsim_client):
    async with connect(marketplace_mcp._mcp_server) as s:
        job = await _first_job(s)
        r = await s.call_tool("create_proposal_draft", {"job_id": job["job_id"], "cover_letter": "x" * 80, "bid_amount": 300,
                                                        "bid_type": job["budget"]["type"], "idempotency_key": "dry-run-0001",
                                                        "dry_run": True})
    assert r.structuredContent["dry_run"] is True
    assert r.structuredContent["connects_cost"] == job["connects_cost"]
    assert gigsim_client.get("/admin/proposals", headers=ADMIN).json()["proposals"] == []


async def test_retried_submit_spends_connects_once(marketplace_mcp, gigsim_client):
    async with connect(marketplace_mcp._mcp_server) as s:
        job = await _first_job(s)
        d = await s.call_tool("create_proposal_draft", {"job_id": job["job_id"], "cover_letter": "y" * 80, "bid_amount": 300,
                                                        "bid_type": job["budget"]["type"], "idempotency_key": "draft-key-0001"})
        pid = d.structuredContent["proposal_id"]
        before = (await s.call_tool("get_connects_balance", {})).structuredContent["balance"]
        r1 = await s.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "submit-key-0001"})
        r2 = await s.call_tool("submit_proposal", {"proposal_id": pid, "idempotency_key": "submit-key-0001"})
        after = (await s.call_tool("get_connects_balance", {})).structuredContent["balance"]
    assert not r1.isError and not r2.isError
    assert r2.structuredContent["idempotent_replay"] is True
    assert before - after == job["connects_cost"]


async def test_invalid_arguments_are_rejected(marketplace_mcp):
    async with connect(marketplace_mcp._mcp_server) as s:
        r = await s.call_tool("create_proposal_draft", {"job_id": "j-1", "cover_letter": "short", "bid_amount": -1,
                                                        "bid_type": "fixed", "idempotency_key": "k"})
    assert r.isError


async def test_outage_is_reported_as_unavailable(marketplace_mcp, gigsim_client):
    gigsim_client.post("/admin/chaos", json={"outage": True}, headers=ADMIN)
    try:
        async with connect(marketplace_mcp._mcp_server) as s:
            r = await s.call_tool("search_jobs", {"query": "react"})
        assert r.isError
        assert "MARKETPLACE_UNAVAILABLE" in r.content[0].text
    finally:
        gigsim_client.post("/admin/chaos", json={"outage": False}, headers=ADMIN)
