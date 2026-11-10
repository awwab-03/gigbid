"""Claim verification (B3 / R5): split a draft into claims, ground each one, fix the draft.

Labels
  supported         best evidence is relevant (cross-encoder), every number and every named skill
                    is found in the freelancer's evidence, and no named skill is only "mentioned
                    but not used"
  partly_supported  relevant evidence exists but a number or a skill does not check out
  unsupported       no relevant evidence, or it names a skill the portfolio does not prove
  not_a_claim       greetings, questions, plans ("I would start by ...")

Unsupported sentences are removed; partly supported ones are rewritten (LLM when a rewriter is
injected, otherwise the unverifiable number/skill is dropped from the sentence). The Critic only
ever sees the fixed draft. Thresholds come from agent/config.yaml.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from rag.index.models import CFG, embed, rerank_scores, sigmoid
from rag.index.store import Hit, PortfolioIndex
from rag.variants.v2_hybrid import hybrid

ROOT = Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / "data" / "policy_pack" / "skills_vocab.json").read_text(encoding="utf-8"))
SKILL_NAMES = sorted(VOCAB["skills"] + VOCAB["out_of_scope_examples"], key=len, reverse=True)
NUM_RE = re.compile(r"(?<![\w.])\$?\d[\d,]*(\.\d+)?\s?(%|x\b|k\b)?")
PLAN_RE = re.compile(r"^\s*(i\s+(would|will|can|could|'d|'ll|plan|propose|suggest)|let's|we\s+(would|will|can|could)|"
                     r"happy to|could you|can you|would you|when would|looking forward|thanks|thank you|best regards|regards)", re.I)
CLAIM_HINT = re.compile(r"\b(i|i've|i'm|my|we|our)\b|\d", re.I)
NEGATED = re.compile(r"(decided not to use|did not use|didn't use|not use it|considered .{0,40} but|looked at .{0,40} (but|early on))", re.I)

_rewriter: Callable[[str, list[str]], str] | None = None


def set_rewriter(fn: Callable[[str, list[str]], str] | None) -> None:
    global _rewriter
    _rewriter = fn


@dataclass
class ClaimCheck:
    claim: str
    label: str
    score: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    evidence_snippet: str = ""
    missing_numbers: list[str] = field(default_factory=list)
    unproven_skills: list[str] = field(default_factory=list)
    fixed: str | None = None


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def is_claim(sentence: str) -> bool:
    if sentence.endswith("?") or PLAN_RE.search(sentence):
        return False
    return bool(CLAIM_HINT.search(sentence)) or any(_has_skill(sentence, s) for s in SKILL_NAMES[:60])


def _has_skill(text: str, skill: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(skill.lower()) + r"(?![\w])", text.lower()) is not None


def skills_in(text: str) -> list[str]:
    found, low = [], text.lower()
    for s in SKILL_NAMES:
        if len(s) <= 2 and s != "R":
            continue
        if s == "R":
            if re.search(r"(?<![\w])R(?![\w+#])", text) and re.search(r"\b(in|with|using)\s+R\b", text):
                found.append(s)
            continue
        if _has_skill(low, s) and not any(s.lower() in f.lower() for f in found):
            found.append(s)
    return found


def _norm_num(n: str) -> str:
    return n.replace(",", "").replace("$", "").replace(" ", "").lower()


class SkillProof:
    """Which skills the portfolio genuinely proves (named in a non-negated sentence or in code)."""

    def __init__(self, index: PortfolioIndex):
        self.proven: set[str] = set()
        for d in index.docs:
            if d.meta.get("type") == "proposal":  # past proposals are claims, not proof
                continue
            for sent in split_sentences(d.text) if d.meta.get("type") != "code" else [d.text]:
                if NEGATED.search(sent):
                    continue
                for s in skills_in(sent):
                    self.proven.add(s)
        for d in index.docs:
            if d.meta.get("type") == "code":
                for s in skills_in(d.text):
                    self.proven.add(s)


_proofs: dict[str, SkillProof] = {}


def check_claim(claim: str, index: PortfolioIndex, evidence: list[Hit] | None = None) -> ClaimCheck:
    th = CFG["thresholds"]
    proof = _proofs.setdefault(index.persona, SkillProof(index))
    qv = embed([claim], query=True)[0]
    cands = {h.chunk_id: h for h in (evidence or [])}
    for h in hybrid(index, claim, qv, n=8):
        if h.meta.get("type") != "proposal":  # a past proposal is not evidence of experience
            cands.setdefault(h.chunk_id, h)
    cl = list(cands.values())
    if not cl:
        return ClaimCheck(claim, "unsupported")
    scores = rerank_scores(claim, [c.text[:1500] for c in cl])
    order = sorted(range(len(cl)), key=lambda i: -scores[i])
    best = [cl[i] for i in order[:3]]
    rel = sigmoid(scores[order[0]])
    ev_text = " ".join(b.text for b in best).lower().replace(",", "")
    nums = [m.group(0).strip() for m in NUM_RE.finditer(claim)]
    missing = [n for n in nums if _norm_num(n).rstrip("%xk") not in ev_text]
    unproven = [s for s in skills_in(claim) if s not in proof.proven]
    support_min = float(th.get("claim_support_min", 0.55))
    if unproven:
        label = "unsupported"
    elif rel >= support_min and not missing:
        label = "supported"
    elif rel >= support_min * 0.5:
        label = "partly_supported"
    else:
        label = "unsupported"
    return ClaimCheck(claim, label, round(rel, 4), [b.chunk_id for b in best], best[0].text[:240], missing, unproven)


def _soften(c: ClaimCheck) -> str:
    if _rewriter:
        return _rewriter(c.claim, [c.evidence_snippet])
    if not c.missing_numbers:
        return ""  # nothing deterministic to repair: drop rather than keep an unverified attribution
    s = c.claim
    for n in c.missing_numbers:
        s = re.sub(re.escape(n) + r"(\s?(%|percent))?", "a measurable amount", s, count=1)
    return re.sub(r"\s{2,}", " ", s)


def verify_draft(text: str, index: PortfolioIndex, evidence: list[Hit] | None = None) -> dict:
    sentences = split_sentences(text)
    checks: list[ClaimCheck] = []
    kept: list[str] = []
    for s in sentences:
        if not is_claim(s):
            checks.append(ClaimCheck(s, "not_a_claim"))
            kept.append(s)
            continue
        c = check_claim(s, index, evidence)
        if c.label == "supported":
            kept.append(s)
        elif c.label == "partly_supported":
            c.fixed = _soften(c)
            if c.fixed:
                kept.append(c.fixed)
        else:
            c.fixed = ""
        checks.append(c)
    claims = [c for c in checks if c.label != "not_a_claim"]
    n = len(claims) or 1
    unsupported = sum(1 for c in claims if c.label == "unsupported")
    partly = sum(1 for c in claims if c.label == "partly_supported")
    return {
        "fixed_text": " ".join(k for k in kept if k),
        "claims": [asdict(c) for c in checks],
        "n_claims": len(claims),
        "unsupported_before": unsupported,
        "partly_before": partly,
        "unsupported_rate_before": round(unsupported / n, 4),
        "unsupported_rate_after": 0.0,  # unsupported sentences are removed; re-verified by the caller if edited
    }
