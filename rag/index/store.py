"""Per-persona portfolio index: dense vectors + BM25 over two chunkings.

Vector store: an on-disk exact-search store (numpy matrix + JSONL metadata) under
data/processed/<persona>/. The corpus is ~1k chunks per persona, where exact cosine search is
faster than an ANN index and has perfect recall (docs/adr/0003-vector-store.md).

Incremental re-indexing: embeddings are cached by the SHA-256 of the chunk text, so adding a
case study in the UI only embeds the new chunks (B1).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from rag.index.models import CFG, embed
from rag.ingest.loaders import Document, fixed_chunks, load_portfolio, structured_chunks

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = Path(os.getenv("GIGBID_PERSONA_DIR", ROOT / "data" / "personas"))
PROCESSED = Path(os.getenv("GIGBID_PROCESSED_DIR", ROOT / "data" / "processed"))
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*[a-z0-9+#]|[a-z0-9]")
STOP = set("the a an and or of to in for on with by at from is are was were be been it this that as i we our you your my "
           "built build using used use into than then also have has had not but".split())


def tokenize(text: str) -> list[str]:
    toks = [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]
    # keep compound tech names searchable both whole and split: "next.js" -> next.js, next, js
    extra = []
    for t in toks:
        if any(c in t for c in "./-") and len(t) > 3:
            extra += [p for p in re.split(r"[./-]", t) if len(p) > 1]
    return toks + extra


@dataclass
class Hit:
    chunk_id: str
    score: float
    text: str
    meta: dict

    @property
    def projects(self) -> list[str]:
        if self.meta.get("type") == "proposal":
            return list(self.meta.get("cited_projects") or [])
        return [self.meta["project"]] if self.meta.get("project") else []


class PgVectorStore:
    """Deployed vector store: Postgres + pgvector (VECTOR_BACKEND=pgvector). Exact cosine search with
    `<=>`; rows are upserted incrementally, so only new chunks are written."""

    def __init__(self, persona: str, name: str):
        import psycopg
        from pgvector.psycopg import register_vector

        self.persona, self.name = persona, name
        self.conn = psycopg.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.conn.execute("CREATE TABLE IF NOT EXISTS vec_chunks (persona text, chunk_set text, chunk_id text, text_hash text, "
                          "emb vector(384), PRIMARY KEY (persona, chunk_set, chunk_id))")

    def sync(self, ids: list[str], hashes: list[str], vecs: np.ndarray) -> None:
        have = {r[0]: r[1] for r in self.conn.execute("SELECT chunk_id, text_hash FROM vec_chunks WHERE persona=%s AND chunk_set=%s",
                                                       (self.persona, self.name)).fetchall()}
        with self.conn.cursor() as cur:
            for cid, h, v in zip(ids, hashes, vecs, strict=False):
                if have.get(cid) != h:
                    cur.execute("INSERT INTO vec_chunks VALUES (%s,%s,%s,%s,%s) ON CONFLICT (persona, chunk_set, chunk_id) "
                                "DO UPDATE SET text_hash=EXCLUDED.text_hash, emb=EXCLUDED.emb", (self.persona, self.name, cid, h, v))
            stale = set(have) - set(ids)
            if stale:
                cur.execute("DELETE FROM vec_chunks WHERE persona=%s AND chunk_set=%s AND chunk_id = ANY(%s)",
                            (self.persona, self.name, list(stale)))

    def search(self, qvec: np.ndarray, k: int) -> list[tuple[str, float]]:
        rows = self.conn.execute("SELECT chunk_id, 1 - (emb <=> %s) FROM vec_chunks WHERE persona=%s AND chunk_set=%s "
                                 "ORDER BY emb <=> %s LIMIT %s", (qvec, self.persona, self.name, qvec, k)).fetchall()
        return [(r[0], float(r[1])) for r in rows]


class ChunkSet:
    def __init__(self, name: str, chunks: list[Document], cache_dir: Path, persona: str = ""):
        self.name = name
        self.chunks = chunks
        self.ids = [c.doc_id for c in chunks]
        self.by_id = {c.doc_id: c for c in chunks}
        self.pos = {cid: i for i, cid in enumerate(self.ids)}
        self.vecs = self._embed_cached([c.text for c in chunks], cache_dir / f"emb_cache_{name}.npz")
        self.bm25 = BM25Okapi([tokenize(c.text) for c in chunks])
        self.pg = None
        if os.getenv("VECTOR_BACKEND") == "pgvector" and os.getenv("DATABASE_URL", "").startswith("postgres"):
            self.pg = PgVectorStore(persona, name)
            self.pg.sync(self.ids, [hashlib.sha256(c.text.encode()).hexdigest() for c in chunks], self.vecs)

    @staticmethod
    def _embed_cached(texts: list[str], path: Path) -> np.ndarray:
        cache: dict[str, np.ndarray] = {}
        if path.exists():
            z = np.load(path, allow_pickle=False)
            cache = dict(zip(z["keys"].tolist(), z["vecs"], strict=False))
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        missing = [i for i, k in enumerate(keys) if k not in cache]
        if missing:
            new = embed([texts[i] for i in missing])
            for i, v in zip(missing, new, strict=False):
                cache[keys[i]] = v
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, keys=np.array(list(cache.keys())), vecs=np.stack(list(cache.values())))
        return np.stack([cache[k] for k in keys]) if keys else np.zeros((0, 384), dtype=np.float32)

    def _hits(self, idx: np.ndarray, scores: np.ndarray) -> list[Hit]:
        return [Hit(self.ids[i], float(scores[i]), self.chunks[i].text, self.chunks[i].meta) for i in idx]

    def dense(self, qvec: np.ndarray, k: int, where=None) -> list[Hit]:
        if self.pg is not None:
            out = []
            for cid, score in self.pg.search(qvec, k * (6 if where else 1)):
                c = self.by_id.get(cid)
                if c is not None and (not where or where(c.meta)):
                    out.append(Hit(cid, score, c.text, c.meta))
            return out[:k]
        s = self.vecs @ qvec
        if where:
            s = np.where([where(c.meta) for c in self.chunks], s, -1e9)
        idx = np.argsort(-s)[:k]
        return [h for h in self._hits(idx, s) if h.score > -1e8]

    def lexical(self, query: str, k: int, where=None) -> list[Hit]:
        s = np.asarray(self.bm25.get_scores(tokenize(query)))
        if where:
            s = np.where([where(c.meta) for c in self.chunks], s, -1e9)
        idx = np.argsort(-s)[:k]
        return [h for h in self._hits(idx, s) if h.score > 0]


class PortfolioIndex:
    def __init__(self, persona: str, portfolio_dir: Path | None = None):
        self.persona = persona
        self.dir = Path(portfolio_dir or PERSONA_DIR / persona)
        self.cache = PROCESSED / persona
        self.reload()

    def reload(self) -> None:
        self.docs = load_portfolio(self.dir)
        self.doc_by_id = {d.doc_id: d for d in self.docs}
        rc = CFG["rag"]
        self.fixed = ChunkSet("fixed", fixed_chunks(self.docs, rc["chunk_size"], rc["chunk_overlap"]), self.cache, self.persona)
        self.struct = ChunkSet("struct", structured_chunks(self.docs), self.cache, self.persona)
        projects = json.loads((self.dir / "projects.json").read_text(encoding="utf-8")) if (self.dir / "projects.json").exists() else []
        self.projects = {p["id"]: p for p in projects}
        self.proposals = [d for d in self.docs if d.meta.get("type") == "proposal"]

    def skills(self) -> dict[str, list[str]]:
        """Skill -> project ids, from case-study metadata (explicit skills only)."""
        out: dict[str, list[str]] = {}
        for d in self.docs:
            if d.meta.get("type") == "case_study":
                for s in d.meta.get("skills", []):
                    out.setdefault(s, []).append(d.meta["project"])
        return dict(sorted(out.items()))


_INDEXES: dict[str, PortfolioIndex] = {}


_INDEX_LOCK = threading.Lock()


def get_index(persona: str) -> PortfolioIndex:
    # MCP tools now run in worker threads: build each persona's index once even under concurrent calls
    if persona not in _INDEXES:
        with _INDEX_LOCK:
            if persona not in _INDEXES:
                _INDEXES[persona] = PortfolioIndex(persona)
    return _INDEXES[persona]


def refresh_index(persona: str) -> PortfolioIndex:
    """Incremental re-index after the user adds work (only new chunk texts are embedded)."""
    idx = get_index(persona)
    idx.reload()
    return idx
