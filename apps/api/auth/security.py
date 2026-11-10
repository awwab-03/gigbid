"""Multi-user auth: bcrypt password hashes and short-lived JWT bearer tokens."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import insert

from apps.api import db

SECRET = os.getenv("APP_SECRET_KEY", "dev-only-secret")
ALGO = "HS256"
TTL_H = int(os.getenv("JWT_TTL_HOURS", "72"))
bearer = HTTPBearer(auto_error=False)

DEFAULT_SETTINGS = {
    "autonomy": "suggest",
    "weekly_connects_budget": 80,
    "marketplace_mode": "gigsim",
    "saved_searches": [],
    "timezone": "Asia/Karachi",
}


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def issue(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=TTL_H)}, SECRET, algorithm=ALGO)


def create_user(email: str, password: str, name: str, account: str, settings: dict | None = None) -> dict:
    uid = "u_" + uuid.uuid4().hex[:12]
    with db.engine.begin() as c:
        c.execute(insert(db.users).values(id=uid, email=email.lower(), password_hash=hash_pw(password), name=name, account=account,
                                          settings={**DEFAULT_SETTINGS, **(settings or {})}))
    return db.get_user(uid)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not cred:
        raise HTTPException(401, "not signed in")
    try:
        sub = jwt.decode(cred.credentials, SECRET, algorithms=[ALGO])["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid or expired session") from e
    u = db.get_user(sub)
    if not u:
        raise HTTPException(401, "unknown user")
    return u
