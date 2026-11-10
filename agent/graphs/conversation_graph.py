"""Conversation graph (C1): one thread per client conversation.

  START -> load_thread -> classify -> plan_reply (calendar slots for interview requests)
        -> draft_reply -> reply_compliance -(block)-> END
                                           -> approval [interrupt] -> approve: send (+ tentative hold) -> END
                                                                   -> edit: reply_compliance -> approval
                                                                   -> reject: END
"""

from __future__ import annotations

import hashlib

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.memory.store import record_edit
from agent.nodes._runtime import node, toolbox
from agent.nodes.client_liaison import (
    classify,
    draft_reply,
    load_thread,
    plan_reply,
    reply_compliance,
)
from agent.state import ConversationState

STOP = {"blocked", "needs_attention", "queued_degraded", "dead_letter", "rejected", "waiting_for_client"}


def _text(state: dict) -> str:
    return state.get("compliance_verdict", {}).get("fixed_text") or state["reply"].get("edited_body") or state["reply"]["body"]


def _key(state: dict, text: str) -> str:
    return f"{state['thread_id']}:msg:{hashlib.sha256(text.encode()).hexdigest()[:16]}"


@node("reply_approval")
async def reply_approval(state: dict) -> dict:
    text = _text(state)
    preview = await toolbox(state, "client_liaison").call("marketplace.send_message", {
        "thread_id": state["marketplace_thread_id"], "body": text, "idempotency_key": _key(state, text), "dry_run": True})
    payload = {"kind": "message", "thread_id": state["thread_id"], "marketplace_thread_id": state["marketplace_thread_id"],
               "client_message": state["last_client_message"], "intent": state["intent"], "reply": text,
               "slots": state.get("slots", []), "compliance": state.get("compliance_verdict", {}), "dry_run": preview,
               "actions": ["approve", "edit", "reject"]}
    d = ApprovalDecision.model_validate(interrupt(payload))
    out: dict = {"approvals": [{**d.model_dump(), "text_shown": text}]}
    if d.action == "edit":
        if d.edited_text and d.edited_text.strip() != text.strip():
            record_edit(state.get("user_id", "local"), state["marketplace_thread_id"], text, d.edited_text)
        out.update(reply={**state["reply"], "edited_body": d.edited_text or text}, status="edited")
    elif d.action == "reject":
        out.update(status="rejected", status_reason=d.reason or "rejected by user")
    else:
        out["status"] = "approved"
    return out


@node("send")
async def send(state: dict) -> dict:
    text = _text(state)
    tb = toolbox(state, "client_liaison")
    res = await tb.call("marketplace.send_message", {"thread_id": state["marketplace_thread_id"], "body": text,
                                                     "idempotency_key": _key(state, text)})
    hold = None
    if state.get("slots"):
        s = state["slots"][0]
        hold = await tb.call("workspace.create_interview_hold", {"start": s["start"], "duration_min": 30,
                                                                  "title": f"Interview hold ({state['marketplace_thread_id']})",
                                                                  "idempotency_key": _key(state, "hold" + s["start"])})
    return {"sent": {**res, "hold": hold}, "status": "sent", "_summary": f"sent {res.get('message_id')}"}


def _r(nxt: str):
    def f(state: dict) -> str:
        return "end" if state.get("status") in STOP else nxt
    return f


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    for name, fn in [("load_thread", load_thread), ("classify", classify), ("plan_reply", plan_reply), ("draft_reply", draft_reply),
                     ("reply_compliance", reply_compliance), ("reply_approval", reply_approval), ("send", send)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _r("classify"), {"classify": "classify", "end": END})
    g.add_edge("classify", "plan_reply")
    g.add_conditional_edges("plan_reply", _r("draft_reply"), {"draft_reply": "draft_reply", "end": END})
    g.add_conditional_edges("draft_reply", _r("reply_compliance"), {"reply_compliance": "reply_compliance", "end": END})
    g.add_conditional_edges("reply_compliance", _r("reply_approval"), {"reply_approval": "reply_approval", "end": END})
    g.add_conditional_edges("reply_approval", lambda s: {"approved": "send", "edited": "reply_compliance"}.get(s.get("status"), "end"),
                            {"send": "send", "reply_compliance": "reply_compliance", "end": END})
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)
