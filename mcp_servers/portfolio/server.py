"""Portfolio MCP server (A1): read-only, evidence-first access to a freelancer's portfolio.

Tools      search_evidence(requirement, k, filters), get_case_study(id), list_skills(), get_proposal(id)
Resources  portfolio://case/{project_id}, portfolio://proposal/{proposal_id}, portfolio://repo/{project_id},
           portfolio://cv
Prompts    answer_screening_question, proposal_opening, evidence_matrix

Point it at any portfolio folder (layout in README.md) with PORTFOLIO_DIR, or let GigBid select
the persona from the caller's account. Works in Claude Desktop / Cursor over stdio:
    uvx --from git+https://github.com/awwab-03/gigbid gigbid-portfolio-mcp --stdio
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common import STATE_DIR, AuditLog, BearerAuthMiddleware, caller_var

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ItemType = Literal["case_study", "readme", "code", "review", "profile_item", "proposal", "cv"]


class EvidenceItem(BaseModel):
    evidence_id: str = Field(description="Chunk id; cite this in proposals")
    item_id: str = Field(description="Parent document id")
    project: str | None
    project_title: str | None
    type: str
    source: str
    date: str | None
    client_industry: str | None = None
    outcome: str | None = Field(None, description="For past proposals: won / replied / ignored")
    score: float
    snippet: str


class EvidenceList(BaseModel):
    requirement: str
    persona: str
    items: list[EvidenceItem]


class CaseStudy(BaseModel):
    project_id: str
    title: str | None
    text: str
    skills: list[str]
    date: str | None
    client_industry: str | None
    related_items: list[str]


class SkillMap(BaseModel):
    persona: str
    skills: dict[str, list[str]] = Field(description="skill -> project ids that name it")


class PastProposal(BaseModel):
    proposal_id: str
    text: str
    outcome: str
    job_category: str | None
    cited_projects: list[str]
    date: str | None


def _persona() -> str:
    if os.getenv("PORTFOLIO_DIR"):
        return Path(os.environ["PORTFOLIO_DIR"]).name
    return caller_var.get()[1]


def _index():
    from rag.index.store import PortfolioIndex, get_index

    if os.getenv("PORTFOLIO_DIR"):
        global _custom
        if _custom is None:
            _custom = PortfolioIndex(Path(os.environ["PORTFOLIO_DIR"]).name, Path(os.environ["PORTFOLIO_DIR"]))
        return _custom
    return get_index(_persona())


_custom = None
audit = AuditLog(STATE_DIR / "audit_portfolio.jsonl")
mcp = FastMCP("gigbid-portfolio",
              instructions="Read-only portfolio evidence. Cite evidence_id for every claim; if search returns nothing relevant, "
                           "do not claim the experience.",
              host=os.getenv("MCP_HOST", "0.0.0.0"), port=int(os.getenv("PORTFOLIO_MCP_PORT", "8091")), stateless_http=True)


@mcp.tool(annotations=READ, title="Search portfolio evidence")
def search_evidence(
    requirement: Annotated[str, Field(min_length=2, max_length=300, description="One requirement, e.g. 'Celery background jobs'")],
    k: Annotated[int, Field(ge=1, le=20)] = 5,
    types: Annotated[list[ItemType] | None, Field(description="Only these item types")] = None,
    project: Annotated[str | None, Field(max_length=32)] = None,
    since: Annotated[str | None, Field(description="YYYY-MM; only items dated on/after")] = None,
    outcome: Annotated[Literal["won", "replied", "ignored"] | None, Field(description="Past proposals with this outcome")] = None,
) -> EvidenceList:
    """Find portfolio items (case studies, repos, code, reviews, past proposals) that prove one requirement.
    Hybrid BM25 + dense retrieval with cross-encoder reranking; results carry type, source, date and outcome."""
    from rag.index.models import embed
    from rag.variants.v2_hybrid import hybrid
    from rag.variants.v3_rerank import rerank

    t0 = time.perf_counter()
    idx = _index()

    # past proposals are claims, not proof: only returned when asked for explicitly
    allowed = set(types) if types else ({"proposal"} if outcome else {"case_study", "readme", "code", "review", "profile_item", "cv"})

    def ok(m: dict) -> bool:
        return (m.get("type") in allowed and (not project or m.get("project") == project)
                and (not since or (m.get("date") or "") >= since) and (not outcome or m.get("outcome") == outcome))

    qv = embed([requirement], query=True)[0]
    cands = hybrid(idx, requirement, qv, n=30, pool=60, where=ok)
    hits = rerank(requirement, cands, n=k) if os.getenv("PORTFOLIO_RERANK", "1") == "1" else cands[:k]
    items = [EvidenceItem(evidence_id=h.chunk_id, item_id=h.meta.get("parent", h.chunk_id), project=h.meta.get("project"),
                          project_title=h.meta.get("project_title"), type=h.meta["type"], source=h.meta.get("source", ""),
                          date=h.meta.get("date"), client_industry=h.meta.get("client_industry"), outcome=h.meta.get("outcome"),
                          score=round(h.score, 4), snippet=h.text[:500]) for h in hits]
    audit.write(server="portfolio", tool="search_evidence", args={"requirement": requirement, "k": k}, result={"n": len(items)},
                ok=True, ms=(time.perf_counter() - t0) * 1000)
    return EvidenceList(requirement=requirement, persona=idx.persona, items=items)


@mcp.tool(annotations=READ, title="Get case study")
def get_case_study(project_id: Annotated[str, Field(min_length=1, max_length=32, description="e.g. ml-03")]) -> CaseStudy:
    """Full case study for one project plus the ids of its repo files, reviews and blurbs."""
    idx = _index()
    d = idx.doc_by_id.get(f"case:{project_id}")
    if not d:
        raise ValueError(f"no case study for project {project_id}")
    related = [x.doc_id for x in idx.docs if x.meta.get("project") == project_id and x.doc_id != d.doc_id]
    return CaseStudy(project_id=project_id, title=d.meta.get("project_title"), text=d.text, skills=d.meta.get("skills", []),
                     date=d.meta.get("date"), client_industry=d.meta.get("client_industry"), related_items=related)


@mcp.tool(annotations=READ, title="List skills")
def list_skills() -> SkillMap:
    """Skills named in the portfolio's case studies and which projects prove them."""
    idx = _index()
    return SkillMap(persona=idx.persona, skills=idx.skills())


@mcp.tool(annotations=READ, title="Get past proposal")
def get_proposal(proposal_id: Annotated[str, Field(min_length=1, max_length=64)]) -> PastProposal:
    """A past proposal with its outcome (won / replied / ignored)."""
    idx = _index()
    d = idx.doc_by_id.get(proposal_id)
    if not d or d.meta.get("type") != "proposal":
        raise ValueError(f"no proposal {proposal_id}")
    m = d.meta
    return PastProposal(proposal_id=proposal_id, text=d.text, outcome=m["outcome"], job_category=m.get("job_category"),
                        cited_projects=m.get("cited_projects", []), date=m.get("date"))


class RequirementEvidence(BaseModel):
    requirement: str
    supported: bool
    evidence: list[EvidenceItem]


class MatchResult(BaseModel):
    persona: str
    variant: str
    matrix: list[RequirementEvidence]
    top_projects: list[str]
    unsupported_requirements: list[str]


class ClaimResult(BaseModel):
    claim: str
    label: Literal["supported", "partly_supported", "unsupported", "not_a_claim"]
    score: float
    evidence_ids: list[str]
    evidence_snippet: str
    fixed: str | None = None


class VerifyResult(BaseModel):
    fixed_text: str
    claims: list[ClaimResult]
    n_claims: int
    unsupported_before: int
    unsupported_rate_before: float


def _item(h) -> EvidenceItem:
    return EvidenceItem(evidence_id=h.chunk_id, item_id=h.meta.get("parent", h.chunk_id), project=h.meta.get("project"),
                        project_title=h.meta.get("project_title"), type=h.meta["type"], source=h.meta.get("source", ""),
                        date=h.meta.get("date"), client_industry=h.meta.get("client_industry"), outcome=h.meta.get("outcome"),
                        score=round(h.score, 4), snippet=h.text[:500])


@mcp.tool(annotations=READ, title="Match job requirements to evidence")
def match_requirements(
    requirements: Annotated[list[Annotated[str, Field(max_length=300)]], Field(min_length=1, max_length=12)],
    job_title: Annotated[str, Field(max_length=200)] = "",
    category: Annotated[str | None, Field(max_length=32)] = None,
    per_requirement: Annotated[int, Field(ge=1, le=6)] = 3,
) -> MatchResult:
    """Requirement-to-evidence matrix using the deployed retrieval variant (rag.variant in config).
    A requirement is 'supported' only if relevant evidence was found; never claim unsupported ones."""
    from rag.index.models import CFG
    from rag.retriever import get_variant

    t0 = time.perf_counter()
    idx = _index()
    variant = get_variant()
    res = variant.retrieve({"title": job_title, "description": "\n".join(f"- {r}" for r in requirements), "category": category,
                            "required_skills": []}, idx, k=10, requirements=requirements)
    good = float(CFG["rag"].get("crag_good_logit", 0.0))
    matrix = []
    for r in requirements:
        hits = [h for h in res.per_requirement.get(r, []) if h.meta.get("type") != "proposal"][:per_requirement]
        if not hits and r not in res.unsupported_requirements:
            # V0 failure mode: past proposals ("Proposal for: Need a ... for ...") mirror job titles and crowd out
            # real evidence. Fall back to an evidence-only dense search for this requirement.
            from rag.index.models import embed as _embed

            hits = idx.struct.dense(_embed([r], query=True)[0], per_requirement, where=lambda m: m.get("type") != "proposal")
        if variant.NAME in ("v3_rerank", "v8_crag"):
            supported = bool(hits) and hits[0].score >= good and r not in res.unsupported_requirements
        else:  # fusion scores are not calibrated; verify the best hit with the cross-encoder
            from rag.index.models import rerank_scores

            supported = bool(hits) and max(rerank_scores(r, [h.text[:1500] for h in hits])) >= good
        matrix.append(RequirementEvidence(requirement=r, supported=supported, evidence=[_item(h) for h in hits]))
    audit.write(server="portfolio", tool="match_requirements", args={"n": len(requirements), "variant": variant.NAME},
                result={"supported": sum(m.supported for m in matrix)}, ok=True, ms=(time.perf_counter() - t0) * 1000)
    return MatchResult(persona=idx.persona, variant=variant.NAME, matrix=matrix, top_projects=[p for p, _ in res.ranked_projects[:5]],
                       unsupported_requirements=[m.requirement for m in matrix if not m.supported])


@mcp.tool(annotations=READ, title="Verify proposal claims")
def verify_claims(text: Annotated[str, Field(min_length=1, max_length=8000)],
                  evidence_ids: Annotated[list[str], Field(max_length=40)] = []) -> VerifyResult:  # noqa: B006
    """Split a draft into claims and ground each against the portfolio. Returns labels, the evidence
    behind each claim, and a fixed text with unsupported claims removed."""
    from rag.verify import verify_draft

    t0 = time.perf_counter()
    idx = _index()
    ev = [h for h in (_hit(idx, e) for e in evidence_ids) if h]
    r = verify_draft(text, idx, ev)
    audit.write(server="portfolio", tool="verify_claims", args={"chars": len(text)}, result={"unsupported": r["unsupported_before"]},
                ok=True, ms=(time.perf_counter() - t0) * 1000)
    return VerifyResult(fixed_text=r["fixed_text"], n_claims=r["n_claims"], unsupported_before=r["unsupported_before"],
                        unsupported_rate_before=r["unsupported_rate_before"],
                        claims=[ClaimResult(**{k: c[k] for k in ("claim", "label", "score", "evidence_ids", "evidence_snippet", "fixed")})
                                for c in r["claims"]])


def _hit(idx, chunk_id: str):
    from rag.index.store import Hit

    c = idx.struct.by_id.get(chunk_id) or idx.fixed.by_id.get(chunk_id)
    return Hit(chunk_id, 1.0, c.text, c.meta) if c else None


# ------------------------------------------------------------------ resources
@mcp.resource("portfolio://case/{project_id}", mime_type="text/markdown")
def case_resource(project_id: str) -> str:
    """Full case study markdown."""
    d = _index().doc_by_id.get(f"case:{project_id}")
    return d.text if d else f"No case study {project_id}"


@mcp.resource("portfolio://proposal/{proposal_id}", mime_type="application/json")
def proposal_resource(proposal_id: str) -> str:
    """Past proposal with outcome."""
    d = _index().doc_by_id.get(proposal_id)
    return json.dumps({"text": d.text, **d.meta}) if d else "{}"


@mcp.resource("portfolio://repo/{project_id}", mime_type="text/plain")
def repo_resource(project_id: str) -> str:
    """README and code files of the project's repository, concatenated."""
    docs = [d for d in _index().docs if d.meta.get("project") == project_id and d.meta.get("type") in ("readme", "code")]
    return "\n\n".join(f"=== {d.meta['source']} ===\n{d.text}" for d in docs) or f"No repo for {project_id}"


@mcp.resource("portfolio://cv", mime_type="text/plain")
def cv_resource() -> str:
    """The freelancer's CV as text."""
    d = next((x for x in _index().docs if x.meta.get("type") == "cv"), None)
    return d.text if d else "No CV"


# ------------------------------------------------------------------ prompts
@mcp.prompt(title="Answer a screening question from my portfolio")
def answer_screening_question(question: str, job_title: str = "") -> str:
    return (f"Answer this client screening question for the job '{job_title}':\n\n<question>{question}</question>\n\n"
            "First call search_evidence with the question's key requirement. Answer in 2-4 sentences using ONLY facts from "
            "the returned evidence, and cite each fact as [evidence_id]. If nothing relevant comes back, say honestly what "
            "you have not done and how you would approach it. Never invent clients, numbers or tools.")


@mcp.prompt(title="Write a specific proposal opening")
def proposal_opening(job_title: str, job_summary: str) -> str:
    return (f"Write the first two sentences of a proposal for '{job_title}'.\n<job>{job_summary}</job>\n"
            "Open with the client's problem in their words, then the single most relevant past project with its measured "
            "result, cited as [evidence_id] from search_evidence. No greetings like 'Dear Hiring Manager', no 'passionate'.")


@mcp.prompt(title="Build a requirement-to-evidence matrix")
def evidence_matrix(requirements: str) -> str:
    return ("For each requirement below (one per line), call search_evidence and list the best 1-2 evidence_ids with a "
            "one-line reason, or 'NO EVIDENCE' if none is relevant:\n" + requirements)


def http_app():
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    app = mcp.streamable_http_app()

    async def health(_):
        return JSONResponse({"server": "portfolio", "ok": True})

    app.router.routes.append(Route("/health", health))
    app.add_middleware(BearerAuthMiddleware, required=os.getenv("MCP_AUTH_REQUIRED", "1") == "1")
    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="GigBid Portfolio MCP server")
    ap.add_argument("--stdio", action="store_true", help="serve over stdio (Claude Desktop, Cursor, MCP Inspector)")
    a = ap.parse_args()
    if a.stdio:
        mcp.run("stdio")
    else:
        import uvicorn

        uvicorn.run(http_app(), host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    main()
