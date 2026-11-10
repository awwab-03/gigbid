"""Job inbox and job detail. Analysis runs in the worker; these routes only read and enqueue."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from apps.api import db, jobqueue
from apps.api.auth.security import current_user
from apps.api.deps import safe_call
from apps.api.runner import graph
from apps.api.schemas.models import Accepted, JobDetail, JobList, JobRow

router = APIRouter(prefix="/jobs", tags=["jobs"])


def to_row(r: dict) -> JobRow:
    return JobRow(job_id=r["job_id"], title=r.get("title"), category=r.get("category"), status=r.get("status"), action=r.get("action"),
                  fit=r.get("fit"), risk=r.get("risk"), scam=bool(r.get("scam")), price=r.get("price"), bid_type=r.get("bid_type"),
                  connects=r.get("connects"), flags=r.get("flags") or [], reason=r.get("reason"), thread_id=r.get("thread_id"),
                  pipeline=r.get("pipeline"), posted_at=r.get("posted_at"), budget=(r.get("job") or {}).get("budget"))


@router.get("", response_model=JobList, operation_id="listJobs")
async def list_jobs(user: dict = Depends(current_user), action: str | None = None, status: str | None = None,
                    q: str | None = None, include_skipped: bool = True, limit: int = Query(100, le=500)) -> JobList:
    with db.engine.begin() as c:
        stmt = select(db.jobs).where(db.jobs.c.user_id == user["id"])
        if action:
            stmt = stmt.where(db.jobs.c.action == action)
        if status:
            stmt = stmt.where(db.jobs.c.status == status)
        rows = [dict(r._mapping) for r in c.execute(stmt).all()]
    if q:
        rows = [r for r in rows if q.lower() in (r.get("title") or "").lower()]
    if not include_skipped:
        rows = [r for r in rows if r.get("action") != "skip"]
    rows.sort(key=lambda r: (r.get("action") == "bid", r.get("fit") or 0, r.get("posted_at") or ""), reverse=True)
    _, err = await safe_call(user, "marketplace.get_policy")
    return JobList(jobs=[to_row(r) for r in rows[:limit]], marketplace_available=err is None, marketplace_message=err)


@router.post("/scout", response_model=Accepted, operation_id="scoutNow")
async def scout_now(user: dict = Depends(current_user)) -> Accepted:
    return Accepted(**await jobqueue.enqueue("scout_user", f"scout:{user['id']}", user_id=user["id"]))


@router.post("/import/{job_id}", response_model=Accepted, operation_id="importJob")
async def import_job(job_id: str, user: dict = Depends(current_user)) -> Accepted:
    """Pull one marketplace job into the inbox and analyse it."""
    job, err = await safe_call(user, "marketplace.get_job", {"job_id": job_id})
    if err:
        raise HTTPException(503, err)
    db.upsert_job(user["id"], job_id, title=job["title"], category=job.get("category"), status="new", job=job, posted_at=job.get("posted_at"))
    return Accepted(**await jobqueue.enqueue("analyze_job", f"analyze:{user['id']}:{job_id}", user_id=user["id"], job_id=job_id, job=job))


@router.get("/{job_id}", response_model=JobDetail, operation_id="getJob")
async def get_job(job_id: str, user: dict = Depends(current_user)) -> JobDetail:
    with db.engine.begin() as c:
        r = c.execute(select(db.jobs).where(db.jobs.c.user_id == user["id"], db.jobs.c.job_id == job_id)).first()
        run = c.execute(select(db.runs).where(db.runs.c.thread_id == f"bid:{user['id']}:{job_id}", db.runs.c.user_id == user["id"])).first()
    r = dict(r._mapping) if r else None
    job = (r or {}).get("job")
    if not job:
        job, err = await safe_call(user, "marketplace.get_job", {"job_id": job_id})
        if err:
            raise HTTPException(503 if "unavailable" in err.lower() else 404, err)
    analysis = {}
    if r and r.get("thread_id"):
        snap = await (await graph("bid")).aget_state({"configurable": {"thread_id": r["thread_id"]}})
        v = snap.values or {}
        analysis = {k: v.get(k) for k in ("job_spec", "risk_report", "fit_report", "decision", "price", "evidence", "status",
                                          "status_reason", "verification", "critiques", "compliance_verdict", "submission", "trace")}
    return JobDetail(job=job, row=to_row(r) if r else None, analysis=analysis, run=dict(run._mapping) if run else None)


@router.post("/{job_id}/analyze", response_model=Accepted, operation_id="analyzeJob")
async def analyze(job_id: str, force: bool = False, user: dict = Depends(current_user)) -> Accepted:
    with db.engine.begin() as c:
        r = c.execute(select(db.jobs.c.job).where(db.jobs.c.user_id == user["id"], db.jobs.c.job_id == job_id)).first()
    return Accepted(**await jobqueue.enqueue("analyze_job", f"analyze:{user['id']}:{job_id}{':f' if force else ''}", user_id=user["id"],
                                             job_id=job_id, job=r[0] if r else None, force=force))


@router.post("/{job_id}/skip", response_model=JobRow, operation_id="skipJob")
def skip(job_id: str, user: dict = Depends(current_user)) -> JobRow:
    db.upsert_job(user["id"], job_id, action="skip", status="skipped", reason="skipped by user")
    with db.engine.begin() as c:
        r = c.execute(select(db.jobs).where(db.jobs.c.user_id == user["id"], db.jobs.c.job_id == job_id)).first()
    return to_row(dict(r._mapping))
