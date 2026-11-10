"""Risk Assessor: client quality from marketplace history + scam and injection signals.

Deterministic signals first (cheap, auditable); the small LLM is consulted only when the signals
are ambiguous (config: risk_llm_band), to keep cost per job low.
"""

from __future__ import annotations

import json
import re

from agent.guardrails import detect_injection, wrap_untrusted
from agent.handoffs import RiskReport
from agent.llm import CFG, call_json
from agent.nodes._runtime import node, toolbox

SCAM_SIGNALS = {
    "unpaid_work": r"\b(free (test|trial|sample)|unpaid|for free as a test|pay only the winner|complete the full .{0,60} as a free)\b",
    "off_platform_contact": r"\b(whats\s?app|telegram|skype|signal|wechat)\b|\+\d[\d\s().-]{8,}\d",
    "upfront_fee": r"\b(registration|onboarding|verification|refundable|training) fee\b|pay (a|an) .{0,20}fee",
    "credential_request": r"\b(send|share) (your|the) (login|password|credentials|bank details)\b|login email and password",
    "off_platform_payment": r"\b(usdt|bitcoin|crypto|western union|outside the platform to avoid fees|directly to your wallet)\b",
    "overpayment": r"\b(cheque|check)\b.{0,80}\b(forward|send) the rest\b",
}


def client_quality(c: dict) -> float:
    q = 0.5 + (0.2 if c.get("payment_verified") else -0.3) + min(0.2, (c.get("hires") or 0) * 0.02)
    if c.get("feedback_score") is not None:
        q += (c["feedback_score"] - 4.0) * 0.2
    q -= 0.1 * (c.get("disputes") or 0)
    return max(0.0, min(1.0, q))


def signals(job: dict, client: dict) -> tuple[list[str], list[str]]:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    flags = [name for name, pat in SCAM_SIGNALS.items() if re.search(pat, text, re.I)]
    b = job.get("budget", {})
    if b.get("type") == "fixed" and (b.get("max") or 0) < 60:
        flags.append("near_zero_budget")
    if not client.get("payment_verified"):
        flags.append("payment_unverified")
    if (client.get("total_spent_usd") or 0) == 0 and (client.get("hires") or 0) == 0:
        flags.append("no_hiring_history")
    if (client.get("disputes") or 0) >= 2:
        flags.append("dispute_history")
    return flags, detect_injection(job.get("description", ""))


@node("risk_assessor")
async def risk_assessor(state: dict) -> dict:
    job = state["job"]
    client = await toolbox(state, "risk_assessor").call("marketplace.get_client_history", {"client_id": job["client_id"]})
    flags, inj = signals(job, client)
    cq = client_quality(client)
    hard = {"unpaid_work", "upfront_fee", "credential_request", "off_platform_payment", "overpayment"}
    scam = bool(hard & set(flags)) or ("off_platform_contact" in flags and "payment_unverified" in flags)
    score = min(1.0, 0.55 * scam + 0.15 * ("off_platform_contact" in flags) + 0.4 * (1 - cq) + 0.1 * bool(inj)
                + 0.1 * ("near_zero_budget" in flags))
    report = RiskReport(score=round(score, 3), flags=flags + (["prompt_injection"] if inj else []), scam_likely=scam,
                        injection_detected=bool(inj), injection_spans=inj, client_quality=round(cq, 3),
                        explanation=("; ".join(flags) or "no red flags") + (f"; injected instructions quarantined ({len(inj)})" if inj else ""))
    lo, hi = CFG.get("risk_llm_band", [0.35, 0.6])
    if lo <= score <= hi:  # ambiguous: ask the small model
        try:
            llm = await call_json("risk_assessor", "risk_assessor", {"client": json.dumps(client), "signals": json.dumps(flags),
                                                               "job_post": wrap_untrusted(job.get("description", ""))}, RiskReport)
            report.scam_likely = report.scam_likely or llm.scam_likely
            report.score = round((report.score + llm.score) / 2, 3)
            report.explanation += f" | model: {llm.explanation[:200]}"
        except Exception:  # noqa: BLE001
            pass
    return {"client": client, "risk_report": report.model_dump(), "_summary": f"risk {report.score} {report.flags}"}
