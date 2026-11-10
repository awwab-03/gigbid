"""Agent run viewer: state, node events, live SSE stream, checkpoint history and replay (C6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select

from apps.api import db, jobqueue
from apps.api.auth.security import current_user
from apps.api.runner import graph
from apps.api.schemas.models import Accepted, CheckpointOut, ReplayIn, RunOut
from apps.api.streaming import stream_run
from shared.pii import mask_obj

router = APIRouter(prefix="/runs", tags=["runs"])


def _run(thread_id: str, user: dict) -> dict:
    with db.engine.begin() as c:
        r = c.execute(select(db.runs).where(db.runs.c.thread_id == thread_id, db.runs.c.user_id == user["id"])).first()
    if not r:
        raise HTTPException(404, "run not found")
    return dict(r._mapping)


@router.get("", response_model=list[RunOut], operation_id="listRuns")
def list_runs(user: dict = Depends(current_user), limit: int = 50) -> list[RunOut]:
    with db.engine.begin() as c:
        rows = c.execute(select(db.runs).where(db.runs.c.user_id == user["id"]).order_by(db.runs.c.updated_at.desc()).limit(limit)).all()
    return [RunOut(**{k: v for k, v in dict(r._mapping).items() if k in RunOut.model_fields}) for r in rows]


@router.get("/{thread_id}", response_model=RunOut, operation_id="getRun")
async def get_run(thread_id: str, user: dict = Depends(current_user)) -> RunOut:
    r = _run(thread_id, user)
    snap = await (await graph("bid" if thread_id.startswith("bid:") else "conv")).aget_state({"configurable": {"thread_id": thread_id}})
    return RunOut(**{k: v for k, v in r.items() if k in RunOut.model_fields}, events=db.events_after(thread_id, user["id"], 0),
                  state=mask_obj({k: v for k, v in (snap.values or {}).items() if k not in ("profile",)}))


@router.get("/{thread_id}/stream", operation_id="streamRun")
async def stream(thread_id: str, request: Request, user: dict = Depends(current_user),
                 last_event_id: str | None = Header(default=None), after: int = 0):
    _run(thread_id, user)
    return await stream_run(request, thread_id, user["id"], int(last_event_id or after or 0))


@router.get("/{thread_id}/history", response_model=list[CheckpointOut], operation_id="runHistory")
async def history(thread_id: str, user: dict = Depends(current_user)) -> list[CheckpointOut]:
    _run(thread_id, user)
    g = await graph("bid" if thread_id.startswith("bid:") else "conv")
    out = []
    async for s in g.aget_state_history({"configurable": {"thread_id": thread_id}}):
        out.append(CheckpointOut(checkpoint_id=s.config["configurable"]["checkpoint_id"], next=list(s.next),
                                 step=(s.metadata or {}).get("step"), created_at=s.created_at, status=(s.values or {}).get("status")))
    return out


@router.post("/{thread_id}/replay", response_model=Accepted, operation_id="replayRun")
async def replay(thread_id: str, body: ReplayIn, user: dict = Depends(current_user)) -> Accepted:
    """Time travel: re-execute the thread from any checkpoint (LangGraph forks the thread there)."""
    _run(thread_id, user)
    return Accepted(**await jobqueue.enqueue("replay_thread", f"replay:{thread_id}:{body.checkpoint_id}", user_id=user["id"],
                                             thread_id=thread_id, checkpoint_id=body.checkpoint_id))


@router.post("/{thread_id}/retry", response_model=Accepted, operation_id="retryRun")
async def retry(thread_id: str, user: dict = Depends(current_user)) -> Accepted:
    _run(thread_id, user)
    return Accepted(**await jobqueue.enqueue("retry_degraded", f"retry:{user['id']}:{thread_id}", user_id=user["id"]))
