"""Proposal Writer: cover letter + screening answers citing evidence as [E#] (large model)."""

from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, Field

from agent.handoffs import ProposalDraft, ScreeningAnswer
from agent.llm import call_json
from agent.memory.store import outcome_insights, style_rules
from agent.nodes._runtime import node


class WriterOut(BaseModel):
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    cited_evidence: list[str] = Field(default_factory=list)


def evidence_table(state: dict) -> tuple[str, dict[str, str]]:
    """Number every evidence chunk E1..En; returns the prompt table and E# -> evidence_id map."""
    lines, emap, seen = [], {}, {}
    for req, evs in (state.get("evidence") or {}).items():
        for e in evs[:2]:
            eid = e["evidence_id"]
            if eid not in seen:
                seen[eid] = f"E{len(seen) + 1}"
                emap[seen[eid]] = eid
                lines.append(f"[{seen[eid]}] ({e['type']}, project: {e.get('project_title') or '-'}) {e['snippet'][:350]}")
            lines.append(f"    supports requirement: {req} -> {seen[eid]}")
    return "\n".join(lines) or "(no evidence found)", emap


def strip_citations(text: str) -> str:
    return re.sub(r"\s*\[E\d+(?:\s*,\s*E\d+)*\]", "", text).strip()


@node("writer")
async def writer(state: dict) -> dict:
    spec = state.get("job_spec") or {}
    table, emap = evidence_table(state)
    feedback = ""
    if state.get("critiques"):
        last = state["critiques"][-1]
        feedback = last.get("revise_instructions", "") + " Issues: " + "; ".join(last.get("issues", []))
    prof = state.get("profile", {})
    user = state.get("user_id", "local")
    # X2 A/B extension: WRITER_STRATEGY selects the proposal strategy (A = "writer", evidence-led; B = "writer_plan", plan-first)
    strategy = os.getenv("WRITER_STRATEGY", "writer")
    strategy = strategy if strategy in ("writer", "writer_plan") else "writer"
    out = await call_json("writer", strategy, {
        "job_spec": json.dumps({k: spec.get(k) for k in ("title", "deliverables", "requirements", "hidden_needs", "screening_questions",
                                                        "timeline_days")}),
        "price": json.dumps({k: state.get("price", {}).get(k) for k in ("bid_type", "amount")}),
        "evidence": table,
        "missing": json.dumps(state.get("fit_report", {}).get("missing", [])),
        "freelancer": json.dumps({k: prof.get(k) for k in ("name", "headline", "years")}),
        "style_rules": json.dumps(style_rules(user)),
        "outcome_insights": json.dumps(outcome_insights(user, state["job"].get("category", "other"))),
        "feedback": feedback,
    }, WriterOut)
    cited = sorted({emap[c] for c in re.findall(r"E\d+", out.cover_letter + " ".join(a.answer for a in out.screening_answers)) if c in emap})
    draft = ProposalDraft(job_id=state["job"]["job_id"], cover_letter=out.cover_letter, screening_answers=out.screening_answers,
                          cited_evidence=cited, revision=int(state.get("revisions") or 0))
    return {"draft": {**draft.model_dump(), "evidence_map": emap}, "status": "drafting",
            "_summary": f"draft r{draft.revision}, {len(out.cover_letter.split())} words, {len(cited)} citations"}
