"""SSE bridge to LangGraph streams.

The runner (in the worker or in-process) writes every node update to run_events. This endpoint
replays events after Last-Event-ID and then tails the table, so it works across processes, survives
API restarts, and a refreshed page simply resumes from the last event it saw.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import Request
from sse_starlette.sse import EventSourceResponse

from apps.api import db

TERMINAL = {"run_finished", "error"}


async def stream_run(request: Request, thread_id: str, user_id: str, last_id: int = 0, follow: bool = True):
    async def gen():
        cursor = last_id
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            evs = db.events_after(thread_id, user_id, cursor)
            for e in evs:
                cursor = e["id"]
                yield {"id": str(e["id"]), "event": e["type"],
                       "data": json.dumps({"node": e["node"], "data": e["data"], "at": str(e["at"])}, default=str)}
            if evs:
                idle = 0
            else:
                idle += 1
                yield {"event": "ping", "data": "{}"} if idle % 30 == 0 else {"comment": "keepalive"}
            if not follow or idle > 1200:  # ~10 minutes without activity
                break
            await asyncio.sleep(0.5)

    return EventSourceResponse(gen(), ping=15)
