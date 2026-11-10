"""Structured hand-offs between agents (C3). Anything a later step decides on is one of these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = "other"
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list, description="Atomic requirements, one per line item")
    budget_type: Literal["fixed", "hourly"] = "fixed"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline_days: int | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated")
    source: Literal["llm", "heuristic"] = "llm"


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 = safe, 1 = certainly bad")
    flags: list[str] = Field(default_factory=list)
    scam_likely: bool = False
    injection_detected: bool = False
    injection_spans: list[str] = Field(default_factory=list)
    client_quality: float = Field(0.5, ge=0, le=1)
    explanation: str = ""


class EvidenceRef(BaseModel):
    evidence_id: str
    project: str | None = None
    project_title: str | None = None
    type: str
    snippet: str
    score: float = 0.0


class RequirementMatch(BaseModel):
    requirement: str
    supported: bool
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    top_projects: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    variant: str = ""


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0, le=1)
    auto: bool = False


class PriceQuote(BaseModel):
    bid_type: Literal["fixed", "hourly"]
    amount: float = Field(gt=0)
    floor: float
    market_p25: float | None = None
    market_p50: float | None = None
    market_p75: float | None = None
    client_budget_max: float | None = None
    connects_cost: int = 0
    connects_worth_it: bool = True
    expected_value_usd: float = 0.0
    rationale: str = ""


class ScreeningAnswer(BaseModel):
    question: str
    answer: str


class ProposalDraft(BaseModel):
    job_id: str
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    cited_evidence: list[str] = Field(default_factory=list)
    revision: int = 0
    status: str = "drafted"


class ClaimCheckOut(BaseModel):
    claim: str
    label: str
    score: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_snippet: str = ""
    fixed: str | None = None


class ClaimReport(BaseModel):
    claims: list[ClaimCheckOut] = Field(default_factory=list)
    n_claims: int = 0
    unsupported_before: int = 0
    unsupported_rate_before: float = 0.0
    fixed_text: str = ""


class Critique(BaseModel):
    score: int = Field(ge=0, le=10)
    passed: bool
    issues: list[str] = Field(default_factory=list)
    revise_instructions: str = ""


class ComplianceViolation(BaseModel):
    rule: str
    detail: str
    severity: Literal["fix", "block"]


class ComplianceVerdict(BaseModel):
    status: Literal["pass", "fixed", "block"]
    violations: list[ComplianceViolation] = Field(default_factory=list)
    fixed_text: str = ""
    policy_version: str = ""


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    edited_amount: float | None = None
    reason: str | None = None
    user_id: str = ""


class IntentClassification(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(0.5, ge=0, le=1)
    asked_price: float | None = None
    injection_detected: bool = False
    summary: str = ""


class ReplyDraft(BaseModel):
    thread_id: str
    body: str
    proposed_slots: list[str] = Field(default_factory=list)
    intent: str = "other"
