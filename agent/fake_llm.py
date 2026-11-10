"""Deterministic stand-in model for CI, Playwright and integration tests (MODEL_PROFILE=fake).

It never pretends to be a quality model: it fills each node's schema from the variables it was
given (heuristic JobSpec, a cover letter assembled from the cited evidence, a rule-based critique).
Reported numbers never come from this profile; evals record which profile produced them.
"""

from __future__ import annotations

import json
import re
from typing import Any


def _evidence_lines(table: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for line in table.splitlines():
        m = re.match(r"\[(E\d+)\] \((\w+), project: ([^)]*)\) (.*)", line.strip())
        if m and m.group(3) not in seen and m.group(3) != "-":
            seen.add(m.group(3))
            out.append((m.group(1), m.group(3)))
    return out


def respond(prompt: str, variables: dict[str, Any]) -> str:
    if prompt == "analyst":
        return json.dumps({"job_id": "x", "title": "x", "requirements": [], "hidden_needs": ["clear handover documentation"]})
    if prompt == "risk_assessor":
        return json.dumps({"score": 0.3, "flags": [], "scam_likely": False, "explanation": "fake model: no extra signals"})
    if prompt == "writer":
        spec = json.loads(variables.get("job_spec") or "{}")
        ev = _evidence_lines(variables.get("evidence", ""))
        title = spec.get("title") or "your project"
        parts = [f"Your {title.lower()} needs someone who has shipped this kind of work before."]
        for eid, proj in ev[:2]:
            parts.append(f"In {proj} I delivered a comparable result for a client [{eid}].")
        parts.append("I would start by agreeing a clear acceptance test with you in week one, then ship a first working version, "
                     "review it together and document the handover.")
        parts.append("Which result matters most to you for the first milestone?")
        answers = [{"question": q, "answer": "I would answer this from the projects above and confirm details on a call."}
                   for q in spec.get("screening_questions") or []]
        return json.dumps({"cover_letter": " ".join(parts), "screening_answers": answers, "cited_evidence": [e for e, _ in ev[:2]]})
    if prompt == "critic":
        checks = json.loads(variables.get("checks") or "[]")
        return json.dumps({"score": 8 if len(checks) <= 1 else 5, "passed": len(checks) <= 1, "issues": checks,
                           "revise_instructions": "Address: " + "; ".join(checks)})
    if prompt == "client_intent":
        return json.dumps({"intent": "other", "confidence": 0.3})
    if prompt == "client_reply":
        slots = json.loads(variables.get("slots") or "[]")
        s = (" I'm available " + ", or ".join(slots) + ".") if slots else ""
        return "Thanks for your message. Happy to help with this and keep everything here on the platform." + s
    if prompt == "judge":
        return json.dumps({"relevance": 3, "specificity": 3, "personalisation": 3, "credibility": 3, "clarity": 3, "overall": 3,
                           "rationale": "fake"})
    if prompt in ("verifier_rewrite", "crag_rewrite"):
        return variables.get("claim") or variables.get("requirement") or ""
    return "{}"
