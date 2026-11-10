"""Client threads with suggested replies; replies are approved through /approvals like proposals."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from apps.api import db, jobqueue
from apps.api.auth.security import current_user
from apps.api.deps import safe_call
from apps.api.schemas.models import Accepted, Pending, ThreadOut, ThreadsOut

router = APIRouter(prefix="/messages", tags=["messages"])


def _pending_for(user_id: str, mp_thread: str) -> Pending | None:
    with db.engine.begin() as c:
        r = c.execute(select(db.runs).where(db.runs.c.user_id == user_id, db.runs.c.ref == mp_thread,
                                            db.runs.c.status == "awaiting_approval")).first()
    if not r:
        return None
    r = dict(r._mapping)
    return Pending(thread_id=r["thread_id"], kind="message", ref=mp_thread, payload=r["pending"] or {}, updated_at=str(r["updated_at"]))


@router.get("", response_model=ThreadsOut, operation_id="listThreads")
async def threads(user: dict = Depends(current_user)) -> ThreadsOut:
    res, err = await safe_call(user, "marketplace.list_threads")
    if err:
        return ThreadsOut(threads=[], marketplace_available=False)
    out = []
    for t in res["threads"]:
        full, _ = await safe_call(user, "marketplace.list_messages", {"thread_id": t["thread_id"]})
        out.append(ThreadOut(thread_id=t["thread_id"], job_id=t["job_id"], stage=t["stage"], messages=(full or {}).get("messages", []),
                             pending_reply=_pending_for(user["id"], t["thread_id"])))
    return ThreadsOut(threads=out)


@router.post("/{thread_id}/draft", response_model=Accepted, operation_id="draftReply")
async def draft(thread_id: str, user: dict = Depends(current_user)) -> Accepted:
    t, err = await safe_call(user, "marketplace.list_messages", {"thread_id": thread_id})
    if err:
        raise HTTPException(503, err)
    with db.engine.begin() as c:
        j = c.execute(select(db.jobs).where(db.jobs.c.user_id == user["id"], db.jobs.c.job_id == t["job_id"])).first()
    prop, job = {}, None
    if j:
        j = dict(j._mapping)
        job = j.get("job")
        prop = {"bid_amount": j.get("price"), "bid_type": j.get("bid_type")}
    n = len(t["messages"])
    return Accepted(**await jobqueue.enqueue("run_conversation", f"conv:{user['id']}:{thread_id}:{n}", user_id=user["id"],
                                             mp_thread_id=thread_id, proposal=prop, job=job))
