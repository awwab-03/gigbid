"""Bid decision: skip / watch / bid from the three parallel analyses. Deterministic and explainable;
thresholds live in agent/config.yaml."""

from __future__ import annotations

from agent.handoffs import BidDecision
from agent.llm import CFG
from agent.nodes._runtime import node


def decide(job: dict, risk: dict, fit: dict, profile: dict) -> BidDecision:
    th = CFG["thresholds"]
    reasons: list[str] = []
    b = job.get("budget", {})
    floor = profile.get("hourly_floor", 0) if b.get("type") == "hourly" else profile.get("min_fixed", 0)
    if risk.get("scam_likely"):
        return BidDecision(action="skip", reasons=["likely scam: " + ", ".join(risk.get("flags", [])[:4])], confidence=0.9)
    if risk.get("client_quality", 1) < th["minimum_client_quality"]:
        reasons.append(f"client quality {risk.get('client_quality')} below {th['minimum_client_quality']}")
    if risk.get("score", 0) > th["maximum_risk_score"]:
        reasons.append(f"risk {risk.get('score')} above {th['maximum_risk_score']}")
    if (b.get("max") or 0) < floor:
        reasons.append(f"budget {b.get('max')} below your floor {floor}")
    fs = fit.get("score", 0)
    if reasons:
        return BidDecision(action="skip", reasons=reasons, confidence=0.8)
    if fs >= th["minimum_fit_score"]:
        return BidDecision(action="bid", reasons=[f"fit {fs:.2f} >= {th['minimum_fit_score']}"] + fit.get("reasons", [])[:2],
                           confidence=min(0.95, 0.5 + fs / 2))
    if fs >= th["watch_fit_score"]:
        return BidDecision(action="watch", reasons=[f"fit {fs:.2f} is borderline"] + fit.get("reasons", [])[1:3], confidence=0.5)
    return BidDecision(action="skip", reasons=[f"fit {fs:.2f} below {th['watch_fit_score']}"] + fit.get("reasons", [])[1:3],
                       confidence=0.75)


@node("decide")
async def decide_node(state: dict) -> dict:
    if state.get("decision"):  # already decided (e.g. duplicate at intake)
        return {}
    d = decide(state["job"], state.get("risk_report", {}), state.get("fit_report", {}), state.get("profile", {}))
    auto = d.action == "skip" and state.get("autonomy") == "auto_skip"
    d.auto = auto
    status = {"skip": "skipped", "watch": "watching", "bid": "analysing"}[d.action]
    return {"decision": d.model_dump(), "status": status, "status_reason": "; ".join(d.reasons)[:300], "_summary": d.action}
