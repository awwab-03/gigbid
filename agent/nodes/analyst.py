"""Job Analyst: extract a structured JobSpec (small model; heuristic fallback)."""

from __future__ import annotations

import asyncio
import json

from agent.guardrails import detect_injection, quarantine, wrap_untrusted
from agent.handoffs import JobSpec
from agent.llm import call_json
from agent.nodes._runtime import TIMEOUT_SCALE, node
from rag.variants.base import extract_requirements

ANALYST_LLM_TIMEOUT_S = 40  # cheap node: fall back to the heuristic spec instead of failing the job


def heuristic_spec(job: dict) -> JobSpec:
    b = job.get("budget", {})
    return JobSpec(job_id=job["job_id"], title=job.get("title", ""), category=job.get("category", "other"),
                   deliverables=job.get("deliverables", []), required_skills=job.get("required_skills", []),
                   requirements=extract_requirements(job), budget_type=b.get("type", "fixed"), budget_min=b.get("min"),
                   budget_max=b.get("max"), timeline_days=job.get("duration_days"),
                   screening_questions=job.get("screening_questions", []), source="heuristic")


@node("analyst")
async def analyst(state: dict) -> dict:
    job = state["job"]
    text = quarantine(job.get("description", ""), detect_injection(job.get("description", "")))
    meta = {k: job.get(k) for k in ("job_id", "title", "category", "required_skills", "budget", "duration_days", "screening_questions")}
    base = heuristic_spec(job)
    try:
        spec = await asyncio.wait_for(
            call_json("analyst", "analyst", {"meta": json.dumps(meta), "job_post": wrap_untrusted(f"{job.get('title', '')}\n{text}")}, JobSpec),
            timeout=ANALYST_LLM_TIMEOUT_S * TIMEOUT_SCALE)
        # trusted marketplace fields win over the model's reading of the text
        spec.job_id, spec.category = job["job_id"], job.get("category", spec.category)
        spec.budget_type, spec.budget_min, spec.budget_max = base.budget_type, base.budget_min, base.budget_max
        spec.screening_questions = base.screening_questions or spec.screening_questions
        if not spec.requirements:
            spec.requirements = base.requirements
        spec.source = "llm"
    except Exception:  # noqa: BLE001 - fallback keeps the graph moving on a cheap node
        spec = base
    return {"job_spec": spec.model_dump(), "_summary": f"{len(spec.requirements)} requirements ({spec.source})"}
