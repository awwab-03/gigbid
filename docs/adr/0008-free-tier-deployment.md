# ADR 0008: Free-tier deployment on an Oracle Cloud Always Free VM

**Decision.** One Always Free `VM.Standard.E2.1.Micro` (1 GB RAM + 4 GB swap, Ubuntu 24.04, Toronto) runs GigBid
as a single process: GigSim and the API as two systemd services, the three MCP servers in-process
(`MCP_TRANSPORT=inproc`), jobs and the worker's schedules in-process (`WORKER_MODE=inline`, `INLINE_CRON=1`),
local Postgres 16 + pgvector, native Caddy with Let's Encrypt on an sslip.io hostname. Files: `infra/deploy/oracle/`.

**Why.** No budget. Hugging Face Docker Spaces turned out to be paid, the Azure student credit is reserved for other
work, and the Ampere A1 shape had no capacity in the home region. The micro VM never sleeps, so the hidden test run
after the deadline needs no keep-alive.

**Consequences.** Separate MCP processes, Redis and the Arq worker are only in `infra/docker-compose.yml` (the
reference multi-container deployment). The VM is slow at embedding, so the portfolio embedding caches are copied
from a dev machine (same model, same keys). Sync MCP tools run in worker threads so CPU-bound retrieval never blocks
the API event loop. The HF deploy and keep-alive workflows are unused.
