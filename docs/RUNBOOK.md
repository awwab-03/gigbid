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

## Deploy (free tier: Oracle Cloud Always Free VM)

The live URL is an Oracle Cloud **Always Free** `VM.Standard.E2.1.Micro` (1 OCPU, 1 GB RAM + 4 GB swap,
Ubuntu 24.04, Toronto) at `https://40-233-123-21.sslip.io` (sslip.io maps the hostname to the IP, so Caddy
gets a Let's Encrypt certificate without buying a domain). It never sleeps and costs nothing.

To fit 1 GB the deploy is **single-process** (`infra/deploy/oracle/`):

| Piece | How it runs on the VM |
|---|---|
| GigSim | `gigbid-gigsim.service` (uvicorn, SQLite state in `~/state`) |
| API + 3 MCP servers + worker | `gigbid-api.service`: MCP servers in-process (`MCP_TRANSPORT=inproc`), jobs as asyncio tasks (`WORKER_MODE=inline`), the worker's cron schedules in-process (`INLINE_CRON=1`, `apps/api/main.py:_inline_cron`) |
| Postgres 16 + pgvector | local apt package: checkpoints, store, app tables, vectors |
| Web | the built React app served by native Caddy, `/api/*` proxied to the API |

The MCP servers keep the same tool code, auth, idempotency and audit log; only the transport changes.
The Docker compose stack (`infra/docker-compose.yml`) is the multi-process version for machines with more RAM.

1. Create the VCN with the **VCN Wizard** (internet connectivity), add an ingress rule for TCP `80,443` from `0.0.0.0/0`.
2. Create the instance: Ubuntu 24.04, shape `VM.Standard.E2.1.Micro`, public subnet, public IPv4 on, your SSH key.
3. On the VM: 4 GB swap, open 80/443 in iptables (`netfilter-persistent save`), `git clone` the repo.
4. Copy `~/gigbid.env` (chmod 600; production overrides of `.env`, never committed) and the built web app
   (`VITE_API_URL=/api npx vite build`, from PowerShell or with `MSYS_NO_PATHCONV=1`: Git Bash rewrites `/api` to `C:/Program Files/Git/api` and every API call then hits the SPA fallback) to `~/web-dist`, then run `infra/deploy/oracle/setup.sh`.
5. `~/gigbid.env` also sets `RAG_VARIANT=v2_hybrid` and `GIGBID_TIMEOUT_SCALE=5` for this slow CPU (ADR 0004).
6. Update: `git pull && sudo systemctl restart gigbid-api gigbid-gigsim`. A restart re-queues interrupted runs,
   which resume from their checkpoint within 2 minutes.

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
