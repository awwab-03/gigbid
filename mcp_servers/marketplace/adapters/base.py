"""Backend interface the Marketplace MCP server delegates to (GigSim or live Upwork)."""

from __future__ import annotations

from typing import Any, Protocol


class MarketplaceError(Exception):
    code = "MARKETPLACE_ERROR"


class MarketplaceUnavailable(MarketplaceError):
    code = "MARKETPLACE_UNAVAILABLE"


class RateLimited(MarketplaceError):
    code = "RATE_LIMITED"


class NotFound(MarketplaceError):
    code = "NOT_FOUND"


class Conflict(MarketplaceError):
    code = "CONFLICT"


class InsufficientConnects(MarketplaceError):
    code = "INSUFFICIENT_CONNECTS"


class PolicyViolation(MarketplaceError):
    code = "POLICY_VIOLATION"


class MarketplaceBackend(Protocol):
    name: str

    async def search_jobs(self, account: str, **filters: Any) -> dict: ...
    async def get_job(self, account: str, job_id: str) -> dict: ...
    async def get_client_history(self, account: str, client_id: str) -> dict: ...
    async def get_connects_balance(self, account: str) -> dict: ...
    async def get_pricing_stats(self, account: str, category: str, budget_type: str) -> dict: ...
    async def get_policy(self, account: str) -> dict: ...
    async def list_threads(self, account: str) -> dict: ...
    async def list_messages(self, account: str, thread_id: str) -> dict: ...
    async def list_proposals(self, account: str, status: str | None) -> dict: ...
    async def get_events(self, account: str, since_id: int) -> dict: ...
    async def create_proposal_draft(self, account: str, payload: dict, key: str, dry_run: bool) -> dict: ...
    async def submit_proposal(self, account: str, proposal_id: str, key: str, dry_run: bool) -> dict: ...
    async def send_message(self, account: str, thread_id: str, body: str, key: str, dry_run: bool) -> dict: ...
    async def health(self) -> dict: ...
