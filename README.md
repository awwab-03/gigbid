# GigBid

**A multi-agent copilot for freelancers that finds jobs, decides whether to bid, prices them, and drafts
proposals grounded in the freelancer's own portfolio. Nothing reaches a client without human approval.**

**Live:** https://40-233-123-21.sslip.io (reviewer login in the private Classroom comment; preloaded persona: ML engineer)

| | |
|---|---|
| Bid/skip F1 on 150 dev jobs (real open model) | **0.95** measured, 0.98 at the dev-tuned threshold (`evals/results/decision_eval_open_v8_fixed_limit50.json`) |
| Scam detection precision / recall | **1.0 / 1.0** (same file) |
| Evidence Recall@5, shipped retriever (V8) vs naive (V0) | **0.798 vs 0.637** on 450 jobs (`evals/results/rag_variants.json`) |
| Cost | 11 Nov runs on Cerebras: **$5.27 in total**, paid by a $5 promotional credit (Cerebras billing page); runs from 12 Nov on Gemma 4 via Google AI Studio's free tier: $0. p95 12.8 s per job analysed |

## What it does

1. **Scouts** a marketplace (GigSim, our simulator; an Upwork adapter exists for live mode) on a schedule.
2. Runs three analysts **in parallel**: Job Analyst (structured JobSpec), Risk Assessor (scams, prompt injection),
   Fit Matcher (requirement-to-evidence matrix from the Portfolio MCP server).
3. **Decides** bid / watch / skip with a reason, then prices the bid against the client's band and history.
4. **Writes** a proposal that cites evidence `[E1]`, **verifies every claim** against the portfolio, lets a
   **Critic** request up to two revisions, and runs a **Compliance Guard** on platform rules.
5. **Stops for approval.** The approval card shows the draft, the evidence behind each claim, the risk report and
   the Connects cost. Submission is idempotent and survives a crash (Postgres checkpoints).
6. Handles **client replies** in a second graph (intent, calendar slots, drafted reply, approval again).

## Architecture

```mermaid
flowchart LR
  UI[React + TS UI] <-->|typed OpenAPI client, SSE| API[FastAPI]
  API --> Q[jobs: Arq on Redis, or in-process]
  Q --> BG[LangGraph bid graph] & CG[LangGraph conversation graph]
  BG & CG -->|per-agent tool allowlists| P[Portfolio MCP] & M[Marketplace MCP] & W[Workspace MCP]
  M -->|port + adapters| GS[GigSim] & UP[Upwork MCP, live mode]
  P --> V[(pgvector + BM25 + cross-encoder)]
  BG & CG --> PG[(Postgres: checkpoints, store, app tables)]
```

Bid graph, rendered from code ([`docs/images/bid_graph.mmd`](docs/images/bid_graph.mmd)):
`intake -> [analyst | risk_assessor | fit_matcher] -> decide -> pricing -> writer -> verifier -> critic (max 2 revisions) -> compliance -> approval (interrupt) -> submit (idempotent)`.
Full design and why each agent exists: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Tools: [`docs/TOOLS.md`](docs/TOOLS.md).
Decisions: [`docs/adr/`](docs/adr).

## Results

### Retrieval (B4/B5): 450 dev jobs, 3 personas

| Variant | Recall@5 | MRR | nDCG@10 |
|---|---|---|---|
| V0 naive dense | 0.637 | 0.767 | 0.713 |
| V1 requirement decomposition | 0.716 | 0.781 | 0.759 |
| V2 hybrid BM25 + dense | 0.748 | 0.812 | 0.787 |
| V3 hybrid + cross-encoder rerank | 0.786 | 0.850 | 0.816 |
| V4 outcome-weighted | 0.750 | 0.805 | 0.780 |
| V5 multi-vector | 0.646 | 0.789 | 0.723 |
| **V8 corrective RAG (ships)** | **0.798** | **0.873** | **0.828** |

Source: `evals/results/rag_variants.json` (per job: `evals/results/rag_per_job.csv`). Why V8 ships, and why the
1 GB live VM runs V2: [ADR 0004](docs/adr/0004-shipped-rag-variant.md). Claim-support threshold calibrated with
Youden's J: `evals/results/support_threshold.json`.

### Decisions (B4): real open model (Cerebras), V8, 150 dev jobs

| Persona | Bid/skip F1 (threshold 0.60, measured) | F1 at shipped threshold 0.70 | Price in fair band |
|---|---|---|---|
| ml_engineer | 0.931 | 0.982 | 1.00 |
| fullstack_dev | 0.915 | 1.000 | 1.00 |
| data_analyst | 1.000 | 0.967 | 1.00 |
| **All** | **0.950** | **0.982** | **1.00** |

Scam P/R 1.0/1.0, injected-post flag recall 1.0, p50/p95 8.3 s / 12.8 s per job, ~2,700 tokens per job, 0 errors
(`evals/results/decision_eval_open_v8_fixed_limit50.json`). The 0.70 column is computed exactly from the same rows
(the decision is deterministic given the fit score) and was **chosen on this dev set**, so it is in-sample
(`evals/results/decision_threshold_sweep.json`). Same jobs with naive retrieval (V0): F1 0.808, recall 0.69
(`decision_eval_open_v0_fixed_limit50.json`).

**A bug the evaluation found.** The first run scored F1 0.900 with only 73% of bids inside the fair price band. Failure
analysis traced both to one line: `profile` was not declared in the LangGraph state, so LangGraph silently dropped it
and every node saw an empty profile (rate floor 0, default $20 floor). Fixed in `f9badfa` with a regression test; the
pre-fix files are kept (`decision_eval_open_v8_limit50.json`).

### Proposals (B5): Gemma 4, V8, first 10 gold-bid dev jobs per persona

| Drafted / jobs | Unsupported claims per proposal (before → after verification) | LLM judge (1-5) | Simulated reply rate | Tokens per proposal | p95 |
|---|---|---|---|---|---|
| 20 / 30 | 1.35 → 0.10 | 3.9 (10 judged) | 0.30 | 8,369 | 878 s |

9 runs ended in `dead_letter` on Google free-tier 429/500s; the writer often fell back from 31B to 26B (counted in
`llm_fallbacks`). Source: `evals/results/proposal_eval_gemma_v8_gemma.json`. Report section 4 has the caveats.

### Tool granularity (R&D A): 40 tasks, first call scored

| Surface (tools) | Gemma 31B tool / args | Gemma 26B tool / args | Tokens per task |
|---|---|---|---|
| fine (42) | 0.950 / 0.900 | 0.925 / 0.900 | 1,917 |
| coarse (3) | 0.925 / 0.700 | 0.950 / 0.600 | 486 |
| ours (22) | 0.975 / 0.975 | 0.925 / 0.925 | 3,421 |
| **ours, rewritten descriptions (ships)** | **0.975 / 0.975** | **0.975 / 0.975** | 3,614 |

Source: `evals/results/tool_granularity.json`. Coarse tools did not help selection and cost 20-30 points of argument accuracy.

## Run it

| What | Command |
|---|---|
| Everything in Docker | `docker compose -f infra/docker-compose.yml --env-file .env up --build`, open http://localhost:8080 |
| Without Docker | `make dev` (GigSim, API with in-process MCP servers and worker, Vite) |
| Tests | `make test` (repo rules, unit, MCP contract snapshots, integration incl. crash-and-resume), `make e2e` (Playwright) |
| Evals | `make eval` writes `evals/results/*.json`; `bash scripts/run_experiments.sh` reruns the real-model experiments |

Copy `.env.example` to `.env`. The `open` model profile needs any OpenAI-compatible open-model key (we used Cerebras'
promotional credit, later Gemma 4 on Google AI Studio's free tier); `MODEL_PROFILE=fake` runs everything offline. Deployment: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Repository map

`gigsim/` marketplace simulator and seed data · `mcp_servers/` Portfolio, Marketplace, Workspace MCP servers ·
`rag/` ingestion, variants V0-V5 and V8, claim verification · `agent/` graphs, nodes, prompts, memory, guardrails ·
`apps/api` FastAPI · `apps/web` React UI · `worker/` Arq worker · `evals/` datasets, runners, committed results ·
`infra/` Docker and the Oracle deploy · `docs/` architecture, data card, runbook, ADRs, AI-usage disclosure.

## Data and integrity

Personas, portfolios, clients and jobs are **synthetic** and generated reproducibly (seed 7); see
[`docs/DATA_CARD.md`](docs/DATA_CARD.md). Live mode never scrapes and never submits without approval.
AI assistance is disclosed in [`docs/AI_USAGE.md`](docs/AI_USAGE.md). Every number above comes from a committed file
in `evals/results/`.
