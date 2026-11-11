"""GigBid API (FastAPI). Typed routes; the web client is generated from /openapi.json."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from apps.api import jobqueue  # noqa: E402
from apps.api.routers import (  # noqa: E402
    analytics,
    approvals,
    auth,
    jobs,
    messages,
    runs,
    settings,
)
from apps.api.schemas.models import HealthOut  # noqa: E402
from apps.api.seed import ensure_reviewer  # noqa: E402


async def _inline_cron():
    """Single-process deploy (WORKER_MODE=inline, INLINE_CRON=1): the same schedules as worker/main.py
    (pipeline sync + degraded retries every 2 min, scouting every SCOUT_EVERY min) without Redis/Arq."""
    import asyncio
    import logging

    from worker import tasks
    from worker.main import SCOUT_EVERY, scout_all

    log = logging.getLogger("inline_cron")
    minute = 0
    while True:
        await asyncio.sleep(120)
        minute += 2
        try:
            await tasks.tick_all({})
            if minute % SCOUT_EVERY == 0:
                await scout_all({})
        except Exception as e:  # keep the scheduler alive; the next tick retries
            log.exception("inline cron failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    ensure_reviewer()
    cron_task = asyncio.create_task(_inline_cron()) if os.getenv("INLINE_CRON") == "1" else None
    yield
    if cron_task:
        cron_task.cancel()


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot. Nothing is sent to a marketplace without human approval.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.getenv("WEB_ORIGIN", "http://localhost:5173").split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for r in (auth, jobs, approvals, messages, runs, analytics, settings):
    app.include_router(r.router)


@app.get("/health", response_model=HealthOut, operation_id="health")
async def health() -> HealthOut:
    import httpx

    from agent.mcp_client import _url

    mp = {"ok": False}
    if os.getenv("MCP_TRANSPORT", "http") == "inproc":
        from mcp_servers.marketplace.server import backend

        mp = await backend.health()
    else:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                mp = (await c.get(_url("marketplace").rsplit("/mcp", 1)[0] + "/health")).json()
        except Exception as e:  # noqa: BLE001
            mp = {"ok": False, "error": f"marketplace MCP server unreachable ({type(e).__name__})"}
    return HealthOut(status="ok" if mp.get("ok") else "degraded", marketplace=mp, mode=os.getenv("MARKETPLACE_MODE", "gigsim"),
                     worker_mode=jobqueue.mode())
