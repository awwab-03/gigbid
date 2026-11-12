# Viva preparation

The viva multiplies the written mark (0 to 1.0), so the goal is to explain every design choice and point at the
code. Each answer below is short on purpose: say it in your own words and open the file.

## The system in 60 seconds

GigSim (our simulator, `gigsim/`) plays the marketplace. Three MCP servers (`mcp_servers/`) are the only way agents
touch the outside world: Portfolio (read-only evidence), Marketplace (reads plus draft/submit/send, all behind
approval), Workspace (calendar and email drafts). Two LangGraph graphs (`agent/graphs/`) do the work: the bid graph
per job and the conversation graph per client thread. FastAPI + SSE serve a React UI; a worker runs jobs and schedules.

## Likely questions

**Why is this multi-agent and not one prompt?** Each agent has its own inputs, tools and failure mode: risk must be
checked before anything is drafted, evidence matching is retrieval not generation, decisions and pricing are
deterministic so they are testable (ADR 0005), the Critic and Compliance Guard are independent checks.
Measured in R&D C (`evals/results/agent_comparison.json`).

**Show the parallel branches.** `agent/graphs/bid_graph.py:54`: `fan_out` returns three `Send`s (analyst,
risk_assessor, fit_matcher); they join at `decide`.

**What can never happen without a human?** Submitting a proposal, sending a message, spending Connects.
`bid_graph.py:79` calls `interrupt(payload)`; the approval payload carries the draft, the evidence behind each
claim, the risk report and the Connects cost. The conversation graph does the same at `conversation_graph.py:49`.

**Crash between approve and submit?** Postgres checkpointer; the run resumes at `submit`. Idempotency keys are
derived from thread id + text + amount (`bid_graph.py:46`, `keys`), the marketplace server stores results by key
and GigSim returns 409 for a second submission, so Connects are spent once. Test:
`tests/integration/test_bid_graph.py::test_approve_survives_restart_and_submits_once`. On the single-process deploy,
startup re-queues runs left `running` (`apps/api/main.py`, lifespan).

**What if the marketplace is down?** Degraded mode: tools raise `ToolUnavailable`, the node wrapper parks the thread as
`queued_degraded` (`agent/nodes/_runtime.py`), the UI shows a banner, the scheduler retries from the checkpoint
every 2 minutes (`worker/tasks.py:retry_degraded`).

**Critic loop bound?** At most two revisions, then Compliance: `route_after_critic` in `agent/nodes/critic.py`,
wired at `bid_graph.py:148`.

**Which RAG variant ships and why?** V8 corrective RAG: best Recall@5 0.798, MRR 0.873, nDCG@10 0.828 on 450 jobs
(`evals/results/rag_variants.json`), and lower p95 than V3 because it only re-queries when the cross-encoder grade
is below the calibrated threshold. The 1 GB live VM runs V2 because the cross-encoder overloaded it (ADR 0004).
V5 multi-vector did not help.

**Does better retrieval matter downstream?** Decisions: bid/skip F1 0.950 with V8 vs 0.808 with V0, same model and
jobs, after the profile fix (`decision_eval_open_v8_fixed_limit50.json`, `decision_eval_open_v0_fixed_limit50.json`).
V0 is timid, not reckless: precision 0.97, recall 0.69. Pre-fix runs (0.900 vs 0.761) are kept for the failure story.

**The bug you found?** `profile` was not declared in `BidState` (`agent/state.py`), LangGraph silently dropped it,
every node saw an empty profile: floor 0 (bids on underpaid jobs), default $20 x 1.4 = $28/h. Found from the error mix
(all false positives) and price in band 0.73, not from F1. Regression test in `tests/integration/test_bid_graph.py`.

**Tool granularity (R&D A)?** `evals/results/tool_granularity.json`: 3 coarse tools did not help selection and lost
20-30 points of argument accuracy; our 22 tools with rewritten descriptions scored 0.975 on both Gemma models.

**How does claim verification work?** `rag/verify.py:154` `verify_draft`: split the draft into claims, retrieve
evidence per claim, score with the cross-encoder; supported / partly / unsupported by a threshold chosen with
Youden's J on labelled pairs (`evals/results/support_threshold.json`, -7.9 logit, AUC 0.787). Unsupported claims are
removed or rewritten before the Critic sees the draft.

**Why are bid/skip and price deterministic?** So they are testable and explainable: the model extracts the JobSpec,
rules decide (`agent/nodes/decision.py:11`, thresholds in `agent/config.yaml`) and price (`agent/nodes/pricing.py:13`).
Side effect we measured: swapping the model barely changes decision metrics.

**Prompt injection: what gets through?** Four layers (`agent/guardrails.py`): detector + quarantine, untrusted
delimiting, data-not-instructions prompts, output checks. Honest finding: the regex detector catches every planted
dev-set attack but none of 12 paraphrased ones (`evals/results/injection_eval_gemma_detector.json`); what has to hold is the
delimiting/prompting layer and the output checks. The end-to-end run timed out on the free tier, so that is a design
claim, not a measured rate (report section 9).

**Why not a prebuilt supervisor?** Same tools, same jobs: single ReAct agent and prebuilt supervisor failed on 50 and
51 of 51 jobs, and on 12 and 16 of 18 when rerun alone on 26B with retries; our graph failed on none (F1 0.963) because
each node has its own model, pacing and a 31B->26B fallback (`agent_comparison_graph.json`, `agent_comparison_matched.json`).
Their answer quality is not measured.

**MCP security?** Bearer service tokens signed with a shared secret, per-agent tool allowlists
(`agent/config.yaml: tool_allowlist`), write tools annotated and requiring idempotency keys, append-only hash-chained
audit log per server (`mcp_servers/common.py`), schema snapshot tests fail CI on unintended signature changes.

**Memory?** LangGraph store: style rules promoted only after consistent repeated edits, counting only sentences that
survived the edit; outcome insights from replies/hires (`agent/memory/promotion_rules.py`).

**Deployment?** Oracle Always Free micro VM, single process (in-process MCP transport, inline worker + scheduler),
Postgres + pgvector, Caddy HTTPS (ADR 0008). Problems we hit and fixed: sync MCP tools blocked the event loop (now
run in threads), portfolio embedding took 12 minutes on the VM (caches copied), the cross-encoder overloaded it (V2).

**Models and cost?** Open models only. First Cerebras (qwen-3.8-27b small, gpt-oss-120b large): not free, the 11 Nov runs
cost USD 5.27, paid by a USD 5 promotional credit, and gpt-oss allowed 5 requests/min. Then Gemma 4 on Google AI Studio's
free tier (`gemma` profile). Tokens are reported per job and per proposal, which shaped how experiments were run
(`scripts/run_experiments.sh`).

**What would you do next?** Replace the regex injection detector with a classifier trained on paraphrases; run the
A/B test with more jobs for power; human pairwise panel for proposal quality.

## Things to have open during the viva

The live URL (signed in), `agent/graphs/bid_graph.py`, `agent/guardrails.py`, `rag/variants/v8_crag.py`,
`evals/results/`, the README results tables, and LangSmith traces.
