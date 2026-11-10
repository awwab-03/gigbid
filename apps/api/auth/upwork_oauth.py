"""OAuth 2.1 (authorization code + PKCE) for the official Upwork MCP server (A4).

Follows the MCP authorization spec: discover the protected-resource metadata, then the
authorization-server metadata, register a client dynamically if no client id is configured,
redirect the user with a PKCE challenge, and exchange the code. Tokens are stored encrypted per
user (shared/token_store.py) and never logged.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx

from shared.token_store import TokenStore

MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
REDIRECT = os.getenv("UPWORK_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/upwork/callback")
_pending: dict[str, dict] = {}


async def _discover(client: httpx.AsyncClient) -> dict:
    u = urlparse(MCP_URL)
    base = f"{u.scheme}://{u.netloc}"
    pr = (await client.get(f"{base}/.well-known/oauth-protected-resource")).json()
    issuer = (pr.get("authorization_servers") or [base])[0].rstrip("/")
    return (await client.get(f"{issuer}/.well-known/oauth-authorization-server")).json()


async def _client_id(client: httpx.AsyncClient, meta: dict) -> tuple[str, str | None]:
    if os.getenv("UPWORK_CLIENT_ID"):
        return os.environ["UPWORK_CLIENT_ID"], os.getenv("UPWORK_CLIENT_SECRET")
    reg = await client.post(meta["registration_endpoint"], json={
        "client_name": "GigBid", "redirect_uris": [REDIRECT], "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "token_endpoint_auth_method": "none"})
    reg.raise_for_status()
    return reg.json()["client_id"], None


async def start(user_id: str) -> str:
    async with httpx.AsyncClient(timeout=15) as c:
        meta = await _discover(c)
        cid, secret = await _client_id(c, meta)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    _pending[state] = {"user_id": user_id, "verifier": verifier, "client_id": cid, "client_secret": secret, "meta": meta,
                       "at": time.time()}
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": REDIRECT, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state, "resource": MCP_URL})


async def finish(code: str, state: str) -> None:
    p = _pending.pop(state, None)
    if not p or time.time() - p["at"] > 900:
        raise ValueError("unknown or expired OAuth state")
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT, "client_id": p["client_id"],
            "code_verifier": p["verifier"], "resource": MCP_URL}
    if p["client_secret"]:
        data["client_secret"] = p["client_secret"]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(p["meta"]["token_endpoint"], data=data)
        r.raise_for_status()
        tok = r.json()
    tok["expires_at"] = time.time() + float(tok.get("expires_in", 3600))
    tok["client_id"] = p["client_id"]
    TokenStore().save(p["user_id"], "upwork", tok)
