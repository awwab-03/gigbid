"""Pipeline board and analytics (reply/hire rate by category, Connects vs outcomes, cost and
latency per proposal, top rejection reasons)."""

from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user
from apps.api.schemas.models import Analytics, PipelineCard, PipelineOut

router = APIRouter(tags=["analytics"])
STAGES = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
POSITIVE = {"replied", "interview", "hired"}


def _p95(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x)
    return round(xs[max(0, int(len(xs) * 0.95) - 1)], 3) if xs else None


@router.get("/pipeline", response_model=PipelineOut, operation_id="pipeline")
def pipeline(user: dict = Depends(current_user)) -> PipelineOut:
    with db.engine.begin() as c:
        rows = [dict(r._mapping) for r in c.execute(select(db.jobs).where(db.jobs.c.user_id == user["id"])).all()]
    cards = []
    for r in rows:
        stage = r.get("pipeline") or ("drafted" if r.get("status") in ("awaiting_approval", "edited") else None)
        if stage:
            cards.append(PipelineCard(job_id=r["job_id"], title=r.get("title"), stage=stage, proposal_id=r.get("proposal_id"),
                                      price=r.get("price"), connects=r.get("connects"), thread_id=r.get("thread_id")))
    return PipelineOut(stages=STAGES, cards=cards)


@router.get("/analytics", response_model=Analytics, operation_id="analytics")
def analytics(user: dict = Depends(current_user)) -> Analytics:
    with db.engine.begin() as c:
        jobs = [dict(r._mapping) for r in c.execute(select(db.jobs).where(db.jobs.c.user_id == user["id"])).all()]
        runs = [dict(r._mapping) for r in c.execute(select(db.runs).where(db.runs.c.user_id == user["id"])).all()]
        ev = [dict(r._mapping) for r in c.execute(select(db.run_events).where(db.run_events.c.user_id == user["id"],
                                                                             db.run_events.c.type == "approval_decided")).all()]
    by_cat: dict[str, Counter] = defaultdict(Counter)
    connects = 0
    for j in jobs:
        if j.get("pipeline"):
            cat = j.get("category") or "other"
            by_cat[cat]["submitted"] += 1
            by_cat[cat]["positive"] += j["pipeline"] in POSITIVE
            by_cat[cat]["hired"] += j["pipeline"] == "hired"
            connects += int(j.get("connects") or 0)
    cats = [{"category": k, "submitted": v["submitted"], "reply_rate": round(v["positive"] / v["submitted"], 3) if v["submitted"] else 0,
             "hire_rate": round(v["hired"] / v["submitted"], 3) if v["submitted"] else 0} for k, v in sorted(by_cat.items())]
    bid_runs = [r for r in runs if r["kind"] == "bid"]
    prop_runs = [r for r in bid_runs if r.get("status") in ("awaiting_approval", "submitted", "rejected")]
    reasons = Counter((e["data"] or {}).get("reason") for e in ev if (e["data"] or {}).get("action") == "reject")
    return Analytics(
        by_category=cats, connects_spent=connects, outcomes=dict(Counter(j.get("pipeline") for j in jobs if j.get("pipeline"))),
        cost_per_proposal_usd=round(sum(r["cost_usd"] or 0 for r in prop_runs) / len(prop_runs), 5) if prop_runs else None,
        cost_per_job_usd=round(sum(r["cost_usd"] or 0 for r in bid_runs) / len(bid_runs), 5) if bid_runs else None,
        p95_latency_proposal_s=_p95([r["latency_s"] for r in prop_runs]), p95_latency_job_s=_p95([r["latency_s"] for r in bid_runs]),
        top_rejection_reasons=[{"reason": k, "count": v} for k, v in reasons.most_common(5) if k], runs=len(runs))
