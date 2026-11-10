"""Shared types and helpers for retrieval variants."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from rag.index.store import Hit, PortfolioIndex

RRF_K = 60


@dataclass
class RetrievalResult:
    variant: str
    ranked_projects: list[tuple[str, float]]
    hits: list[Hit]
    per_requirement: dict[str, list[Hit]] = field(default_factory=dict)
    unsupported_requirements: list[str] = field(default_factory=list)
    debug: dict = field(default_factory=dict)

    def evidence_for(self, requirement: str, n: int = 3) -> list[Hit]:
        return self.per_requirement.get(requirement, [])[:n]


def job_text(job: dict) -> str:
    return f"{job.get('title', '')}\n{job.get('description', '')}\nSkills: {', '.join(job.get('required_skills', []))}"


def extract_requirements(job: dict) -> list[str]:
    """Cheap deterministic requirement extraction (used by retrieval evals and as the Analyst's
    fallback). Bullet lines are the client's requirement list; deliverables are added."""
    reqs: list[str] = []
    for line in (job.get("description") or "").splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            r = re.sub(r"^[-*•]\s+", "", line)
            r = re.sub(r"\b(strong experience with|must know|hands-on|experience with|you have built|before|\(required\))\b", "", r, flags=re.I)
            r = re.sub(r"\s+", " ", r).strip(" .")
            if 2 <= len(r) <= 200:
                reqs.append(r)
    for s in job.get("required_skills", []):
        if not any(s.lower() in r.lower() for r in reqs):
            reqs.append(s)
    for d in job.get("deliverables", [])[:2]:
        reqs.append(d)
    seen, out = set(), []
    for r in reqs:
        if r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out[:8]


def rrf(lists: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    s: dict[str, float] = defaultdict(float)
    for lst in lists:
        for rank, item in enumerate(lst):
            s[item] += 1.0 / (k + rank + 1)
    return s


def project_order(hits: list[Hit]) -> list[str]:
    seen, out = set(), []
    for h in hits:
        for p in h.projects:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def merge_requirements(per_req: dict[str, list[Hit]], index: PortfolioIndex, k: int) -> tuple[list[tuple[str, float]], list[Hit]]:
    """Project-level fusion across requirements: projects that prove more requirements rank higher."""
    scores = rrf([project_order(h) for h in per_req.values()])
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best: dict[str, Hit] = {}
    for hits in per_req.values():
        for h in hits:
            if h.chunk_id not in best or h.score > best[h.chunk_id].score:
                best[h.chunk_id] = h
    order = {p: i for i, (p, _) in enumerate(ranked)}
    flat = sorted(best.values(), key=lambda h: min([order.get(p, 999) for p in h.projects] or [999]))
    return ranked, flat[: k * 3]
