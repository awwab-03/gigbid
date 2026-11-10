# Single-container deployment for a free Hugging Face Space (Docker SDK, port 7860).
# Runs GigSim, the three MCP servers, the API, the Arq worker, Redis and Caddy (web + /api proxy)
# under supervisord. Postgres (with pgvector) is external: set DATABASE_URL to a Neon database.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ENV VITE_API_URL=/api
RUN npx vite build

FROM caddy:2.10-alpine AS caddy

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/app/data/processed/models MCP_STATE_DIR=/app/state HOME=/app     REDIS_URL=redis://127.0.0.1:6379/0 MCP_TRANSPORT=http MODEL_PROFILE=open VECTOR_BACKEND=pgvector     OPEN_LLM_BASE_URL=https://api.groq.com/openai/v1 GIGSIM_BASE_URL=http://127.0.0.1:8081 GIGSIM_TIME_SCALE=20     PORTFOLIO_MCP_URL=http://127.0.0.1:8091/mcp MARKETPLACE_MCP_URL=http://127.0.0.1:8092/mcp WORKSPACE_MCP_URL=http://127.0.0.1:8093/mcp
RUN apt-get update && apt-get install -y --no-install-recommends supervisor redis-server curl && rm -rf /var/lib/apt/lists/* \
    && pip install uv==0.7.8
WORKDIR /app
COPY . .
RUN uv pip install --system -e . && python -c "from rag.index.models import embedder, reranker; embedder(); reranker()" \
    && python -c "from rag.index.store import get_index; [get_index(p) for p in ('ml_engineer','fullstack_dev','data_analyst')]"
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY --from=web /web/dist /srv
COPY infra/deploy/hf/supervisord.conf /etc/supervisor/conf.d/gigbid.conf
COPY infra/deploy/hf/Caddyfile /etc/caddy/Caddyfile
# HF Spaces run as uid 1000 with a writable /app
RUN mkdir -p /app/state /app/logs && useradd -m -u 1000 user 2>/dev/null || true && chown -R 1000:1000 /app /srv
USER 1000
EXPOSE 7860
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/gigbid.conf"]
