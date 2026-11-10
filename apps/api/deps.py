"""Shared API helpers: the per-user marketplace toolbox and degraded-mode detection."""

from __future__ import annotations

from agent.mcp_client import Toolbox, ToolError, ToolUnavailable


def ui_tools(user: dict) -> Toolbox:
    return Toolbox("ui", user["id"], user["account"])


async def safe_call(user: dict, tool: str, args: dict | None = None) -> tuple[dict | None, str | None]:
    """Returns (result, None) or (None, message) when the marketplace is unavailable (UI banner)."""
    try:
        return await ui_tools(user).call(tool, args or {}), None
    except ToolUnavailable as e:
        return None, f"Marketplace unavailable: {e}. Work is queued and will resume automatically."
    except ToolError as e:
        return None, str(e)
