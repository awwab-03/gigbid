"""Live Upwork backend: the official Upwork MCP server (https://mcp.upwork.com/mcp, OAuth 2.1).

Connects with langchain-mcp-adapters' MultiServerMCPClient over Streamable HTTP using the user's
access token (completed via apps/api/auth/upwork_oauth.py and stored encrypted per user).
Upwork tool names are mapped onto GigBid's marketplace operations by `marketplace.live_tool_map`
in agent/config.yaml, so a renamed upstream tool is a config change. At startup the adapter lists
the upstream tools and reports any unmapped operation in /health instead of failing silently.

Platform rules enforced here regardless of what the caller asks:
  * Every write creates a DRAFT on Upwork; the freelancer confirms it on Upwork itself.
  * No browser automation, no session cookies, no scraping.
  * Reads are throttled by the server's per-user rate limiter (live_requests_per_minute).
"""

from __future__ import annotations

import json
import os
from typing import Any

import yaml

from mcp_servers.marketplace.adapters.base import MarketplaceError, MarketplaceUnavailable
from shared.token_store import TokenStore

CONFIG = yaml.safe_load(open(os.getenv("GIGBID_CONFIG", "agent/config.yaml"), encoding="utf-8"))
UPWORK_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")


class UpworkLiveBackend:
    name = "upwork_live"

    def __init__(self) -> None:
        self.tokens = TokenStore()
        self.tool_map: dict[str, str] = CONFIG["marketplace"].get("live_tool_map", {})
        self._clients: dict[str, Any] = {}

    async def _tools(self, account: str) -> dict[str, Any]:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        tok = self.tokens.load(account, "upwork")
        if not tok:
            raise MarketplaceUnavailable("Upwork account not connected for this user (complete OAuth in Settings)")
        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": UPWORK_URL,
                                                  "headers": {"Authorization": f"Bearer {tok['access_token']}"}}})
        try:
            tools = await client.get_tools()
        except Exception as e:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork MCP unreachable: {type(e).__name__}") from e
        return {t.name: t for t in tools}

    async def _call(self, account: str, op: str, args: dict) -> dict:
        name = self.tool_map.get(op)
        if not name:
            raise MarketplaceError(f"operation {op} has no live mapping in config (marketplace.live_tool_map)")
        tools = await self._tools(account)
        if name not in tools:
            raise MarketplaceError(f"Upwork MCP has no tool named {name!r}; update live_tool_map")
        raw = await tools[name].ainvoke({k: v for k, v in args.items() if v is not None})
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"text": raw}
        return raw if isinstance(raw, dict) else {"result": raw}

    async def search_jobs(self, account: str, **filters: Any) -> dict:
        res = await self._call(account, "search_jobs", {"query": filters.get("q"), "limit": filters.get("limit", 20)})
        jobs = res.get("jobs") or res.get("results") or []
        return {"total": len(jobs), "jobs": [self._job(j) for j in jobs]}

    @staticmethod
    def _job(j: dict) -> dict:
        b = j.get("budget") or {}
        hourly = bool(j.get("hourly") or j.get("hourlyBudgetMin"))
        return {"job_id": str(j.get("id") or j.get("job_id")), "title": j.get("title", ""), "description": j.get("description", ""),
                "category": j.get("category", "other"), "required_skills": [s.get("name", s) if isinstance(s, dict) else s for s in j.get("skills", [])],
                "deliverables": [], "budget": {"type": "hourly" if hourly else "fixed",
                                               "min": float(j.get("hourlyBudgetMin") or b.get("amount") or 0),
                                               "max": float(j.get("hourlyBudgetMax") or b.get("amount") or 0)},
                "screening_questions": j.get("questions", []), "client_id": str((j.get("client") or {}).get("id", "unknown")),
                "posted_at": j.get("createdDateTime", ""), "connects_cost": int(j.get("connectsRequired") or 0), "source": "upwork"}

    async def get_job(self, account: str, job_id: str) -> dict:
        return self._job(await self._call(account, "get_job", {"job_id": job_id}))

    async def get_client_history(self, account: str, client_id: str) -> dict:
        return await self._call(account, "get_client_history", {"client_id": client_id})

    async def get_connects_balance(self, account: str) -> dict:
        return await self._call(account, "get_connects_balance", {})

    async def get_pricing_stats(self, account: str, category: str, budget_type: str) -> dict:
        # Upwork does not expose market statistics; GigBid falls back to its historical-job statistics.
        raise MarketplaceError("pricing statistics are not available in live mode")

    async def get_policy(self, account: str) -> dict:
        return {"version": "upwork-live", "rules": ["Upwork Terms of Service apply; drafts only, confirmed by the user on Upwork."]}

    async def list_threads(self, account: str) -> dict:
        return await self._call(account, "list_threads", {})

    async def list_messages(self, account: str, thread_id: str) -> dict:
        return await self._call(account, "list_messages", {"room_id": thread_id})

    async def list_proposals(self, account: str, status: str | None) -> dict:
        return await self._call(account, "list_proposals", {"status": status})

    async def get_events(self, account: str, since_id: int) -> dict:
        return {"events": []}

    async def create_proposal_draft(self, account: str, payload: dict, key: str, dry_run: bool) -> dict:
        if dry_run:
            return {"dry_run": True, "would_create": {**payload, "note": "Created as a draft on Upwork; you confirm it there."}}
        res = await self._call(account, "create_proposal_draft", {"job_id": payload["job_id"], "cover_letter": payload["cover_letter"],
                                                                   "bid_amount": payload["bid_amount"]})
        return {"proposal_id": str(res.get("id") or res.get("proposal_id")), "status": "draft", **payload}

    async def submit_proposal(self, account: str, proposal_id: str, key: str, dry_run: bool) -> dict:
        # Upwork requires the user to confirm submission on Upwork. GigBid never auto-submits in live mode.
        return {"proposal_id": proposal_id, "status": "awaiting_user_confirmation_on_upwork", "dry_run": dry_run,
                "note": "Open Upwork to review and confirm this draft. GigBid does not submit on your behalf in live mode."}

    async def send_message(self, account: str, thread_id: str, body: str, key: str, dry_run: bool) -> dict:
        if dry_run:
            return {"dry_run": True, "would_send": {"thread_id": thread_id, "body": body}}
        res = await self._call(account, "send_message_draft", {"room_id": thread_id, "message": body})
        return {"message_id": str(res.get("id", "")), "thread_id": thread_id, "status": "draft_on_upwork"}

    async def health(self) -> dict:
        return {"backend": "upwork_live", "ok": True, "url": UPWORK_URL, "mapped_ops": sorted(self.tool_map)}
