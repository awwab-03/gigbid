"""Per-user encrypted OAuth token store (E4: tokens encrypted at rest, never logged, tenant-scoped).

Postgres when DATABASE_URL is set, sqlite otherwise. Ciphertext only; plaintext exists in memory
for the duration of one call.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from shared.security import decrypt, encrypt

DDL = ("CREATE TABLE IF NOT EXISTS oauth_tokens (user_id TEXT NOT NULL, provider TEXT NOT NULL, ciphertext TEXT NOT NULL,"
       " expires_at TEXT, updated_at TEXT, PRIMARY KEY (user_id, provider))")


def _pg_url() -> str | None:
    url = os.getenv("DATABASE_URL", "")
    return url.replace("postgresql+psycopg://", "postgresql://") if url.startswith("postgres") else None


class TokenStore:
    def __init__(self) -> None:
        self.pg = _pg_url()
        if not self.pg:
            path = Path(os.getenv("MCP_STATE_DIR", "logs")) / "tokens.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.sq = sqlite3.connect(str(path), check_same_thread=False)
            self.sq.execute(DDL)
            self.sq.commit()

    def _exec(self, sql: str, args: tuple, fetch: bool = False):
        if self.pg:
            import psycopg

            with psycopg.connect(self.pg, autocommit=True) as conn:
                conn.execute(DDL)
                cur = conn.execute(sql.replace("?", "%s"), args)
                return cur.fetchone() if fetch else None
        cur = self.sq.execute(sql, args)
        self.sq.commit()
        return cur.fetchone() if fetch else None

    def save(self, user_id: str, provider: str, token: dict) -> None:
        exp = token.get("expires_at")
        self._exec("DELETE FROM oauth_tokens WHERE user_id=? AND provider=?", (user_id, provider))
        self._exec("INSERT INTO oauth_tokens VALUES (?,?,?,?,?)",
                   (user_id, provider, encrypt(json.dumps(token)), exp, datetime.now(timezone.utc).isoformat()))

    def load(self, user_id: str, provider: str) -> dict | None:
        row = self._exec("SELECT ciphertext FROM oauth_tokens WHERE user_id=? AND provider=?", (user_id, provider), fetch=True)
        return json.loads(decrypt(row[0])) if row else None

    def delete(self, user_id: str, provider: str) -> None:
        self._exec("DELETE FROM oauth_tokens WHERE user_id=? AND provider=?", (user_id, provider))
