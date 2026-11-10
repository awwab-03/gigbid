# ADR 0002: Coarse portfolio tools for agents, fine tools kept for hosts

**Decision.** Agents use two coarse portfolio tools (`match_requirements`, `verify_claims`); fine-grained
`search_evidence`, `get_case_study`, resources and prompts stay for Claude Desktop / Cursor users.
**Why.** Our graph already knows which step it is in, so it needs one call per step; coarse tools keep the
retrieval variant and the verification thresholds server-side and testable. The R&D question A study
(`evals/results/tool_granularity.json`) measures selection accuracy, argument accuracy and tokens per task
for fine, coarse and rewritten tool sets with a tool-calling model.
