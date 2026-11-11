"""MCP client setup with per-agent tool allowlists (A6).

Two transports, same interface:
  * http  - langchain-mcp-adapters MultiServerMCPClient over Streamable HTTP, with a signed
            service token (user + marketplace account) and the run's X-Trace-Id header
  * inproc - in-memory sessions to the same FastMCP servers (evals, tests, single-process dev)

Discipline: every agent gets only the tools in `tool_allowlist` (filtered by "server.tool" name),
each call has a timeout and bounded retries with backoff, and MARKETPLACE_UNAVAILABLE errors are
raised as `ToolUnavailable` so the graph can switch to degraded mode (queue + UI banner).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from contextlib import AsyncExitStack
from typing import Any

from agent.llm import CFG
from shared.security import sign_service_token, trace_id_var


class ToolUnavailable(RuntimeError):
    """The upstream system behind a tool is down; the work should be queued, not failed."""


class ToolError(RuntimeError):
    pass


def _url(server: str) -> str:
    s = CFG["mcp"]["servers"][server]
    return os.getenv(s["url_env"], s["default"])


class Toolbox:
    """Tools for ONE agent, for one user/account, filtered by the allowlist."""

    def __init__(self, agent: str, user_id: str, account: str, transport: str | None = None):
        self.agent = agent
        self.user_id = user_id
        self.account = account
        self.allowed = set(CFG["tool_allowlist"].get(agent, []))
        self.transport = transport or os.getenv("MCP_TRANSPORT", "http")
        # GIGBID_TIMEOUT_SCALE also stretches tool calls on slow hosts (the 1 GB deploy VM runs the cross-encoder on a fraction of a CPU)
        self.timeout = float(CFG["mcp"]["timeout_s"]) * float(os.getenv("GIGBID_TIMEOUT_SCALE", "1"))
        self.retries = int(CFG["mcp"]["max_retries"])

    def allows(self, qualified: str) -> bool:
        return qualified in self.allowed

    async def call(self, qualified: str, args: dict[str, Any] | None = None) -> dict:
        if not self.allows(qualified):
            raise PermissionError(f"agent '{self.agent}' may not call {qualified} (tool_allowlist)")
        server, tool = qualified.split(".", 1)
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return await asyncio.wait_for(self._call_once(server, tool, args or {}), timeout=self.timeout)
            except ToolError as e:
                msg = str(e)
                if "MARKETPLACE_UNAVAILABLE" in msg or "RATE_LIMITED" in msg:
                    last = ToolUnavailable(msg)
                else:
                    raise
            except (asyncio.TimeoutError, OSError, ConnectionError) as e:
                last = ToolUnavailable(f"{qualified} timed out or unreachable: {type(e).__name__}")
            except Exception as e:  # noqa: BLE001 - httpx/anyio connection failures surface as varied types
                if "connect" in type(e).__name__.lower() or "connect" in str(e).lower():
                    last = ToolUnavailable(f"{server} MCP server unreachable: {type(e).__name__}")
                else:
                    raise
            if attempt < self.retries:
                await asyncio.sleep(min(4.0, 0.5 * 2**attempt) * (0.5 + random.random()))
        raise last or ToolUnavailable(qualified)

    async def _call_once(self, server: str, tool: str, args: dict) -> dict:
        if self.transport == "inproc":
            return await _inproc_call(server, tool, args, self.account)
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {sign_service_token(self.user_id, self.account)}"}
        if trace_id_var.get():
            headers["X-Trace-Id"] = trace_id_var.get()
        async with AsyncExitStack() as stack:
            read, write, _ = await stack.enter_async_context(streamablehttp_client(_url(server), headers=headers))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            res = await session.call_tool(tool, args)
        return _result(res)


def _result(res) -> dict:
    if res.isError:
        raise ToolError(" ".join(getattr(c, "text", "") for c in res.content))
    if res.structuredContent is not None:
        return res.structuredContent
    txt = " ".join(getattr(c, "text", "") for c in res.content)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return {"text": txt}


async def _inproc_call(server: str, tool: str, args: dict, account: str) -> dict:
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    from mcp_servers.common import caller_var

    mod = __import__(f"mcp_servers.{server}.server", fromlist=["mcp"])
    token = caller_var.set(("inproc", account))
    try:
        async with connect(mod.mcp._mcp_server) as s:
            return _result(await s.call_tool(tool, args))
    finally:
        caller_var.reset(token)


async def langchain_tools(agent: str | None, user_id: str, account: str, servers: list[str] | None = None):
    """LangChain tools (for the single-agent ReAct and supervisor baselines), filtered by allowlist.
    agent=None returns every tool (the 'one agent holding all tools' baseline)."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    servers = servers or ["portfolio", "marketplace", "workspace"]
    headers = {"Authorization": f"Bearer {sign_service_token(user_id, account)}"}
    client = MultiServerMCPClient({s: {"transport": "streamable_http", "url": _url(s), "headers": headers} for s in servers})
    tools = await client.get_tools()
    if agent is None:
        return tools
    allowed = {q.split(".", 1)[1] for q in CFG["tool_allowlist"].get(agent, [])}
    return [t for t in tools if t.name in allowed]
