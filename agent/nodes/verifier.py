"""Claim verification step (B3): runs BEFORE the Critic; unsupported claims are removed or rewritten."""

from __future__ import annotations

from agent.handoffs import ClaimReport
from agent.nodes._runtime import node, toolbox
from agent.nodes.writer import strip_citations


@node("verifier")
async def verifier(state: dict) -> dict:
    d = state["draft"]
    text = strip_citations(d["cover_letter"])
    tb = toolbox(state, "verifier")
    res = await tb.call("portfolio.verify_claims", {"text": text, "evidence_ids": d.get("cited_evidence", [])[:40]})
    answers = []
    for a in d.get("screening_answers", []):
        r = await tb.call("portfolio.verify_claims", {"text": strip_citations(a["answer"]), "evidence_ids": d.get("cited_evidence", [])[:40]})
        answers.append({"question": a["question"], "answer": r["fixed_text"], "unsupported": r["unsupported_before"]})
    report = ClaimReport(claims=res["claims"], n_claims=res["n_claims"], unsupported_before=res["unsupported_before"],
                         unsupported_rate_before=res["unsupported_rate_before"], fixed_text=res["fixed_text"])
    fixed = {**d, "cover_letter_verified": res["fixed_text"], "screening_answers_verified": answers}
    return {"verification": {**report.model_dump(), "answers_unsupported": sum(a["unsupported"] for a in answers)},
            "draft": fixed, "_summary": f"{report.unsupported_before}/{report.n_claims} claims unsupported before fix"}
