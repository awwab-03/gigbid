"""Settings (autonomy, budgets, saved searches, rates), the memory viewer (see and delete what
GigBid learned), portfolio upload with incremental re-index, and the Upwork OAuth 2.1 connect flow."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import update

from agent.memory.store import delete_memory, list_memory
from apps.api import db
from apps.api.auth.security import current_user
from apps.api.auth.upwork_oauth import finish, start
from apps.api.routers.auth import user_out
from apps.api.schemas.models import MemoryOut, Settings, UserOut
from shared.token_store import TokenStore

router = APIRouter(tags=["settings"])
ROOT = Path(__file__).resolve().parents[3]


@router.get("/settings", response_model=Settings, operation_id="getSettings")
def get_settings(user: dict = Depends(current_user)) -> Settings:
    return Settings(**{k: v for k, v in (user.get("settings") or {}).items() if k in Settings.model_fields})


@router.put("/settings", response_model=UserOut, operation_id="putSettings")
def put_settings(body: Settings, user: dict = Depends(current_user)) -> UserOut:
    with db.engine.begin() as c:
        c.execute(update(db.users).where(db.users.c.id == user["id"]).values(settings={**(user.get("settings") or {}), **body.model_dump()}))
    return user_out(db.get_user(user["id"]))


@router.get("/memory", response_model=MemoryOut, operation_id="getMemory")
def memory(user: dict = Depends(current_user)) -> MemoryOut:
    return MemoryOut(**list_memory(user["id"]))


@router.delete("/memory/{kind}/{key}", response_model=MemoryOut, operation_id="deleteMemory")
def forget(kind: str, key: str, category: str | None = None, user: dict = Depends(current_user)) -> MemoryOut:
    if kind not in ("style", "outcome"):
        raise HTTPException(422, "kind must be style or outcome")
    delete_memory(user["id"], kind, key, category)
    return MemoryOut(**list_memory(user["id"]))


@router.post("/portfolio/upload", operation_id="uploadPortfolio")
async def upload(file: UploadFile = File(...), project_title: str = "", user: dict = Depends(current_user)) -> dict:
    """Add a case study (Markdown or text) to the user's portfolio; only new chunks are embedded."""
    if not (file.filename or "").lower().endswith((".md", ".txt")):
        raise HTTPException(422, "upload a .md or .txt case study (PDF CVs are ingested at onboarding)")
    raw = (await file.read())[:200_000].decode("utf-8", errors="ignore")
    pid = "up-" + re.sub(r"[^a-z0-9]+", "-", (project_title or file.filename).lower()).strip("-")[:40]
    pdir = ROOT / "data" / "personas" / user["account"] / "case_studies"
    fm = (f"---\nid: case:{pid}\npersona: {user['account']}\ntype: case_study\nproject: {pid}\nskills: []\n"
          f"date: \nclient_industry: \nsynthetic: false\nuploaded_by: {user['id']}\n---\n# {project_title or file.filename}\n\n")
    (pdir / f"{pid}.md").write_text(fm + raw, encoding="utf-8")
    from rag.index.store import refresh_index

    idx = refresh_index(user["account"])
    return {"added": pid, "chunks": len(idx.struct.chunks)}


@router.get("/auth/upwork/start", operation_id="upworkStart")
async def upwork_start(user: dict = Depends(current_user)) -> dict:
    return {"authorize_url": await start(user["id"])}


@router.get("/auth/upwork/callback", include_in_schema=False)
async def upwork_callback(code: str, state: str):
    await finish(code, state)
    return RedirectResponse(os.getenv("WEB_ORIGIN", "http://localhost:5173") + "/settings?upwork=connected")


@router.delete("/auth/upwork", response_model=UserOut, operation_id="upworkDisconnect")
def upwork_disconnect(user: dict = Depends(current_user)) -> UserOut:
    TokenStore().delete(user["id"], "upwork")
    return user_out(user)
