"""Bid graph (C1): one thread per job.

  START -> intake -> [Send] analyst | risk_assessor | fit_matcher  (parallel)
        -> decide -> skip/watch: END
                  -> bid: pricing -> writer -> verifier -> critic -(revise, max 2)-> writer
                                                                  -> compliance -(block)-> END
                                                                                -> approval [interrupt]
                                                         approve -> submit -> END
                                                         edit    -> compliance (re-check) -> approval
                                                         reject  -> END (reason saved)

Nothing reaches the marketplace without an `interrupt()` approval. Submission uses deterministic
idempotency keys, so a crash/restart or a retried submit can never send twice (C6).
"""

from __future__ import annotations

import hashlib

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from agent.handoffs import ApprovalDecision
from agent.mcp_client import ToolError
from agent.memory.store import record_edit
from agent.nodes._runtime import node, toolbox
from agent.nodes.analyst import analyst
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic, route_after_critic
from agent.nodes.decision import decide_node
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import intake
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

STOP = {"skipped", "watching", "blocked", "needs_attention", "queued_degraded", "dead_letter", "rejected"}


def final_text(draft: dict, compliance_v: dict) -> str:
    return compliance_v.get("fixed_text") or draft.get("edited_text") or draft.get("cover_letter_verified") or draft["cover_letter"]


def keys(thread_id: str, text: str, amount: float) -> tuple[str, str]:
    h = hashlib.sha256(f"{text}|{amount}".encode()).hexdigest()[:16]
    return f"{thread_id}:draft:{h}"[:120], f"{thread_id}:submit:{h}"[:120]


def fan_out(state: BidState):
    if state.get("status") in STOP:
        return END
    return [Send("analyst", state), Send("risk_assessor", state), Send("fit_matcher", state)]


@node("revise")
async def revise(state: dict) -> dict:
    return {"revisions": int(state.get("revisions") or 0) + 1, "_summary": "sent back to writer"}


@node("approval")
async def approval(state: dict) -> dict:
    d, comp, price = state["draft"], state.get("compliance_verdict", {}), state.get("price", {})
    text = final_text(d, comp)
    answers = [a["answer"] for a in d.get("screening_answers_verified", [])]
    k_draft, _ = keys(state["thread_id"], text, price["amount"])
    preview = await toolbox(state, "submitter").call("marketplace.create_proposal_draft", {
        "job_id": state["job"]["job_id"], "cover_letter": text, "bid_amount": price["amount"], "bid_type": price["bid_type"],
        "screening_answers": answers, "idempotency_key": k_draft, "dry_run": True})
    payload = {
        "kind": "proposal", "thread_id": state["thread_id"], "job_id": state["job"]["job_id"], "job_title": state["job"].get("title"),
        "cover_letter": text, "screening_answers": d.get("screening_answers_verified", []),
        "claims": state.get("verification", {}).get("claims", []), "evidence": state.get("evidence", {}),
        "evidence_map": d.get("evidence_map", {}), "risk_report": state.get("risk_report", {}), "price": price,
        "critiques": state.get("critiques", []), "compliance": comp, "dry_run": preview,
        "connects_cost": preview.get("connects_cost"), "actions": ["approve", "edit", "reject"],
    }
    decision = ApprovalDecision.model_validate(interrupt(payload))
    out: dict = {"approvals": [{**decision.model_dump(), "text_shown": text}], "approval_request": {k: payload[k] for k in ("cover_letter", "connects_cost")}}
    if decision.action == "edit":
        if decision.edited_text and decision.edited_text.strip() != text.strip():
            record_edit(state.get("user_id", "local"), state["job"]["job_id"], text, decision.edited_text)
        out["draft"] = {**d, "edited_text": decision.edited_text or text}
        if decision.edited_amount:
            out["price"] = {**price, "amount": decision.edited_amount}
        out["status"] = "edited"
    elif decision.action == "reject":
        out.update(status="rejected", status_reason=decision.reason or "rejected by user")
    else:
        out["status"] = "approved"
    out["_summary"] = decision.action
    return out


@node("submit")
async def submit(state: dict) -> dict:
    d, comp, price = state["draft"], state.get("compliance_verdict", {}), state["price"]
    text = final_text(d, comp)
    k_draft, k_submit = keys(state["thread_id"], text, price["amount"])
    tb = toolbox(state, "submitter")
    try:
        return await _submit(tb, state, text, price, d, k_draft, k_submit)
    except ToolError as e:  # platform refused (already applied, not enough Connects, policy): visible, not a crash
        return {"status": "needs_attention", "status_reason": f"marketplace refused the submission: {e}"[:300],
                "_summary": "refused by marketplace"}


async def _submit(tb, state: dict, text: str, price: dict, d: dict, k_draft: str, k_submit: str) -> dict:
    draft = await tb.call("marketplace.create_proposal_draft", {
        "job_id": state["job"]["job_id"], "cover_letter": text, "bid_amount": price["amount"], "bid_type": price["bid_type"],
        "screening_answers": [a["answer"] for a in d.get("screening_answers_verified", [])], "idempotency_key": k_draft})
    res = await tb.call("marketplace.submit_proposal", {"proposal_id": draft["proposal_id"], "idempotency_key": k_submit})
    return {"submission": {**res, "proposal_id": draft["proposal_id"], "idempotency_key": k_submit}, "status": "submitted",
            "status_reason": res.get("note") or f"submitted, {res.get('connects_spent')} Connects spent",
            "_summary": f"{res.get('status')} replay={res.get('idempotent_replay')}"}


def route_decide(state: BidState) -> str:
    return "pricing" if state.get("decision", {}).get("action") == "bid" and state.get("status") not in STOP else "end"


def route_simple(nxt: str):
    def r(state: BidState) -> str:
        return "end" if state.get("status") in STOP else nxt
    return r


def route_approval(state: BidState) -> str:
    st = state.get("status")
    return {"approved": "submit", "edited": "compliance"}.get(st, "end")


def build_bid_graph(checkpointer=None, store=None, stop_before: list[str] | None = None):
    """stop_before=['writer'] runs analysis + decision + pricing only (decision evals)."""
    g = StateGraph(BidState)
    for name, fn in [("intake", intake), ("analyst", analyst), ("risk_assessor", risk_assessor), ("fit_matcher", fit_matcher),
                     ("decide", decide_node), ("pricing", pricing), ("writer", writer), ("verifier", verifier), ("critic", critic),
                     ("revise", revise), ("compliance", compliance), ("approval", approval), ("submit", submit)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge(["analyst", "risk_assessor", "fit_matcher"], "decide")
    g.add_conditional_edges("decide", route_decide, {"pricing": "pricing", "end": END})
    g.add_conditional_edges("pricing", route_simple("writer"), {"writer": "writer", "end": END})
    g.add_conditional_edges("writer", route_simple("verifier"), {"verifier": "verifier", "end": END})
    g.add_conditional_edges("verifier", route_simple("critic"), {"critic": "critic", "end": END})
    g.add_conditional_edges("critic", route_after_critic, {"revise": "revise", "compliance": "compliance", "end": END})
    g.add_edge("revise", "writer")
    g.add_conditional_edges("compliance", route_simple("approval"), {"approval": "approval", "end": END})
    g.add_conditional_edges("approval", route_approval, {"submit": "submit", "compliance": "compliance", "end": END})
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store, interrupt_before=stop_before)
