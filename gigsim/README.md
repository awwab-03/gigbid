# GigSim: marketplace simulator

GigSim is a synthetic, repeatable stand-in for a freelance marketplace. All grading-style runs
(dev evals, smoke evals in CI, the demo) go through it. It is built for this project because the
course starter kit (v0.1) shipped without a simulator. It is treated as a **frozen component**:
`gigsim/CHECKSUMS.sha256` is verified in CI, so GigBid changes can never quietly tune the simulator.

## Data
`python -m gigsim.seed.generate --seed 7` regenerates everything (see `docs/DATA_CARD.md`):

| File | Contents |
|---|---|
| `data/jobs.json` | 600 dev jobs (200 per persona) + 240 live-stream jobs released over 21 simulated days |
| `data/clients.json` | 420 clients: public history + hidden preferences (`_hidden`) |
| `data/historical_jobs.json` | 1,500 historical jobs with winning bids (Kaggle titles/budgets when `data/raw/*.csv` exists) |
| `data/pricing_stats.json` | p25/p50/p75 winning bid per category and budget type |
| `data/accounts.json` | the three persona accounts and their Connects |

Fields starting with `_` (hidden preferences, planted scam/injection metadata, requirements) are
never returned by the API.

## API
All routes except `/health` and `/policy` need `Authorization: Bearer <freelancer_id>.<hmac>`.
Writes need an `Idempotency-Key` header (at least 8 chars). Replaying a key returns the stored
response with `idempotent_replay: true`. Reusing a key with a different body returns 409.

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | status, simulated time, active policy |
| GET | `/policy` | active platform policy (connects multiplier, limits, rules) |
| POST | `/auth/token` | `{freelancer_id, admin_token}` -> bearer token |
| GET | `/jobs` | `q, category, skills, budget_type, min_budget, posted_after, limit<=50, offset` |
| GET | `/jobs/{id}` | public job view |
| GET | `/clients/{id}` | client history: spend, hires, ratings, disputes, recent reviews |
| GET | `/stats/pricing` | market percentiles for a category |
| GET | `/me/connects` | balance, spent, weekly allowance |
| POST | `/proposals/drafts` | create draft (`dry_run: true` returns the preview and Connects cost) |
| POST | `/proposals/{id}/submit` | spends Connects; `?dry_run=true` previews |
| GET | `/proposals`, `/proposals/{id}` | status: draft, submitted, viewed, replied, interview, hired, lost |
| GET | `/threads`, `/threads/{id}/messages` | client conversations |
| POST | `/threads/{id}/messages` | send a reply (`dry_run` supported) |
| GET | `/events?since_id=` | marketplace events for the pipeline board |

Admin routes (header `X-Admin-Token`): `/admin/advance?minutes=`, `/admin/chaos` (`error_rate`,
`outage`), `/admin/policy?version=`, `/admin/connects`, `/admin/proposals`, `/admin/reset`.

## Behaviour
- **Rate limit:** `GIGSIM_RATE_LIMIT` requests per minute per token (default 60), returning 429 with `Retry-After`.
- **Transient errors:** `GIGSIM_ERROR_RATE` (default 0.03) random 503s on GETs.
- **Outage:** `/admin/chaos {"outage": true}` makes every non-admin route return 503 (viva question 1).
- **Clock:** the simulated time is `2026-10-27 09:00 UTC + real elapsed x GIGSIM_TIME_SCALE + admin offset`.
- **Clients:** `gigsim/client_model.py` scores each proposal against the client's hidden preferences: must-have
  coverage (only credited for skills the freelancer really has), fabricated skills, specificity,
  personalisation, generic openings, length, price vs ceiling, off-platform contact and injected canaries.
  Replies are deterministic for a given proposal. They lead to questions, negotiation, interview
  requests or scam signals, and some client messages carry planted prompt injections.
- **Policy:** `gigsim/policy.yaml` holds versioned rules. The platform policy update is switched on with
  `/admin/policy?version=v2`.

## Run
```
uvicorn gigsim.app:app --port 8081
```
