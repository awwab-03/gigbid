"""Bid graph against GigSim (in-process) with the deterministic fake model.

Covers: parallel analysis -> approval interrupt; approve -> submitted exactly once even when the
process "crashes" after approval and a fresh graph resumes from the checkpoint; scams skipped;
reject keeps the reason.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

os.environ["MODEL_PROFILE"] = "fake"
os.environ["MCP_TRANSPORT"] = "inproc"
ROOT = Path(__file__).resolve().parents[2]
ADMIN = {"X-Admin-Token": "gigsim-admin"}
pytestmark = pytest.mark.asyncio


def gold(persona: str, pred) -> dict:
    rows = [json.loads(x) for x in (ROOT / f"evals/datasets/dev/{persona}.jsonl").read_text().splitlines() if x.strip()]
    return next(r for r in rows if pred(r))


def start(job_id: str, persona: str, tid: str) -> dict:
    return {"thread_id": tid, "user_id": "itest", "account": persona, "job": {"job_id": job_id}, "skip_dedup": True,
            "profile": json.loads((ROOT / f"data/personas/{persona}/profile.json").read_text())}


async def run(g, inp, cfg):
    async for _ in g.astream(inp, cfg, stream_mode="updates"):
        pass
    return await g.aget_state(cfg)


async def test_approve_survives_restart_and_submits_once(marketplace_mcp, gigsim_client):
    from agent.graphs.bid_graph import build_bid_graph

    gigsim_client.post("/admin/connects", params={"freelancer_id": "data_analyst", "balance": 500}, headers=ADMIN)
    g0 = gold("data_analyst", lambda r: r["decision"] == "bid" and not r["has_injection"] and r["coverage"] == 1)
    saver = InMemorySaver()
    cfg = {"configurable": {"thread_id": "it-1"}}
    st = await run(build_bid_graph(checkpointer=saver), start(g0["job_id"], "data_analyst", "it-1"), cfg)
    assert st.next == ("approval",), st.values.get("status_reason")
    assert st.values["decision"]["action"] == "bid"
    assert {"job_spec", "risk_report", "fit_report"} <= set(st.values)
    before = gigsim_client.get("/admin/proposals", headers=ADMIN).json()["proposals"]

    # "crash": a brand-new graph object on the same durable checkpoint resumes the approval
    st = await run(build_bid_graph(checkpointer=saver), Command(resume={"action": "approve"}), cfg)
    assert st.values["status"] == "submitted"
    sub = st.values["submission"]
    # a retried resume replays from the checkpoint: idempotency keys prevent a second submission
    from agent.mcp_client import Toolbox

    again = await Toolbox("submitter", "itest", "data_analyst").call(
        "marketplace.submit_proposal", {"proposal_id": sub["proposal_id"], "idempotency_key": sub["idempotency_key"]})
    assert again["idempotent_replay"] is True
    after = gigsim_client.get("/admin/proposals", headers=ADMIN).json()["proposals"]
    submitted = [p for p in after if p["job_id"] == g0["job_id"] and p["status"] != "draft"]
    assert len(submitted) == 1
    assert len(after) - len(before) == 1


async def test_scam_is_skipped_without_drafting(marketplace_mcp):
    from agent.graphs.bid_graph import build_bid_graph

    g0 = gold("ml_engineer", lambda r: r["is_scam"] and r["scam_type"] in ("upfront_fee", "credential_phish", "unpaid_trial"))
    cfg = {"configurable": {"thread_id": "it-2"}}
    st = await run(build_bid_graph(checkpointer=InMemorySaver()), start(g0["job_id"], "ml_engineer", "it-2"), cfg)
    assert st.values["decision"]["action"] == "skip"
    assert st.values["risk_report"]["scam_likely"] is True
    assert "draft" not in st.values and not st.next


async def test_reject_keeps_reason(marketplace_mcp, gigsim_client):
    from agent.graphs.bid_graph import build_bid_graph

    gigsim_client.post("/admin/connects", params={"freelancer_id": "data_analyst", "balance": 500}, headers=ADMIN)
    g0 = gold("data_analyst", lambda r: r["decision"] == "bid" and not r["has_injection"] and r["coverage"] == 1)
    cfg = {"configurable": {"thread_id": "it-3"}}
    g = build_bid_graph(checkpointer=InMemorySaver())
    st = await run(g, start(g0["job_id"], "data_analyst", "it-3"), cfg)
    assert st.next == ("approval",), (st.values.get("status"), st.values.get("status_reason"), st.values.get("fit_report", {}).get("score"))
    st = await run(g, Command(resume={"action": "reject", "reason": "budget too low"}), cfg)
    assert st.values["status"] == "rejected" and st.values["status_reason"] == "budget too low"
    assert "submission" not in st.values
