"""Critic: grounding, personalisation and length; sends the draft back with reasons, at most twice."""

from __future__ import annotations

import json
import re

from agent.handoffs import Critique
from agent.llm import CFG, call_json
from agent.nodes._runtime import node

GENERIC = [r"dear (sir|madam|hiring manager)", r"i am (very )?passionate", r"i have read your job", r"perfect (fit|candidate)",
           r"i can do (this|your) (job|task)", r"to whom it may concern"]


def deterministic_checks(text: str, job_spec: dict, verification: dict) -> list[str]:
    issues = []
    words = len(text.split())
    if words < 80:
        issues.append(f"too short ({words} words)")
    if words > 260:
        issues.append(f"too long ({words} words)")
    first = " ".join(re.split(r"(?<=[.!?])\s+", text.strip())[:2]).lower()
    if any(re.search(p, text.lower()) for p in GENERIC):
        issues.append("generic phrasing")
    terms = {w for w in re.findall(r"[a-z]{5,}", (job_spec.get("title", "") + " " + " ".join(job_spec.get("deliverables", []))).lower())}
    if terms and not any(t in first for t in terms):
        issues.append("opening does not mention the client's project")
    if verification.get("unsupported_before", 0) >= 2:
        issues.append(f"{verification['unsupported_before']} unsupported claims had to be removed")
    if not text.strip().endswith("?"):
        issues.append("does not end with a question for the client")
    return issues


@node("critic")
async def critic(state: dict) -> dict:
    d, spec, ver = state["draft"], state.get("job_spec", {}), state.get("verification", {})
    text = d.get("cover_letter_verified") or d["cover_letter"]
    checks = deterministic_checks(text, spec, ver)
    try:
        c = await call_json("critic", "critic", {"job_spec": json.dumps({k: spec.get(k) for k in ("title", "requirements", "screening_questions")}),
                                           "draft": text, "answers": json.dumps(d.get("screening_answers_verified", [])),
                                           "verification": json.dumps({k: ver.get(k) for k in ("n_claims", "unsupported_before")}),
                                           "checks": json.dumps(checks)}, Critique)
    except Exception:  # noqa: BLE001 - deterministic critique if the model fails
        c = Critique(score=max(0, 9 - 2 * len(checks)), passed=len(checks) <= 1, issues=checks,
                     revise_instructions="Fix: " + "; ".join(checks))
    hard = [i for i in checks if i.startswith(("generic", "too long", "opening"))]
    c.issues = list(dict.fromkeys(c.issues + checks))
    c.passed = c.score >= CFG["thresholds"]["critic_pass_score"] and not hard
    return {"critiques": [c.model_dump()], "_summary": f"score {c.score} {'pass' if c.passed else 'revise'}"}


def route_after_critic(state: dict) -> str:
    if state.get("status") in ("needs_attention", "dead_letter", "queued_degraded"):
        return "end"
    last = (state.get("critiques") or [{}])[-1]
    if last.get("passed") or int(state.get("revisions") or 0) >= CFG["budgets"]["max_revisions"]:
        return "compliance"
    return "revise"
