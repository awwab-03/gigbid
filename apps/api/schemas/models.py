"""Typed request/response models. The web client in apps/web/src/lib/api is generated from the
OpenAPI schema these produce (make api-client)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=6, max_length=200)


class RegisterIn(LoginIn):
    name: str = Field(min_length=1, max_length=120)
    account: Literal["ml_engineer", "fullstack_dev", "data_analyst"] = Field(description="Persona / marketplace account to connect")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class SavedSearch(BaseModel):
    query: str = Field("", max_length=200)
    category: str | None = None
    limit: int = Field(20, ge=1, le=50)


class Settings(BaseModel):
    autonomy: Literal["suggest", "auto_skip"] = "suggest"
    weekly_connects_budget: int = Field(80, ge=0, le=1000)
    marketplace_mode: Literal["gigsim", "upwork_live"] = "gigsim"
    saved_searches: list[SavedSearch] = Field(default_factory=list)
    hourly_floor: float | None = Field(None, ge=1)
    hourly_target: float | None = Field(None, ge=1)
    min_fixed: float | None = Field(None, ge=1)
    timezone: str = "Asia/Karachi"


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    account: str
    settings: dict[str, Any]
    upwork_connected: bool = False


class JobRow(BaseModel):
    job_id: str
    title: str | None
    category: str | None
    status: str | None
    action: str | None
    fit: float | None
    risk: float | None
    scam: bool = False
    price: float | None
    bid_type: str | None
    connects: int | None
    flags: list[str] = Field(default_factory=list)
    reason: str | None
    thread_id: str | None
    pipeline: str | None
    posted_at: str | None
    budget: dict | None = None


class JobList(BaseModel):
    jobs: list[JobRow]
    marketplace_available: bool = True
    marketplace_message: str | None = None


class JobDetail(BaseModel):
    job: dict[str, Any]
    row: JobRow | None
    analysis: dict[str, Any] = Field(default_factory=dict, description="job_spec, risk_report, fit_report, decision, price, evidence")
    run: dict[str, Any] | None = None


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(None, max_length=8000)
    edited_amount: float | None = Field(None, gt=0)
    reason: str | None = Field(None, max_length=500)


class Pending(BaseModel):
    thread_id: str
    kind: str
    ref: str | None
    payload: dict[str, Any]
    updated_at: str | None = None


class PendingList(BaseModel):
    pending: list[Pending]


class Accepted(BaseModel):
    queued: bool
    job_id: str
    mode: str
    duplicate: bool = False


class RegenerateIn(BaseModel):
    paragraph_index: int = Field(ge=0, le=20)
    instruction: str | None = Field(None, max_length=300)


class RegenerateOut(BaseModel):
    paragraph_index: int
    text: str
    unsupported_removed: int


class RunOut(BaseModel):
    thread_id: str
    kind: str | None
    ref: str | None
    status: str | None
    trace_id: str | None
    trace_url: str | None
    tokens: int | None
    cost_usd: float | None
    latency_s: float | None
    node_latency: dict[str, float] | None
    error: str | None
    events: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)


class CheckpointOut(BaseModel):
    checkpoint_id: str
    next: list[str]
    step: int | None
    created_at: str | None
    status: str | None


class ReplayIn(BaseModel):
    checkpoint_id: str


class PipelineCard(BaseModel):
    job_id: str
    title: str | None
    stage: str
    proposal_id: str | None
    price: float | None
    connects: int | None
    thread_id: str | None


class PipelineOut(BaseModel):
    stages: list[str]
    cards: list[PipelineCard]


class ThreadOut(BaseModel):
    thread_id: str
    job_id: str
    stage: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    pending_reply: Pending | None = None


class ThreadsOut(BaseModel):
    threads: list[ThreadOut]
    marketplace_available: bool = True


class Analytics(BaseModel):
    by_category: list[dict[str, Any]]
    connects_spent: int
    outcomes: dict[str, int]
    cost_per_proposal_usd: float | None
    p95_latency_proposal_s: float | None
    p95_latency_job_s: float | None
    cost_per_job_usd: float | None
    top_rejection_reasons: list[dict[str, Any]]
    runs: int


class MemoryOut(BaseModel):
    style: list[dict[str, Any]]
    outcome: list[dict[str, Any]]
    observations: dict[str, int]


class HealthOut(BaseModel):
    status: str
    marketplace: dict[str, Any]
    mode: str
    worker_mode: str


TokenOut.model_rebuild()
