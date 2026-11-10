"""Background work (E1): scouting on a schedule, long graph runs, pipeline sync, degraded retries.

All functions are idempotent:
  * analyze_job skips a job whose thread already exists (dedup by deterministic thread id)
  * resume_thread relies on the graph's deterministic idempotency keys for submit/send
  * sync_pipeline tracks the last processed marketplace event id per user
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from agent.mcp_client import Toolbox, ToolUnavailable
from agent.memory.promotion_rules import first_sentence
from agent.memory.store import get_store, record_outcome
from agent.nodes.critic import GENERIC
from agent.nodes.scout import scout
from apps.api import db, runner

log = logging.getLogger("gigbid.worker")
PIPELINE = {"proposal.submitted": "submitted", "proposal.viewed": "viewed", "proposal.replied": "replied",
            "proposal.interview": "interview", "proposal.hired": "hired", "proposal.lost": "lost"}


def _user(user_id: str) -> dict:
    u = db.get_user(user_id)
    if not u:
        raise ValueError(f"unknown user {user_id}")
    return u


async def analyze_job(ctx, user_id: str, job_id: str, job: dict | None = None, force: bool = False) -> dict:
    u = _user(user_id)
    with db.engine.begin() as c:
        existing = c.execute(select(db.runs.c.status).where(db.runs.c.thread_id == f"bid:{user_id}:{job_id}")).first()
    if existing and not force and existing[0] not in ("failed", "queued_degraded", "dead_letter"):
        return {"skipped": "already analysed", "status": existing[0]}
    return await runner.analyze_job(u, job_id, job)


async def resume_thread(ctx, user_id: str, thread_id: str, decision: dict) -> dict:
    return await runner.resume(_user(user_id), thread_id, decision)


async def replay_thread(ctx, user_id: str, thread_id: str, checkpoint_id: str) -> dict:
    return await runner.replay(_user(user_id), thread_id, checkpoint_id)


async def run_conversation(ctx, user_id: str, mp_thread_id: str, proposal: dict | None = None, job: dict | None = None) -> dict:
    return await runner.converse(_user(user_id), mp_thread_id, proposal, job)


async def scout_user(ctx, user_id: str, analyze_limit: int = 10) -> dict:
    u = _user(user_id)
    searches = (u.get("settings") or {}).get("saved_searches") or [{"query": "", "limit": 20}]
    try:
        res = await scout(user_id, u["account"], [{"query": s.get("query", ""), "category": s.get("category"), "limit": s.get("limit", 20)}
                                                  for s in searches])
    except ToolUnavailable as e:
        log.warning("scout degraded for %s: %s", user_id, e)
        return {"degraded": str(e)}
    for job in res["new"]:
        db.upsert_job(user_id, job["job_id"], title=job["title"], category=job.get("category"), status="new", job=job,
                      posted_at=job.get("posted_at"), connects=job.get("connects_cost"), bid_type=job["budget"]["type"])
    for job in res["new"][:analyze_limit]:
        await analyze_job(ctx, user_id, job["job_id"], job)
    for d in res["duplicates"]:
        db.upsert_job(user_id, d["job_id"], status="skipped", action="skip", reason=f"duplicate of {d['duplicate_of']}")
    return {"new": len(res["new"]), "duplicates": len(res["duplicates"])}


async def sync_pipeline(ctx, user_id: str) -> dict:
    """Pull marketplace events; move pipeline cards; record CONFIRMED outcomes into outcome memory;
    start a conversation graph for each new client message."""
    u = _user(user_id)
    s = get_store()
    cur = s.get(("cursor", user_id), "events")
    since = cur.value["id"] if cur else 0
    tb = Toolbox("pipeline", user_id, u["account"])
    try:
        evs = (await tb.call("marketplace.get_events", {"since_id": since}))["events"]
    except ToolUnavailable as e:
        return {"degraded": str(e)}
    with db.engine.begin() as c:
        by_prop = {r.proposal_id: dict(r._mapping) for r in c.execute(select(db.jobs).where(db.jobs.c.user_id == user_id,
                                                                                         db.jobs.c.proposal_id.isnot(None))).all()}
    started = 0
    for e in evs:
        stage = PIPELINE.get(e["type"])
        if stage and e["ref"] in by_prop:
            j = by_prop[e["ref"]]
            db.upsert_job(user_id, j["job_id"], pipeline=stage)
            if stage in ("replied", "interview", "hired", "lost"):
                snap = (await (await runner.graph("bid")).aget_state({"configurable": {"thread_id": j["thread_id"]}})).values
                text = (snap.get("submission") and (snap.get("draft") or {}).get("cover_letter")) or ""
                record_outcome(user_id, proposal_id=e["ref"], category=j.get("category") or "other", outcome=stage,
                               cited_projects=sorted({ev.get("project") for evs_ in (snap.get("evidence") or {}).values()
                                                      for ev in evs_ if ev.get("project")})[:3],
                               generic_opening=any(__import__("re").search(p, first_sentence(text).lower()) for p in GENERIC))
        if e["type"] == "message.received":
            j = next((v for v in by_prop.values() if v["job_id"] == e["payload"].get("job_id")), None)
            snap = {}
            if j:
                snap = (await (await runner.graph("bid")).aget_state({"configurable": {"thread_id": j["thread_id"]}})).values
            prop = {"cover_letter": (snap.get("draft") or {}).get("cover_letter"), "bid_amount": (snap.get("price") or {}).get("amount"),
                    "bid_type": (snap.get("price") or {}).get("bid_type")}
            await run_conversation(ctx, user_id, e["ref"], prop, snap.get("job"))
            started += 1
        since = max(since, e["id"])
    s.put(("cursor", user_id), "events", {"id": since, "at": datetime.now(timezone.utc).isoformat()})
    return {"events": len(evs), "conversations_started": started}


async def retry_degraded(ctx, user_id: str) -> dict:
    u = _user(user_id)
    with db.engine.begin() as c:
        rows = c.execute(select(db.runs.c.thread_id).where(db.runs.c.user_id == user_id, db.runs.c.status == "queued_degraded")).all()
    done = 0
    for (tid,) in rows:
        try:
            await runner.retry_degraded(u, tid)
            done += 1
        except Exception as e:  # noqa: BLE001
            log.warning("retry %s failed: %s", tid, e)
    return {"retried": done}


async def tick_all(ctx) -> dict:
    """Cron entry: scout + sync + retry for every user, at the configured interval."""
    with db.engine.begin() as c:
        ids = [r[0] for r in c.execute(select(db.users.c.id)).all()]
    out = {}
    for uid in ids:
        out[uid] = {"sync": await sync_pipeline(ctx, uid), "retry": await retry_degraded(ctx, uid)}
    return out
