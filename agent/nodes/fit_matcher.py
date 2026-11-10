"""Fit Matcher: map every requirement to portfolio evidence and score fit with reasons.

Runs in parallel with the Analyst, so it extracts requirements itself (deterministically) and calls
the Portfolio MCP server's match_requirements, which uses the retrieval variant chosen by the eval.
"""

from __future__ import annotations

from agent.handoffs import EvidenceRef, FitReport, RequirementMatch
from agent.nodes._runtime import node, toolbox
from rag.variants.base import extract_requirements


@node("fit_matcher")
async def fit_matcher(state: dict) -> dict:
    job = state["job"]
    reqs = extract_requirements(job)
    res = await toolbox(state, "fit_matcher").call("portfolio.match_requirements", {
        "requirements": reqs, "job_title": job.get("title", ""), "category": job.get("category"), "per_requirement": 3})
    matrix = [RequirementMatch(requirement=m["requirement"], supported=m["supported"],
                               evidence=[EvidenceRef(evidence_id=e["evidence_id"], project=e["project"], project_title=e["project_title"],
                                                     type=e["type"], snippet=e["snippet"][:400], score=e["score"]) for e in m["evidence"]])
              for m in res["matrix"]]
    # deliverables are weighted half: missing a deliverable phrase is weaker evidence of poor fit than missing a skill
    deliv = set(job.get("deliverables", []))
    w = [0.5 if m.requirement in deliv else 1.0 for m in matrix]
    score = sum(wi for wi, m in zip(w, matrix, strict=False) if m.supported) / max(1e-9, sum(w))
    report = FitReport(score=round(score, 3), matrix=matrix, matched=[m.requirement for m in matrix if m.supported],
                       missing=[m.requirement for m in matrix if not m.supported], top_projects=res["top_projects"],
                       reasons=[f"{sum(m.supported for m in matrix)}/{len(matrix)} requirements have portfolio evidence"]
                       + [f"no evidence for: {m.requirement}" for m in matrix if not m.supported][:4],
                       variant=res["variant"])
    return {"fit_report": report.model_dump(), "evidence": {m.requirement: [e.model_dump() for e in m.evidence] for m in matrix},
            "_summary": f"fit {report.score} via {report.variant}"}
