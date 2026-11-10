"""Shared plumbing for GigBid's own MCP servers.

* BearerAuthMiddleware: validates signed service tokens on the streamable-HTTP endpoint and puts
  the caller (user, account) and the X-Trace-Id header into context variables.
* RateLimiter: per-user sliding window that *waits* (politely) rather than hammering upstream.
* IdempotencyStore: sqlite-backed; a retried write with the same key returns the first result.
* AuditLog: append-only JSONL (user, tool, masked args, masked result, trace id). Lines are
  hash-chained so tampering with history is detectable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from shared.pii import mask_obj
from shared.security import trace_id_var, verify_service_token

caller_var: ContextVar[tuple[str, str]] = ContextVar("caller", default=("local", os.getenv("DEFAULT_ACCOUNT", "ml_engineer")))
STATE_DIR = Path(os.getenv("MCP_STATE_DIR", Path(__file__).resolve().parents[1] / "logs"))
STATE_DIR.mkdir(parents=True, exist_ok=True)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, required: bool = True):
        super().__init__(app)
        self.required = required

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/health"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        tok = auth[7:] if auth.lower().startswith("bearer ") else ""
        who = verify_service_token(tok) if tok else None
        if self.required and not who:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        t1 = caller_var.set(who or caller_var.get())
        t2 = trace_id_var.set(request.headers.get("x-trace-id", ""))
        try:
            return await call_next(request)
        finally:
            caller_var.reset(t1)
            trace_id_var.reset(t2)


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def acquire(self, key: str, max_wait: float = 20.0) -> None:
        start = time.monotonic()
        while True:
            async with self.lock:
                q = self.hits[key]
                t = time.monotonic()
                while q and t - q[0] > 60:
                    q.popleft()
                if len(q) < self.per_minute:
                    q.append(t)
                    return
                wait = 60 - (t - q[0]) + 0.05
            if time.monotonic() - start + wait > max_wait:
                raise RuntimeError(f"RATE_LIMITED: more than {self.per_minute} calls/min for {key}; queued, try again later")
            await asyncio.sleep(min(wait, 2.0))


class IdempotencyStore:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS idem (user TEXT, tool TEXT, key TEXT, args_hash TEXT, result TEXT, at TEXT,"
                        " PRIMARY KEY (user, tool, key))")
        self.db.commit()
        self.lock = threading.Lock()

    @staticmethod
    def _hash(args: dict) -> str:
        return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()

    def get(self, user: str, tool: str, key: str, args: dict) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT args_hash, result FROM idem WHERE user=? AND tool=? AND key=?", (user, tool, key)).fetchone()
        if not row:
            return None
        if row[0] != self._hash(args):
            raise ValueError("idempotency_key was already used with different arguments")
        out = json.loads(row[1])
        out["idempotent_replay"] = True
        return out

    def put(self, user: str, tool: str, key: str, args: dict, result: dict) -> None:
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO idem VALUES (?,?,?,?,?,?)",
                            (user, tool, key, self._hash(args), json.dumps(result, default=str), datetime.now(timezone.utc).isoformat()))
            self.db.commit()


class AuditLog:
    """Append-only, hash-chained JSONL audit log."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.prev = "0" * 64
        if path.exists():
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            if lines:
                self.prev = json.loads(lines[-1]).get("hash", self.prev)

    def write(self, *, server: str, tool: str, args: dict, result: Any, ok: bool, ms: float) -> None:
        user, account = caller_var.get()
        rec = {"at": datetime.now(timezone.utc).isoformat(), "server": server, "user": user, "account": account,
               "tool": tool, "args": mask_obj(args), "ok": ok, "ms": round(ms, 1),
               "result": mask_obj(result if isinstance(result, (dict, list, str)) else str(result)),
               "trace_id": trace_id_var.get(), "prev": self.prev}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
        with self.lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            self.prev = rec["hash"]


def verify_audit_chain(path: Path) -> bool:
    prev = "0" * 64
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        h = rec.pop("hash")
        if rec["prev"] != prev or hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest() != h:
            return False
        prev = h
    return True
