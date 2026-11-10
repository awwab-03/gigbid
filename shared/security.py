"""Signed service tokens, symmetric encryption for stored OAuth tokens, and trace ids."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from contextvars import ContextVar

from cryptography.fernet import Fernet

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _secret() -> bytes:
    return os.getenv("MCP_SHARED_SECRET", os.getenv("APP_SECRET_KEY", "dev-only-secret")).encode()


def sign_service_token(user_id: str, account: str) -> str:
    """Token GigBid presents to its own MCP servers: '<user>:<account>.<hmac>'."""
    body = f"{user_id}:{account}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{body}.{sig}"


def verify_service_token(token: str) -> tuple[str, str] | None:
    try:
        body, sig = token.rsplit(".", 1)
        user, account = body.split(":", 1)
    except ValueError:
        return None
    good = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]
    return (user, account) if hmac.compare_digest(sig, good) else None


def _fernet() -> Fernet:
    raw = os.getenv("TOKEN_ENCRYPTION_KEY")
    if raw:
        return Fernet(raw.encode())
    # derive a stable key from APP_SECRET_KEY for development; production sets TOKEN_ENCRYPTION_KEY
    digest = hashlib.sha256(_secret()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
