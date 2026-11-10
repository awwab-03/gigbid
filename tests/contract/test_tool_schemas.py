"""MCP tool-schema snapshot test (A7): fails CI when a tool signature changes unintentionally.

Regenerate deliberately with:  UPDATE_SNAPSHOTS=1 pytest tests/contract
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

SNAP = Path(__file__).parent / "snapshots"
pytestmark = pytest.mark.asyncio


def _servers():
    from mcp_servers.marketplace.server import mcp as marketplace
    from mcp_servers.portfolio.server import mcp as portfolio
    from mcp_servers.workspace.server import mcp as workspace

    return {"marketplace": marketplace, "portfolio": portfolio, "workspace": workspace}


@pytest.mark.parametrize("name", ["marketplace", "portfolio", "workspace"])
async def test_tool_schemas_match_snapshot(name):
    server = _servers()[name]
    async with connect(server._mcp_server) as s:
        tools = (await s.list_tools()).tools
    current = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                        "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
               for t in sorted(tools, key=lambda t: t.name)}
    path = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAP.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert current == expected, f"{name} tool schemas changed; if intended, rerun with UPDATE_SNAPSHOTS=1"
