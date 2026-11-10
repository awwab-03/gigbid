# AI usage disclosure

**Tool:** Claude Code (Anthropic, Claude Opus 5.5) in the Claude desktop app, used as a pair programmer.
I remain accountable for every line and can explain and change any part of the system.

## What it was used for

| Area | Files | How |
|---|---|---|
| Simulator and synthetic data | `gigsim/`, `gigsim/seed/` | Generated the first drafts of the generator, client model and API from my spec; I chose the persona projects, the trap types and the gold-label rules |
| MCP servers | `mcp_servers/` | Drafted tool schemas, idempotency and audit log; I reviewed annotations and limits |
| RAG | `rag/` | Drafted variants and verification; thresholds come from my calibration run |
| Agents and graphs | `agent/` | Drafted nodes, prompts and the graph wiring from the assignment's architecture |
| API, worker, web | `apps/`, `worker/` | Drafted routes and screens; I tested every flow in the browser |
| Evals, CI, docs | `evals/`, `.github/`, `docs/` | Drafted runners and docs; every number is produced by the committed scripts |

## Things it got wrong that were caught

(Fill in at least one in your own words. Examples from the commit history that were found by running the system:)

* The first requirement extractor left "(required)" inside every requirement, because a `\b` word boundary never
  matches before "(". Retrieval silently degraded; caught by the Fit Matcher returning fit 0.0 on an obvious match.
* The first style-memory rule promoted every word of a deleted sentence ("Never use the word 'data'"); caught in a
  unit check and fixed by only counting removals inside sentences that survived the edit.
* The marketplace server's own rate limiter raised an error the client did not recognise as rate limiting, so jobs
  dead-lettered instead of being queued; caught by the decision eval (47 of 60 jobs failed under load).
* `enqueue(fn, job_id, **kwargs)` collided with the task's own `job_id` argument and returned HTTP 500; caught while
  clicking through the UI.

**My own example:** _..._
