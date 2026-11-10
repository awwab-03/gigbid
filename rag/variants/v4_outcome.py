"""V4 outcome-aware ranking (Ranking group).

Boosts projects that were cited in past proposals that WON or got REPLIES for similar jobs
(same category or overlapping skills), with Laplace smoothing so a single lucky win does not
dominate. Base candidates come from V2 hybrid fusion (cheaper than V3; see the ablation).
Boost weights live in agent/config.yaml (rag.outcome_boost).
"""

from __future__ import annotations

from collections import defaultdict

from rag.index.models import CFG, embed
from rag.index.store import PortfolioIndex
from rag.variants.base import RetrievalResult, extract_requirements, merge_requirements
from rag.variants.v2_hybrid import hybrid

NAME = "v4_outcome"


def outcome_prior(index: PortfolioIndex, category: str | None, skills: set[str]) -> dict[str, float]:
    w = CFG["rag"]["outcome_boost"]
    num: dict[str, float] = defaultdict(float)
    den: dict[str, float] = defaultdict(float)
    for d in index.proposals:
        m = d.meta
        sim = (1.0 if category and m.get("job_category") == category else 0.0) + 0.5 * len(skills & set(m.get("skills", [])))
        if sim <= 0:
            continue
        for p in m.get("cited_projects", []):
            num[p] += sim * w.get(m["outcome"], 0.0)
            den[p] += sim
    return {p: num[p] / (den[p] + 2.0) for p in den}


def retrieve(job: dict, index: PortfolioIndex, k: int = 10, requirements: list[str] | None = None) -> RetrievalResult:
    reqs = requirements or extract_requirements(job)
    qv = embed(reqs, query=True)
    per_req = {r: hybrid(index, r, qv[i]) for i, r in enumerate(reqs)}
    ranked, flat = merge_requirements(per_req, index, k)
    prior = outcome_prior(index, job.get("category"), set(job.get("required_skills", [])))
    scale = max((s for _, s in ranked), default=1.0)
    boosted = sorted(((p, s + scale * prior.get(p, 0.0)) for p, s in ranked), key=lambda x: -x[1])
    return RetrievalResult(NAME, boosted, flat, per_req, debug={"prior": prior})
