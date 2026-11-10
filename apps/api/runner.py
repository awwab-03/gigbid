"""Runs LangGraph threads and turns their stream into stored, replayable UI events.

Used by the worker (production) and by the API in single-process dev mode. Each run:
  * gets a trace id that flows to every MCP call (X-Trace-Id) and the audit logs
  * streams `updates` from LangGraph; each node update becomes a run_event (SSE replays them)
  * on interrupt, stores the approval payload in runs.pending, so a refresh never loses it
  * updates the job inbox row (fit, risk, action, price, status)
  * is traced in LangSmith with thread/job metadata when LANGSMITH_TRACING is set
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from langgraph.types import Command

from agent.checkpoint import get_checkpointer
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.memory.store import get_store
from apps.api import db
from shared.pii import mask_obj
from shared.security import new_trace_id, trace_id_var

ROOT = Path(__file__).resolve().parents[2]
_graphs: dict[str, object] = {}


async def graph(kind: str):
    if kind not in _graphs:
        cp = await get_checkpointer()
        _graphs[kind] = (build_bid_graph if kind == "bid" else build_conversation_graph)(checkpointer=cp, store=get_store())
    return _graphs[kind]


def profile_for(user: dict) -> dict:
    s = user.get("settings") or {}
    p = ROOT / "data" / "personas" / user["account"] / "profile.json"
    base = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    for k in ("hourly_floor", "hourly_target", "min_fixed", "timezone", "name", "headline"):
        if s.get(k) is not None:
            base[k] = s[k]
    return base


def _trace_url(run_id: str) -> str | None:
    if not os.getenv("LANGSMITH_API_KEY"):
        return None
    try:
        from langsmith import Client

        c = Client()
        return c.get_run_url(run=c.read_run(run_id), project_name=os.getenv("LANGSMITH_PROJECT", "gigbid"))
    except Exception:  # noqa: BLE001 - trace link is best effort
        return None


def _index_job(user_id: str, state: dict) -> None:
    job = state.get("job") or {}
    if not job.get("job_id"):
        return
    fit, risk, dec, price = (state.get(k) or {} for k in ("fit_report", "risk_report", "decision", "price"))
    db.upsert_job(user_id, job["job_id"], thread_id=state.get("thread_id"), title=job.get("title"), category=job.get("category"),
                  status=state.get("status"), action=dec.get("action"), fit=fit.get("score"), risk=risk.get("score"),
                  scam=int(bool(risk.get("scam_likely"))), price=price.get("amount"), bid_type=price.get("bid_type") or job.get("budget", {}).get("type"),
                  connects=price.get("connects_cost") or job.get("connects_cost"), flags=risk.get("flags", []),
                  reason=state.get("status_reason") or "; ".join(dec.get("reasons", [])), job=job,
                  proposal_id=(state.get("submission") or {}).get("proposal_id"), posted_at=job.get("posted_at"),
                  pipeline="submitted" if state.get("status") == "submitted" else None)


async def _drive(kind: str, user: dict, thread_id: str, inp, ref: str, checkpoint_id: str | None = None) -> dict:
    g = await graph(kind)
    trace_id = new_trace_id()
    trace_id_var.set(trace_id)
    run_id = str(uuid.uuid4())
    conf = {"thread_id": thread_id, **({"checkpoint_id": checkpoint_id} if checkpoint_id else {})}
    cfg = {"configurable": conf, "run_id": run_id, "run_name": f"{kind}:{ref}",
           "metadata": {"thread_id": thread_id, "user_id": user["id"], "trace_id": trace_id, "kind": kind, "ref": ref},
           "tags": [kind, user["account"]], "recursion_limit": 60}
    db.upsert_run(thread_id, user["id"], kind=kind, ref=ref, status="running", trace_id=trace_id, pending=None)
    db.add_event(thread_id, user["id"], "run_started", None, {"trace_id": trace_id})
    t0 = time.perf_counter()
    if isinstance(inp, dict):
        inp["trace_id"] = trace_id
    try:
        async for chunk in g.astream(inp, cfg, stream_mode="updates"):
            for node, upd in chunk.items():
                if node == "__interrupt__":
                    payload = upd[0].value
                    db.upsert_run(thread_id, user["id"], status="awaiting_approval", pending=payload)
                    db.add_event(thread_id, user["id"], "approval_required", node, {"kind": payload.get("kind")})
                    continue
                upd = upd or {}
                tr = (upd.get("trace") or [{}])[0]
                db.add_event(thread_id, user["id"], "node", node, mask_obj({"status": upd.get("status"), "summary": tr.get("summary"),
                                                                             "latency_s": tr.get("latency_s"), "tokens": tr.get("tokens"),
                                                                             "cost_usd": tr.get("cost_usd"), "models": tr.get("models")}))
    except Exception as e:  # noqa: BLE001 - surface as a visible failed run
        db.upsert_run(thread_id, user["id"], status="failed", error=str(e)[:1000])
        db.add_event(thread_id, user["id"], "error", None, {"error": str(e)[:500]})
        raise
    snap = await g.aget_state({"configurable": {"thread_id": thread_id}})
    st = snap.values
    pending = bool(snap.next)
    status = "awaiting_approval" if pending else st.get("status", "done")
    if kind == "bid":
        _index_job(user["id"], {**st, "status": status})
    dt = time.perf_counter() - t0
    prev = db.events_after(thread_id, user["id"], 0)
    db.upsert_run(thread_id, user["id"], status=status, tokens=int(st.get("tokens") or 0), cost_usd=float(st.get("cost_usd") or 0),
                  latency_s=round(dt, 3), node_latency=st.get("node_latency"), trace_url=_trace_url(run_id),
                  **({} if pending else {"pending": None}))
    db.add_event(thread_id, user["id"], "run_finished", None, {"status": status, "events": len(prev)})
    return {"thread_id": thread_id, "status": status}


async def analyze_job(user: dict, job_id: str, job: dict | None = None) -> dict:
    thread_id = f"bid:{user['id']}:{job_id}"
    inp = {"thread_id": thread_id, "user_id": user["id"], "account": user["account"], "job": job or {"job_id": job_id},
           "profile": profile_for(user), "autonomy": (user.get("settings") or {}).get("autonomy", "suggest")}
    db.upsert_job(user["id"], job_id, thread_id=thread_id, status="analysing", title=(job or {}).get("title"))
    return await _drive("bid", user, thread_id, inp, job_id)


async def resume(user: dict, thread_id: str, decision: dict) -> dict:
    kind = "bid" if thread_id.startswith("bid:") else "conv"
    return await _drive(kind, user, thread_id, Command(resume={**decision, "user_id": user["id"]}), thread_id.split(":")[-1])


async def converse(user: dict, mp_thread_id: str, proposal: dict | None = None, job: dict | None = None) -> dict:
    thread_id = f"conv:{user['id']}:{mp_thread_id}:{uuid.uuid4().hex[:6]}"
    inp = {"thread_id": thread_id, "user_id": user["id"], "account": user["account"], "marketplace_thread_id": mp_thread_id,
           "proposal": proposal or {}, "job": job or {}, "profile": profile_for(user)}
    return await _drive("conv", user, thread_id, inp, mp_thread_id)


async def retry_degraded(user: dict, thread_id: str) -> dict:
    """Re-run a thread that stopped in degraded mode (marketplace down) from its last good checkpoint."""
    g = await graph("bid")
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await g.aget_state(cfg)
    last_node = (snap.values.get("trace") or [{}])[-1].get("node")
    await g.aupdate_state(cfg, {"status": "approved" if last_node == "submit" else "analysing", "status_reason": "retrying"},
                          as_node="approval" if last_node == "submit" else "intake")
    return await _drive("bid", user, thread_id, None, thread_id.split(":")[-1])


async def replay(user: dict, thread_id: str, checkpoint_id: str) -> dict:
    kind = "bid" if thread_id.startswith("bid:") else "conv"
    return await _drive(kind, user, thread_id, None, f"replay:{checkpoint_id[-8:]}", checkpoint_id=checkpoint_id)
