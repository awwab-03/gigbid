"""Client Liaison: read client replies, classify intent, draft a response or interview slots,
and keep the pipeline current. Client messages are untrusted; nothing is sent without approval."""

from __future__ import annotations

import json
import re

from agent.guardrails import detect_injection, quarantine, wrap_untrusted
from agent.handoffs import IntentClassification, ReplyDraft
from agent.llm import call_json, call_text
from agent.memory.store import style_rules
from agent.nodes._runtime import node, toolbox

INTENT_RULES = [
    ("scam_signal", r"\b(whats\s?app|telegram|skype|outside the platform|verification fee|pay .{0,20}fee|send .{0,20}(email|password))\b"),
    ("interview_request", r"\b(call|interview|time slots?|available .{0,20}(this|next) week|meet)\b"),
    ("negotiation", r"\$\s?\d|budget is tight|lower (price|rate)|would you consider|could you do it for"),
    ("question", r"\?"),
]
DECLINE_OFF_PLATFORM = ("Thanks for getting back to me. I keep all communication and payments on the platform, which protects "
                        "us both, so I'm happy to continue right here. Is there anything else you'd like to know about the project?")


def rule_intent(text: str) -> IntentClassification:
    for intent, pat in INTENT_RULES:
        if re.search(pat, text, re.I):
            m = re.search(r"\$\s?([\d,]+)", text)
            return IntentClassification(intent=intent, confidence=0.6, asked_price=float(m.group(1).replace(",", "")) if m else None,
                                        injection_detected=bool(detect_injection(text)), summary="rule-based")
    return IntentClassification(intent="other", confidence=0.4, injection_detected=bool(detect_injection(text)))


@node("load_thread")
async def load_thread(state: dict) -> dict:
    t = await toolbox(state, "client_liaison").call("marketplace.list_messages", {"thread_id": state["marketplace_thread_id"]})
    msgs = t["messages"]
    last = next((m for m in reversed(msgs) if m["sender"] == "client"), None)
    if not last or (msgs and msgs[-1]["sender"] == "freelancer"):
        return {"messages": msgs, "status": "waiting_for_client", "_summary": "no new client message"}
    return {"messages": msgs, "last_client_message": last, "status": "drafting", "_summary": last["body"][:80]}


@node("classify")
async def classify(state: dict) -> dict:
    msg = state["last_client_message"]["body"]
    spans = detect_injection(msg)
    history = " | ".join(f"{m['sender']}: {m['body'][:120]}" for m in state.get("messages", [])[-6:-1])
    rule = rule_intent(quarantine(msg, spans))
    try:
        ic = await call_json("intent", "client_intent", {"history": history,
                                                         "message": wrap_untrusted(quarantine(msg, spans), "client_message")},
                             IntentClassification)
        if rule.intent == "scam_signal":  # deterministic safety signal always wins
            ic.intent = "scam_signal"
        ic.asked_price = ic.asked_price or rule.asked_price
    except Exception:  # noqa: BLE001
        ic = rule
    ic.injection_detected = ic.injection_detected or bool(spans)
    return {"intent": {**ic.model_dump(), "injection_spans": spans}, "_summary": ic.intent}


@node("plan_reply")
async def plan_reply(state: dict) -> dict:
    intent = state["intent"]["intent"]
    if intent == "interview_request":
        res = await toolbox(state, "client_liaison").call("workspace.free_slots", {"days": 5, "duration_min": 30, "max_slots": 3,
                                                                                    "timezone_name": state.get("profile", {}).get("timezone", "Asia/Karachi")})
        return {"slots": res["slots"], "_summary": f"{len(res['slots'])} slots"}
    return {"slots": []}


@node("draft_reply")
async def draft_reply(state: dict) -> dict:
    intent = state["intent"]
    msg = state["last_client_message"]["body"]
    prof, prop = state.get("profile", {}), state.get("proposal", {})
    floor = prof.get("min_fixed") if prop.get("bid_type") != "hourly" else prof.get("hourly_floor")
    if intent["intent"] == "scam_signal":
        body = DECLINE_OFF_PLATFORM
    else:
        pricing = {"floor": floor, "current_bid": prop.get("bid_amount"), "client_asked": intent.get("asked_price"),
                   "rule": "accept the client's price only if it is at or above the floor; otherwise offer a reduced scope at the floor"}
        body = await call_text("client_liaison", "client_reply", {
            "intent": intent["intent"], "message": wrap_untrusted(quarantine(msg, intent.get("injection_spans", [])), "client_message"),
            "proposal": (prop.get("cover_letter") or "")[:800], "pricing": json.dumps(pricing),
            "slots": json.dumps([s["label"] for s in state.get("slots", [])]), "evidence": "(see proposal)",
            "style_rules": json.dumps(style_rules(state.get("user_id", "local")))})
        if intent["intent"] == "interview_request" and state.get("slots") and not any(s["label"][:3] in body for s in state["slots"]):
            body += " I'm free " + ", or ".join(s["label"] for s in state["slots"]) + "."
    r = ReplyDraft(thread_id=state["marketplace_thread_id"], body=body.strip(), proposed_slots=[s["label"] for s in state.get("slots", [])],
                   intent=intent["intent"])
    return {"reply": r.model_dump(), "_summary": f"{len(body.split())} words"}


@node("reply_compliance")
async def reply_compliance(state: dict) -> dict:
    from agent.nodes.compliance import check_text

    policy = {"version": "messages", "min_cover_letter_words": 0, "max_cover_letter_words": 400}
    text = state["reply"].get("edited_body") or state["reply"]["body"]
    prop = state.get("proposal", {})
    prices = [float(p.replace(",", "")) for p in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", text)]
    prof = state.get("profile", {})
    floor = prof.get("min_fixed") if prop.get("bid_type") != "hourly" else prof.get("hourly_floor")
    v = check_text(text, risk={"injection_spans": state["intent"].get("injection_spans", [])}, verification=None, policy=policy,
                   bid=min(prices) if prices else None, floor=floor)
    out = {"compliance_verdict": v.model_dump(), "_summary": v.status}
    if v.status == "block":
        out.update(status="blocked", status_reason="; ".join(x.detail for x in v.violations))
    return out
