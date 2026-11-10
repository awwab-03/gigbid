"""Single-process dev launcher for the API: MCP servers in-process, inline worker, SQLite.
Real values in .env override these defaults. Production uses docker compose instead."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
for k, v in {"MCP_TRANSPORT": "inproc", "WORKER_MODE": "inline", "GIGSIM_BASE_URL": "http://localhost:8081",
             "MODEL_PROFILE": "local" if not os.getenv("OPEN_LLM_API_KEY") else "open", "GIGBID_TIMEOUT_SCALE": "10",
             "REVIEWER_EMAIL": "reviewer@gigbid.test", "REVIEWER_PASSWORD": "dev-reviewer-pass", "MCP_STATE_DIR": str(ROOT / "logs"),
             "WEB_ORIGIN": "http://localhost:5173"}.items():
    os.environ.setdefault(k, v)

import uvicorn  # noqa: E402

uvicorn.run("apps.api.main:app", host="127.0.0.1", port=int(os.getenv("API_PORT", "8000")))
