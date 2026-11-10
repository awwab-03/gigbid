# ADR 0008: Free-tier deployment on a Hugging Face Space + Neon Postgres

**Decision.** One Docker container on a free HF Space (2 vCPU, 16 GB) runs every service under supervisord;
Postgres is a free Neon database. **Why.** No budget for a VPS; HF is the only free host with enough RAM for the
CPU embedding and reranking models plus seven processes. **Risks.** Free Spaces sleep after 48 h idle: a GitHub
Actions cron pings `/api/health` every 6 h. Cold start is about a minute. `docker compose` remains the reference
local deployment with separate containers.
