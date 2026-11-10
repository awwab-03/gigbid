"""GigSim backend: HTTP client with timeouts, bounded retries with jittered backoff, and 429 handling."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import random
from typing import Any

import httpx

from mcp_servers.marketplace.adapters.base import (
    Conflict,
    InsufficientConnects,
    MarketplaceError,
    MarketplaceUnavailable,
    NotFound,
    PolicyViolation,
    RateLimited,
)
from shared.security import trace_id_var


class GigSimBackend:
    name = "gigsim"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0, max_retries: int = 3):
        self.base_url = (base_url or os.getenv("GIGSIM_BASE_URL", "http://localhost:8081")).rstrip("/")
        self.secret = os.getenv("GIGSIM_SECRET", "gigsim-dev-secret")
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def _token(self, account: str) -> str:
        sig = hmac.new(self.secret.encode(), account.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{account}.{sig}"

    async def _req(self, method: str, path: str, account: str, *, key: str | None = None, **kw: Any) -> dict:
        headers = {"Authorization": f"Bearer {self._token(account)}"}
        if key:
            headers["Idempotency-Key"] = key
        if trace_id_var.get():
            headers["X-Trace-Id"] = trace_id_var.get()
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                r = await self.client.request(method, path, headers=headers, **kw)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
                last = MarketplaceUnavailable(f"GigSim unreachable: {type(e).__name__}")
            else:
                if r.status_code < 400:
                    return r.json()
                detail = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("error", r.text)
                if r.status_code == 429:
                    retry = float(r.headers.get("Retry-After", "2"))
                    last = RateLimited(f"GigSim rate limit: {detail}")
                    if attempt < self.max_retries and retry <= 10:
                        await asyncio.sleep(retry)
                        continue
                    raise last
                if r.status_code >= 500:
                    last = MarketplaceUnavailable(f"GigSim {r.status_code}: {detail}")
                elif r.status_code == 404:
                    raise NotFound(detail)
                elif r.status_code == 409:
                    raise Conflict(detail)
                elif r.status_code == 402:
                    raise InsufficientConnects(detail)
                elif r.status_code == 422:
                    raise PolicyViolation(detail)
                else:
                    raise MarketplaceError(f"GigSim {r.status_code}: {detail}")
            if attempt < self.max_retries:
                # writes are safe to retry because every write carries an idempotency key
                await asyncio.sleep(min(8.0, 0.4 * 2**attempt) * (0.5 + random.random()))
        raise last or MarketplaceUnavailable("GigSim failed")

    async def search_jobs(self, account: str, **filters: Any) -> dict:
        params = {k: v for k, v in filters.items() if v not in (None, "", [])}
        if isinstance(params.get("skills"), list):
            params["skills"] = ",".join(params["skills"])
        return await self._req("GET", "/jobs", account, params=params)

    async def get_job(self, account: str, job_id: str) -> dict:
        return await self._req("GET", f"/jobs/{job_id}", account)

    async def get_client_history(self, account: str, client_id: str) -> dict:
        return await self._req("GET", f"/clients/{client_id}", account)

    async def get_connects_balance(self, account: str) -> dict:
        return await self._req("GET", "/me/connects", account)

    async def get_pricing_stats(self, account: str, category: str, budget_type: str) -> dict:
        return await self._req("GET", "/stats/pricing", account, params={"category": category, "budget_type": budget_type})

    async def get_policy(self, account: str) -> dict:
        return await self._req("GET", "/policy", account)

    async def list_threads(self, account: str) -> dict:
        return await self._req("GET", "/threads", account)

    async def list_messages(self, account: str, thread_id: str) -> dict:
        return await self._req("GET", f"/threads/{thread_id}/messages", account)

    async def list_proposals(self, account: str, status: str | None) -> dict:
        return await self._req("GET", "/proposals", account, params={"status": status} if status else None)

    async def get_events(self, account: str, since_id: int) -> dict:
        return await self._req("GET", "/events", account, params={"since_id": since_id})

    async def create_proposal_draft(self, account: str, payload: dict, key: str, dry_run: bool) -> dict:
        return await self._req("POST", "/proposals/drafts", account, key=key, json={**payload, "dry_run": dry_run})

    async def submit_proposal(self, account: str, proposal_id: str, key: str, dry_run: bool) -> dict:
        return await self._req("POST", f"/proposals/{proposal_id}/submit", account, key=key, params={"dry_run": str(dry_run).lower()})

    async def send_message(self, account: str, thread_id: str, body: str, key: str, dry_run: bool) -> dict:
        return await self._req("POST", f"/threads/{thread_id}/messages", account, key=key, json={"body": body, "dry_run": dry_run})

    async def health(self) -> dict:
        try:
            r = await self.client.get("/health", timeout=3.0)
            data = r.json()
            return {"backend": "gigsim", "ok": r.status_code == 200 and data.get("status") == "ok", **data}
        except Exception as e:  # noqa: BLE001
            return {"backend": "gigsim", "ok": False, "error": type(e).__name__}
