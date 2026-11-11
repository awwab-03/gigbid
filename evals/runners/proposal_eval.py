"""Proposal quality and GigSim outcomes (B4): unsupported claims per proposal before/after
verification, calibrated judge score, Critic loops, latency and cost per proposal, and the simulated
reply/hire rate on a fixed job set.

Every proposal is drafted by the real bid graph, then auto-approved (simulator only, eval only),
submitted to an in-process GigSim, and the simulated clock is advanced so clients decide.

  RAG_VARIANT=v3_rerank MODEL_PROFILE=open python -m evals.runners.proposal_eval --limit 15 --tag v3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

os.environ.setdefault("MCP_TRANSPORT", "inproc")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RATE_LIMIT", "100000")
os.environ.setdefault("MARKETPLACE_RPM", "100000")

from evals.runners.decision_eval import PERSONAS, p95, setup_inprocess_gigsim  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
ADMIN = {"X-Admin-Token": os.getenv("GIGSIM_ADMIN_TOKEN", "gigsim-admin")}


async def judge(job: dict, text: str) -> dict | None:
    from pydantic import BaseModel

    from agent.llm import call_json, profile_name

    if profile_name() == "fake":
        return None

    class J(BaseModel):
        relevance: int
        specificity: int
        personalisation: int
        credibility: int
        clarity: int
        overall: int
        rationale: str = ""

    try:
        return (await call_json("judge", "judge", {"job": job["title"] + "\n" + job["description"][:1500], "proposal": text}, J)).model_dump()
    except Exception:  # noqa: BLE001
        return None


async def one(graph, persona: str, g: dict, profile: dict, sem, jobs: dict) -> dict:
    from langgraph.types import Command

    async with sem:
        tid = f"peval:{persona}:{g['job_id']}"
        cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 60}
        t0 = time.perf_counter()
        async for _ in graph.astream({"thread_id": tid, "user_id": f"peval-{persona}", "account": persona, "job": {"job_id": g["job_id"]},
                                      "profile": profile, "skip_dedup": True}, cfg, stream_mode="updates"):
            pass
        snap = await graph.aget_state(cfg)
        draft_latency = time.perf_counter() - t0
        st = snap.values
        row = {"job_id": g["job_id"], "persona": persona, "pred": (st.get("decision") or {}).get("action"), "status": st.get("status"),
               "drafted": bool(snap.next), "latency_s": round(draft_latency, 2), "tokens": st.get("tokens", 0), "cost_usd": st.get("cost_usd", 0.0),
               "revisions": int(st.get("revisions") or 0), "critic_rounds": len(st.get("critiques") or [])}
        if not snap.next:
            return row
        ver = st.get("verification") or {}
        text = (st.get("compliance_verdict") or {}).get("fixed_text") or (st.get("draft") or {}).get("cover_letter_verified", "")
        # re-verify the FINAL text to measure what is left after verification + compliance
        from agent.mcp_client import Toolbox

        after = await Toolbox("verifier", "peval", persona).call("portfolio.verify_claims", {"text": text})
        row.update(unsupported_before=ver.get("unsupported_before", 0), n_claims=ver.get("n_claims", 0),
                   unsupported_after=after["unsupported_before"], words=len(text.split()), text=text,
                   judge=await judge(jobs[g["job_id"]], text), compliance=(st.get("compliance_verdict") or {}).get("status"))
        async for _ in graph.astream(Command(resume={"action": "approve", "user_id": "eval"}), cfg, stream_mode="updates"):
            pass
        st2 = (await graph.aget_state(cfg)).values
        row["submitted"] = st2.get("status") == "submitted"
        row["proposal_id"] = (st2.get("submission") or {}).get("proposal_id")
        return row


def summary(rows: list[dict]) -> dict:
    d = [r for r in rows if r.get("drafted")]
    sub = [r for r in d if r.get("submitted")]
    j = [r["judge"]["overall"] for r in d if r.get("judge")]
    return {"jobs": len(rows), "drafted": len(d), "submitted": len(sub),
            "unsupported_before_per_proposal": round(sum(r["unsupported_before"] for r in d) / max(1, len(d)), 3),
            "unsupported_after_per_proposal": round(sum(r["unsupported_after"] for r in d) / max(1, len(d)), 3),
            "unsupported_claim_rate_before": round(sum(r["unsupported_before"] for r in d) / max(1, sum(r["n_claims"] for r in d)), 4),
            "judge_overall_mean": round(sum(j) / len(j), 3) if j else None,
            "reply_rate": round(sum(r.get("outcome") in ("replied", "interview", "hired") for r in sub) / max(1, len(sub)), 4) if sub else None,
            "hire_rate": round(sum(r.get("outcome") == "hired" for r in sub) / max(1, len(sub)), 4) if sub else None,
            "mean_p_reply": round(sum(r.get("p_reply", 0) for r in sub) / max(1, len(sub)), 4) if sub else None,
            "critic_loops_mean": round(sum(r["revisions"] for r in d) / max(1, len(d)), 3),
            "latency_p50_s": sorted(r["latency_s"] for r in d)[len(d) // 2] if d else None, "latency_p95_s": p95([r["latency_s"] for r in d]),
            "cost_per_proposal_usd": round(sum(r["cost_usd"] for r in d) / max(1, len(d)), 6),
            "tokens_per_proposal": round(sum(r["tokens"] for r in d) / max(1, len(d)), 1)}


async def run(limit: int = 15, personas: list[str] | None = None, concurrency: int = 3, tag: str = "") -> dict:
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.llm import profile_name
    from rag.retriever import get_variant

    gs = setup_inprocess_gigsim()
    admin = TestClient(gs)
    admin.post("/admin/reset", headers=ADMIN)
    personas = personas or PERSONAS
    for p in personas:
        admin.post("/admin/connects", params={"freelancer_id": p, "balance": 100000}, headers=ADMIN)
    jobs = {j["job_id"]: j for j in json.loads((ROOT / "gigsim/data/jobs.json").read_text(encoding="utf-8"))}
    graph = build_bid_graph(checkpointer=InMemorySaver())
    sem = asyncio.Semaphore(concurrency)
    rows: list[dict] = []
    for p in personas:
        gold = [json.loads(x) for x in (ROOT / f"evals/datasets/dev/{p}.jsonl").read_text().splitlines() if x.strip()]
        fixed = [g for g in gold if g["decision"] == "bid" and not g["is_duplicate"]][:limit]  # fixed job set
        prof = json.loads((ROOT / f"data/personas/{p}/profile.json").read_text())
        rows += await asyncio.gather(*(one(graph, p, g, prof, sem, jobs) for g in fixed))
        admin.post("/admin/advance", params={"minutes": 60 * 24 * 25}, headers=ADMIN)  # daily cap: spread submissions
    admin.post("/admin/advance", params={"minutes": 60 * 24 * 3}, headers=ADMIN)
    props = {x["proposal_id"]: x for x in admin.get("/admin/proposals", headers=ADMIN).json()["proposals"]}
    for r in rows:
        pr = props.get(r.get("proposal_id") or "")
        if pr:
            r["outcome"] = pr["status"]
            r["p_reply"] = (pr["decision"] or {}).get("p_reply")
            r["client_reasons"] = (pr["decision"] or {}).get("reasons")
    out = {"profile": profile_name(), "rag_variant": get_variant().NAME, "fixed_job_set": f"first {limit} gold-bid dev jobs per persona",
           "llm_fallbacks": __import__("agent.llm", fromlist=["FALLBACKS"]).FALLBACKS, "overall": summary(rows), "by_persona": {p: summary([r for r in rows if r["persona"] == p]) for p in personas}}
    RES.mkdir(parents=True, exist_ok=True)
    name = f"proposal_eval_{tag or out['rag_variant']}_{out['profile']}"
    (RES / f"{name}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (RES / f"{name}_rows.jsonl").write_text("\n".join(json.dumps(r, default=str) for r in rows) + "\n", encoding="utf-8")
    o = out["overall"]
    print(f"[{out['profile']}/{out['rag_variant']}] drafted={o['drafted']} unsupported/prop before={o['unsupported_before_per_proposal']} "
          f"after={o['unsupported_after_per_proposal']} judge={o['judge_overall_mean']} reply={o['reply_rate']} hire={o['hire_rate']} "
          f"p95={o['latency_p95_s']}s cost/prop=${o['cost_per_proposal_usd']}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--personas", nargs="*", default=PERSONAS)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    asyncio.run(run(a.limit, a.personas, a.concurrency, a.tag))
