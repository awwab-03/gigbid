"""Loaders for a freelancer portfolio folder -> Documents with metadata (B1).

Handles: PDF CV, Markdown case studies (front matter), repo READMEs and code files, client
reviews, profile blurbs and past proposals with outcomes. Every document carries:
persona, type, item_id, project, skills, date, client_industry, outcome (proposals), source.

The same folder layout is what the published Portfolio MCP server reads, so another freelancer
can point PORTFOLIO_DIR at their own folder (see mcp_servers/portfolio/README.md).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CODE_EXT = {".py", ".ts", ".js", ".sql", ".dax", ".liquid", ".graphql", ".prisma", ".php", ".R", ".gs", ".yaml", ".yml", ".txt"}
CODE_NAMES = {"Dockerfile"}


@dataclass
class Document:
    doc_id: str
    text: str
    meta: dict = field(default_factory=dict)


def _front_matter(md: str) -> tuple[dict, str]:
    if not md.startswith("---"):
        return {}, md
    _, fm, body = md.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            try:
                meta[k.strip()] = json.loads(v)
            except json.JSONDecodeError:
                meta[k.strip()] = v
    return meta, body.strip()


def load_pdf(path: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)


def load_portfolio(pdir: Path) -> list[Document]:
    pdir = Path(pdir)
    persona = pdir.name
    docs: list[Document] = []
    projects = {p["id"]: p for p in json.loads((pdir / "projects.json").read_text(encoding="utf-8"))} if (pdir / "projects.json").exists() else {}
    manifest = json.loads((pdir / "manifest.json").read_text(encoding="utf-8")) if (pdir / "manifest.json").exists() else []
    repo_project = {m["path"]: m["project"] for m in manifest if m["type"] == "repo"}

    def base(project: str | None) -> dict:
        p = projects.get(project or "", {})
        return {"persona": persona, "project": project, "project_title": p.get("title"), "date": p.get("date"),
                "client_industry": p.get("industry"), "synthetic": True}

    cv = pdir / "cv.pdf"
    if cv.exists():
        docs.append(Document(f"cv:{persona}", load_pdf(cv), {**base(None), "type": "cv", "source": "cv.pdf", "skills": []}))
    for md in sorted((pdir / "case_studies").glob("*.md")):
        fm, body = _front_matter(md.read_text(encoding="utf-8"))
        proj = fm.get("project") or md.stem
        docs.append(Document(f"case:{proj}", body, {**base(proj), "type": "case_study", "source": f"case_studies/{md.name}",
                                                    "skills": fm.get("skills", [])}))
    repos = pdir / "repos"
    if repos.exists():
        for rdir in sorted(p for p in repos.iterdir() if p.is_dir()):
            proj = repo_project.get(f"repos/{rdir.name}")
            for f in sorted(rdir.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(rdir).as_posix()
                if f.name.lower() == "readme.md":
                    typ = "readme"
                elif f.suffix in CODE_EXT or f.name in CODE_NAMES:
                    typ = "code"
                else:
                    continue
                docs.append(Document(f"repo:{proj or rdir.name}:{rel}", f.read_text(encoding="utf-8", errors="ignore"),
                                     {**base(proj), "type": typ, "source": f"repos/{rdir.name}/{rel}", "repo": rdir.name, "skills": []}))
    for name, typ in (("reviews.json", "review"), ("profile_items.json", "profile_item")):
        f = pdir / name
        if f.exists():
            for r in json.loads(f.read_text(encoding="utf-8")):
                iid = r.get("review_id") or r.get("item_id")
                meta = {**base(r.get("project")), "type": typ, "source": name, "skills": []}
                if typ == "review":
                    meta["rating"] = r.get("rating")
                docs.append(Document(iid, r["text"], meta))
    f = pdir / "proposals.json"
    if f.exists():
        for pr in json.loads(f.read_text(encoding="utf-8")):
            cited = pr.get("cited_projects", [])
            meta = {**base(cited[0] if cited else None), "type": "proposal", "source": "proposals.json", "outcome": pr["outcome"],
                    "cited_projects": cited, "job_category": pr.get("job_category"), "skills": pr.get("job_skills", []),
                    "date": pr.get("date")}
            docs.append(Document(pr["proposal_id"], f"Proposal for: {pr['job_title']}\n{pr['text']}", meta))
    return docs


def fixed_chunks(docs: list[Document], size: int = 700, overlap: int = 100) -> list[Document]:
    """V0 chunking: fixed character windows, ignoring structure."""
    out = []
    for d in docs:
        t = d.text
        i = n = 0
        while i < len(t):
            out.append(Document(f"{d.doc_id}#f{n}", t[i: i + size], {**d.meta, "parent": d.doc_id}))
            i += size - overlap
            n += 1
    return out


def structured_chunks(docs: list[Document], max_chars: int = 1200) -> list[Document]:
    """Structure-aware chunking: Markdown sections, whole small items, code files split by blank-line blocks.
    Each chunk is prefixed with a short header naming the project and item type."""
    out = []
    for d in docs:
        head = f"[{d.meta.get('type')}] {d.meta.get('project_title') or ''}".strip()
        if d.meta.get("type") in ("case_study", "readme", "cv"):
            parts = re.split(r"\n(?=#{1,3} )", d.text)
        elif len(d.text) > max_chars:
            parts = re.split(r"\n\s*\n", d.text)
        else:
            parts = [d.text]
        buf, n = "", 0
        for part in parts:
            if buf and len(buf) + len(part) > max_chars:
                out.append(Document(f"{d.doc_id}#s{n}", f"{head}\n{buf.strip()}", {**d.meta, "parent": d.doc_id}))
                n += 1
                buf = ""
            buf += part + "\n"
        if buf.strip():
            out.append(Document(f"{d.doc_id}#s{n}", f"{head}\n{buf.strip()}", {**d.meta, "parent": d.doc_id}))
    return out
