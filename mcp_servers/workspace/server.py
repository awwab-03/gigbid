"""Workspace MCP server (A3): calendar free slots, tentative interview holds and email drafts.

Backed by a local mock (sqlite) with a seeded working calendar per account, as the assignment
allows. The agent only sees MCP tools; swapping in Google Calendar / Gmail means replacing
`MockWorkspace` with an implementation of the same four methods.

Run:  python -m mcp_servers.workspace.server   (streamable HTTP on :8093/mcp)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import (
    STATE_DIR,
    AuditLog,
    BearerAuthMiddleware,
    IdempotencyStore,
    caller_var,
)


class Slot(BaseModel):
    start: str = Field(description="ISO 8601 with offset")
    end: str
    label: str = Field(description="Human-friendly, e.g. 'Tue 12 Nov, 3:00 PM PKT'")


class SlotList(BaseModel):
    timezone: str
    slots: list[Slot]


class Hold(BaseModel):
    hold_id: str
    start: str
    end: str
    title: str
    status: str = "tentative"
    idempotent_replay: bool = False


class EmailDraft(BaseModel):
    draft_id: str
    to: str
    subject: str
    body: str
    status: str = "draft"
    idempotent_replay: bool = False


class MockWorkspace:
    """Working hours 10:00-18:00 local, Mon-Fri; seeded busy blocks; holds become busy."""

    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS holds (hold_id TEXT PRIMARY KEY, account TEXT, start TEXT, end TEXT, title TEXT, status TEXT);"
            "CREATE TABLE IF NOT EXISTS drafts (draft_id TEXT PRIMARY KEY, account TEXT, rcpt TEXT, subject TEXT, body TEXT, at TEXT);")

    def busy(self, account: str, day: datetime) -> list[tuple[datetime, datetime]]:
        seed = int(hashlib.md5(f"{account}{day.date()}".encode()).hexdigest()[:6], 16)
        blocks = []
        for i in range(seed % 3):
            h = 10 + (seed >> (i * 3)) % 7
            s = day.replace(hour=h, minute=0)
            blocks.append((s, s + timedelta(hours=1)))
        for s, e in self.db.execute("SELECT start, end FROM holds WHERE account=?", (account,)).fetchall():
            blocks.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))
        return blocks

    def free_slots(self, account: str, start_date: str | None, days: int, duration_min: int, tz: str, max_slots: int) -> list[Slot]:
        zone = ZoneInfo(tz)
        base = datetime.fromisoformat(start_date).replace(tzinfo=zone) if start_date else datetime.now(zone) + timedelta(days=1)
        out: list[Slot] = []
        for d in range(days):
            day = (base + timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
            if day.weekday() >= 5:
                continue
            busy = self.busy(account, day)
            t = day.replace(hour=10)
            while t + timedelta(minutes=duration_min) <= day.replace(hour=18):
                e = t + timedelta(minutes=duration_min)
                if not any(s < e and t < be for s, be in busy):
                    out.append(Slot(start=t.isoformat(), end=e.isoformat(), label=t.strftime("%a %d %b, %I:%M %p ") + t.tzname()))
                    t = e + timedelta(minutes=60)
                else:
                    t += timedelta(minutes=30)
                if len(out) >= max_slots:
                    return out
        return out


ws = MockWorkspace(STATE_DIR / "workspace.sqlite")
idem = IdempotencyStore(STATE_DIR / "workspace_idem.sqlite")
audit = AuditLog(STATE_DIR / "audit_workspace.jsonl")
mcp = FastMCP("gigbid-workspace", instructions="Calendar and email-draft tools. Nothing is sent: holds are tentative, emails are drafts.",
              host=os.getenv("MCP_HOST", "0.0.0.0"), port=int(os.getenv("WORKSPACE_MCP_PORT", "8093")), stateless_http=True)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
          title="Find free calendar slots")
def free_slots(start_date: Annotated[str | None, Field(description="YYYY-MM-DD; default tomorrow")] = None,
               days: Annotated[int, Field(ge=1, le=14)] = 5,
               duration_min: Annotated[int, Field(ge=15, le=180)] = 30,
               timezone_name: Annotated[str, Field(max_length=64)] = "Asia/Karachi",
               max_slots: Annotated[int, Field(ge=1, le=10)] = 3) -> SlotList:
    """Free interview slots in the freelancer's working hours."""
    t0 = time.perf_counter()
    _, account = caller_var.get()
    slots = ws.free_slots(account, start_date, days, duration_min, timezone_name, max_slots)
    audit.write(server="workspace", tool="free_slots", args={"start_date": start_date, "days": days}, result={"n": len(slots)},
                ok=True, ms=(time.perf_counter() - t0) * 1000)
    return SlotList(timezone=timezone_name, slots=slots)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
          title="Create tentative interview hold")
def create_interview_hold(start: Annotated[str, Field(description="ISO 8601 start")],
                          duration_min: Annotated[int, Field(ge=15, le=180)],
                          title: Annotated[str, Field(min_length=3, max_length=120)],
                          idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]) -> Hold:
    """Block a tentative slot on the calendar (no invite is sent)."""
    user, account = caller_var.get()
    args = {"start": start, "duration_min": duration_min, "title": title, "idempotency_key": idempotency_key}
    prev = idem.get(user, "create_interview_hold", idempotency_key, args)
    if prev:
        return Hold(**prev)
    s = datetime.fromisoformat(start)
    if s.tzinfo is None:
        s = s.replace(tzinfo=timezone.utc)
    e = s + timedelta(minutes=duration_min)
    hid = "h-" + hashlib.sha256(f"{account}{idempotency_key}".encode()).hexdigest()[:10]
    ws.db.execute("INSERT OR IGNORE INTO holds VALUES (?,?,?,?,?,?)", (hid, account, s.isoformat(), e.isoformat(), title, "tentative"))
    ws.db.commit()
    out = Hold(hold_id=hid, start=s.isoformat(), end=e.isoformat(), title=title).model_dump()
    idem.put(user, "create_interview_hold", idempotency_key, args, out)
    audit.write(server="workspace", tool="create_interview_hold", args=args, result=out, ok=True, ms=0)
    return Hold(**out)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False),
          title="Create email draft")
def create_email_draft(to: Annotated[str, Field(max_length=200)], subject: Annotated[str, Field(min_length=1, max_length=200)],
                       body: Annotated[str, Field(min_length=1, max_length=5000)],
                       idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]) -> EmailDraft:
    """Save an email draft for the freelancer to review. Never sends."""
    user, account = caller_var.get()
    args = {"to": to, "subject": subject, "body": body, "idempotency_key": idempotency_key}
    prev = idem.get(user, "create_email_draft", idempotency_key, args)
    if prev:
        return EmailDraft(**prev)
    did = "d-" + hashlib.sha256(f"{account}{idempotency_key}".encode()).hexdigest()[:10]
    ws.db.execute("INSERT OR IGNORE INTO drafts VALUES (?,?,?,?,?,?)", (did, account, to, subject, body, datetime.now(timezone.utc).isoformat()))
    ws.db.commit()
    out = EmailDraft(draft_id=did, to=to, subject=subject, body=body).model_dump()
    idem.put(user, "create_email_draft", idempotency_key, args, out)
    audit.write(server="workspace", tool="create_email_draft", args=args, result={"draft_id": did}, ok=True, ms=0)
    return EmailDraft(**out)


@mcp.resource("workspace://holds", mime_type="application/json")
def holds() -> str:
    """All tentative holds for the current account."""
    _, account = caller_var.get()
    rows = ws.db.execute("SELECT hold_id, start, end, title, status FROM holds WHERE account=?", (account,)).fetchall()
    return json.dumps([dict(zip(["hold_id", "start", "end", "title", "status"], r, strict=False)) for r in rows])


def http_app():
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    app = mcp.streamable_http_app()

    async def health(_):
        return JSONResponse({"server": "workspace", "ok": True, "backend": "mock"})

    app.router.routes.append(Route("/health", health))
    app.add_middleware(BearerAuthMiddleware, required=os.getenv("MCP_AUTH_REQUIRED", "1") == "1")
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdio", action="store_true")
    if ap.parse_args().stdio:
        mcp.run("stdio")
    else:
        import uvicorn

        uvicorn.run(http_app(), host=mcp.settings.host, port=mcp.settings.port)
