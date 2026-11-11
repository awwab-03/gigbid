"""Typed graph state with reducers (C2).

Three things are kept apart:
  * STATE (this file): what this job / conversation needs right now. Parallel branches write to
    disjoint keys (job_spec | risk_report | fit_report); list fields use additive reducers.
  * EXECUTION TRACE: every tool call and node event goes to `trace` (append-only) AND to
    LangSmith; it is for audit and debugging and is never read back into prompts as memory.
  * LONG-TERM MEMORY: agent/memory/store.py, written only through promotion rules.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dict(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class BidState(TypedDict, total=False):
    # identity
    thread_id: str
    user_id: str
    account: str
    trace_id: str
    autonomy: str
    # freelancer profile (rate floor, target, name, headline). It MUST be declared here: LangGraph drops undeclared
    # input keys, which once left decide/pricing/writer with an empty profile (floor 0, default $20 floor).
    profile: dict[str, Any]
    skip_dedup: bool
    # job
    job: dict[str, Any]
    client: dict[str, Any]
    # parallel analyses (each written by exactly one branch)
    job_spec: dict[str, Any]
    risk_report: dict[str, Any]
    fit_report: dict[str, Any]
    evidence: dict[str, Any]            # requirement -> evidence refs (requirement-to-evidence matrix)
    # decision and pricing
    decision: dict[str, Any]
    price: dict[str, Any]
    # drafting loop
    draft: dict[str, Any]
    verification: dict[str, Any]
    critiques: Annotated[list[dict[str, Any]], operator.add]
    revisions: int
    compliance_verdict: dict[str, Any]
    # human in the loop
    approval_request: dict[str, Any]
    approvals: Annotated[list[dict[str, Any]], operator.add]
    # outcome
    submission: dict[str, Any]
    outcome: dict[str, Any]
    status: str                         # analysing | skipped | watching | awaiting_approval | submitted |
                                        # rejected | blocked | needs_attention | queued_degraded | dead_letter
    status_reason: str
    # bookkeeping (reducers because parallel branches append)
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    node_latency: Annotated[dict[str, float], merge_dict]


class ConversationState(TypedDict, total=False):
    thread_id: str
    user_id: str
    account: str
    trace_id: str
    marketplace_thread_id: str
    profile: dict[str, Any]
    job: dict[str, Any]
    proposal: dict[str, Any]
    messages: list[dict[str, Any]]
    last_client_message: dict[str, Any]
    intent: dict[str, Any]
    slots: list[dict[str, Any]]
    reply: dict[str, Any]
    compliance_verdict: dict[str, Any]
    approvals: Annotated[list[dict[str, Any]], operator.add]
    sent: dict[str, Any]
    status: str
    status_reason: str
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    node_latency: Annotated[dict[str, float], merge_dict]
