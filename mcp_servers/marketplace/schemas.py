"""Pydantic input/output schemas for the Marketplace MCP server (declared output schemas)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Budget(BaseModel):
    type: Literal["fixed", "hourly"]
    min: float
    max: float
    currency: str = "USD"


class Job(BaseModel):
    job_id: str
    title: str
    description: str
    category: str
    required_skills: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    budget: Budget
    duration_days: int | None = None
    experience_level: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    client_id: str
    posted_at: str
    connects_cost: int
    proposals_count: int | None = None
    source: str = "gigsim"


class JobList(BaseModel):
    total: int
    jobs: list[Job]
    sim_time: str | None = None


class ClientHistory(BaseModel):
    client_id: str
    name: str | None = None
    industry: str | None = None
    country: str | None = None
    payment_verified: bool
    member_since: str | None = None
    jobs_posted: int = 0
    hires: int = 0
    total_spent_usd: float = 0
    avg_rating_given: float | None = None
    feedback_score: float | None = None
    disputes: int = 0
    hire_rate: float = 0
    recent_reviews: list[dict] = Field(default_factory=list)


class ConnectsBalance(BaseModel):
    balance: int
    spent: int = 0
    weekly_allowance: int | None = None
    policy_version: str | None = None


class PricingStats(BaseModel):
    category: str
    budget_type: str
    n: int
    p25: float
    p50: float
    p75: float


class Policy(BaseModel):
    version: str
    published: str | None = None
    summary: str | None = None
    connects_multiplier: float = 1.0
    connects_flat_fee: int = 0
    max_submissions_per_day: int | None = None
    min_cover_letter_words: int = 0
    max_cover_letter_words: int = 5000
    rules: list[str] = Field(default_factory=list)


class Message(BaseModel):
    message_id: str
    sender: Literal["client", "freelancer"]
    body: str
    at: str


class Thread(BaseModel):
    thread_id: str
    job_id: str
    client_id: str | None = None
    proposal_id: str | None = None
    stage: str
    messages: list[Message] = Field(default_factory=list)


class ThreadList(BaseModel):
    threads: list[Thread]


class ProposalStatus(BaseModel):
    proposal_id: str
    job_id: str
    status: str
    bid_amount: float | None = None
    bid_type: str | None = None
    connects_spent: int | None = 0
    thread_id: str | None = None
    submitted_at: str | None = None


class ProposalList(BaseModel):
    proposals: list[ProposalStatus]


class Event(BaseModel):
    id: int
    type: str
    ref: str
    payload: dict
    at: str


class EventList(BaseModel):
    events: list[Event]


class WriteResult(BaseModel):
    """Result of a write tool. With dry_run=True nothing is written and `preview` shows exactly
    what would be sent and what it costs."""

    ok: bool
    dry_run: bool
    preview: dict | None = None
    proposal_id: str | None = None
    message_id: str | None = None
    status: str | None = None
    connects_cost: int | None = None
    connects_spent: int | None = None
    balance_after: int | None = None
    idempotent_replay: bool = False
    marketplace: str = "gigsim"
    note: str | None = None
