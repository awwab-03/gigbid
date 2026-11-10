"""Pending approvals (proposals and messages) and the approve / edit / reject actions that resume
the interrupted LangGraph thread. Pending payloads are stored in the runs table and the Postgres
checkpoint, so a page refresh or an API restart never loses one."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent.llm import call_text
from agent.mcp_client import Toolbox
from apps.api import db, jobqueue
from apps.api.auth.security import current_user
from apps.api.schemas.models import (
    Accepted,
    ApprovalIn,
    Pending,
    PendingList,
    RegenerateIn,
    RegenerateOut,
)

router = APIRouter(tags=["approvals"])


def _pending(user_id: str, thread_id: str | None = None) -> list[dict]:
    with db.engine.begin() as c:
        stmt = select(db.runs).where(db.runs.c.user_id == user_id, db.runs.c.status == "awaiting_approval")
        if thread_id:
            stmt = stmt.where(db.runs.c.thread_id == thread_id)
        return [dict(r._mapping) for r in c.execute(stmt.order_by(db.runs.c.updated_at.desc())).all()]


@router.get("/approvals", response_model=PendingList, operation_id="listApprovals")
def list_pending(user: dict = Depends(current_user)) -> PendingList:
    return PendingList(pending=[Pending(thread_id=r["thread_id"], kind=(r["pending"] or {}).get("kind", r["kind"]), ref=r["ref"],
                                        payload=r["pending"] or {}, updated_at=str(r["updated_at"])) for r in _pending(user["id"])])


@router.get("/approvals/{thread_id}", response_model=Pending, operation_id="getApproval")
def get_pending(thread_id: str, user: dict = Depends(current_user)) -> Pending:
    rows = _pending(user["id"], thread_id)
    if not rows:
        raise HTTPException(404, "no pending approval for this thread")
    r = rows[0]
    return Pending(thread_id=thread_id, kind=(r["pending"] or {}).get("kind", r["kind"]), ref=r["ref"], payload=r["pending"] or {},
                   updated_at=str(r["updated_at"]))


@router.post("/approvals/{thread_id}", response_model=Accepted, operation_id="decideApproval")
async def decide(thread_id: str, body: ApprovalIn, user: dict = Depends(current_user)) -> Accepted:
    if not _pending(user["id"], thread_id):
        raise HTTPException(409, "nothing is waiting for approval on this thread (already decided?)")
    if body.action == "reject" and not body.reason:
        raise HTTPException(422, "a reason is required when rejecting")
    if body.action == "edit" and not (body.edited_text or body.edited_amount):
        raise HTTPException(422, "edit needs edited_text or edited_amount")
    db.upsert_run(thread_id, user["id"], status="resuming")
    db.add_event(thread_id, user["id"], "approval_decided", None, {"action": body.action, "reason": body.reason})
    key = f"resume:{thread_id}:{body.action}:{abs(hash((body.edited_text or '') + str(body.edited_amount))) % 10**8}"
    return Accepted(**await jobqueue.enqueue("resume_thread", key, user_id=user["id"], thread_id=thread_id, decision=body.model_dump()))


@router.post("/approvals/{thread_id}/regenerate", response_model=RegenerateOut, operation_id="regenerateParagraph")
async def regenerate(thread_id: str, body: RegenerateIn, user: dict = Depends(current_user)) -> RegenerateOut:
    """Rewrite ONE paragraph of a pending proposal from the same evidence, then re-verify it.
    The result is returned for the editor; it is only used if the user approves it as an edit."""
    rows = _pending(user["id"], thread_id)
    if not rows:
        raise HTTPException(404, "no pending proposal")
    p = rows[0]["pending"]
    paras = [x for x in re.split(r"\n\s*\n", p["cover_letter"]) if x.strip()]
    if len(paras) == 1:
        paras = re.split(r"(?<=[.!?])\s+(?=[A-Z])", p["cover_letter"])
    if body.paragraph_index >= len(paras):
        raise HTTPException(422, f"draft has {len(paras)} paragraphs")
    ev = "\n".join(f"- {e['snippet'][:300]}" for evs in (p.get("evidence") or {}).values() for e in evs[:1])[:3000]
    new = await call_text("writer", "verifier_rewrite", {"claim": paras[body.paragraph_index] + (f" (instruction: {body.instruction})" if body.instruction else ""),
                                                         "evidence": ev})
    res = await Toolbox("verifier", user["id"], user["account"]).call("portfolio.verify_claims", {"text": new or paras[body.paragraph_index]})
    return RegenerateOut(paragraph_index=body.paragraph_index, text=res["fixed_text"], unsupported_removed=res["unsupported_before"])
