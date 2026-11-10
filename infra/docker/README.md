# Docker images

| File | Service(s) |
|---|---|
| `api.Dockerfile` | FastAPI API |
| `worker.Dockerfile` | Arq worker (scheduled scouting, graph runs) |
| `mcp.Dockerfile` | Portfolio / Marketplace / Workspace MCP servers (`SERVER=` env) |
| `gigsim.Dockerfile` | GigSim simulator |
| `web.Dockerfile` | React build served by Caddy, which also proxies `/api` to the API (SSE-friendly, `flush_interval -1`) |

Embedding and reranker models (CPU, ONNX) are downloaded at build time so containers start offline.
