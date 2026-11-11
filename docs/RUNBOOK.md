# Runbook

## Run locally

| What | Command |
|---|---|
| Everything (Docker) | `docker compose -f infra/docker-compose.yml --env-file .env up --build` then open http://localhost:8080 |
| Single-process dev (no Docker) | `uvicorn gigsim.app:app --port 8081`, `python scripts/dev_api.py`, `npm --prefix apps/web run dev` |
| Tests | `make test` (unit, contract, integration) and `make e2e` (Playwright) |
| Evals | `make eval` (writes `evals/results/*.json`) |

`scripts/dev_api.py` runs the MCP servers in-process (`MCP_TRANSPORT=inproc`), the worker inline and
SQLite storage, so a laptop without Docker can run the whole product. Production always uses the
streamable-HTTP MCP servers, Postgres, Redis and the Arq worker.

## Deploy (free tier: Hugging Face Space + Neon)

The live URL is a free Hugging Face Space (Docker SDK, 2 vCPU / 16 GB) running one container
(`infra/deploy/hf/Dockerfile`): GigSim, the three MCP servers, API, Arq worker, Redis and Caddy under
supervisord. Postgres (checkpoints, store, app tables, pgvector) is a free Neon database so state
survives container restarts.

1. **Neon**: create a project, enable the `vector` extension (`CREATE EXTENSION vector;` in the SQL editor), copy the
   connection string (`postgresql://...?sslmode=require`).
2. **Hugging Face**: create a Space, SDK **Docker**, hardware **CPU basic (free)**. Name it `gigbid`.
3. **Space settings, Variables and secrets** (all as *secrets* except where noted):

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string |
   | `APP_SECRET_KEY`, `MCP_SHARED_SECRET`, `GIGSIM_SECRET`, `GIGSIM_ADMIN_TOKEN` | four different long random strings |
   | `TOKEN_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
   | `OPEN_LLM_API_KEY` | Cerebras API key (`OPEN_LLM_BASE_URL` defaults to Groq) |
   | `LANGSMITH_API_KEY` | LangSmith key; also set variable `LANGSMITH_TRACING=true` |
   | `REVIEWER_EMAIL`, `REVIEWER_PASSWORD` | the reviewer login you will paste in the private Classroom comment |
   | `WEB_ORIGIN` (variable) | `https://<user>-gigbid.hf.space` |
   | `UPWORK_OAUTH_REDIRECT_URI` (variable) | `https://<user>-gigbid.hf.space/api/auth/upwork/callback` |

4. **GitHub repo settings**: secret `HF_TOKEN` (a Hugging Face *write* token), variables `HF_SPACE=<user>/gigbid` and
   `LIVE_URL=https://<user>-gigbid.hf.space`. Every push to `main` then redeploys (`.github/workflows/deploy-hf.yml`),
   and `.github/workflows/keepalive.yml` pings `/api/health` every 6 hours so the free Space never sleeps
   (free Spaces sleep after 48 h without traffic, and the hidden test run happens after the deadline).
5. Open the Space URL, sign in as the reviewer, press **Scout now**.

Non-secret defaults for the container (Redis on localhost, MCP URLs on localhost, `VECTOR_BACKEND=pgvector`,
`MODEL_PROFILE=open`) are baked into `infra/deploy/hf/Dockerfile`.

## Schedules and rate limits (E1, A4)

| Job | Interval | Why |
|---|---|---|
| Pipeline sync + degraded retries | every 2 min | reads one cheap event feed per user |
| Scouting (GigSim) | 30 min | the stream releases a few jobs per simulated hour |
| Scouting (live Upwork) | **240 min** | a freelancer refreshes saved searches a few times a day; four reads per day per search is well inside normal human use and cannot look like scraping |
| Marketplace MCP limiter | 40/min (GigSim), **6/min (live)** | GigSim allows 60/min; live mode stays far below anything automated |

Live mode never scrapes, uses no browser automation or cookies, and every write is a draft the user
confirms on Upwork (`mcp_servers/marketplace/adapters/upwork_live.py`).

## Degraded mode (viva question 1)

Kill the marketplace: `curl -X POST localhost:8081/admin/chaos -H "X-Admin-Token: $GIGSIM_ADMIN_TOKEN" -d '{"outage": true}'`
(or stop the `mcp-marketplace` container).

* The UI shows the amber **Degraded mode** banner (`apps/web/src/components/DegradedBanner.tsx`, polling `/health`).
* Running graph nodes catch `ToolUnavailable` (`agent/mcp_client.py`) and the node wrapper
  (`agent/nodes/_runtime.py`) parks the thread as `queued_degraded` instead of failing it.
* The worker's `retry_degraded` (every 2 minutes) resumes those threads from their last checkpoint once
  `/health` is green again (`apps/api/runner.py:retry_degraded`).

## Crash and resume, exactly once (viva question 2, C6)

1. Analyse a job until it waits for approval. Approve it in the UI.
2. Kill the worker (`docker compose kill worker`) before it submits, then `docker compose up -d worker`.
3. The Arq job is retried; the graph resumes from the Postgres checkpoint at the `submit` node and
   calls `create_proposal_draft` / `submit_proposal` with the **same deterministic idempotency keys**
   (`agent/graphs/bid_graph.py:keys`). The marketplace server returns the stored result
   (`idempotent_replay: true`) and GigSim returns 409 for a second submission, so Connects are spent once.
   `tests/integration/test_bid_graph.py::test_approve_survives_restart_and_submits_once` proves this in CI.

## Platform policy change (change request)

Policy lives in `gigsim/policy.yaml` (simulator side) and `data/policy_pack/rules.yaml` +
`agent/config.yaml` (GigBid side). The Compliance Guard and Pricing Strategist read `GET /policy`
at run time, so a new Connects multiplier, fee, submission cap or length rule is absorbed without
code changes. See `docs/adr/0007-change-request.md` for what changed and the diff.

## Secrets

Only from environment variables. `.env` is git-ignored; `scripts/ci_checks.py` fails CI on anything
that looks like a key, on committed env files, and on any change under `gigsim/` that was not
deliberately re-frozen.
