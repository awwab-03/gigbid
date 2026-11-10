"""Explicit promotion rules for long-term memory (R7).

Nothing enters long-term memory directly. Edits and marketplace outcomes are first recorded as
OBSERVATIONS; a rule below decides when a pattern is promoted into memory. Raw tool output and
LLM text never become memory.

Style memory (per user) - learned from the user's edits to drafts
  An edit yields observations such as  cut_first_sentence | removed_word:passionate | shortened |
  added_closing_question.  RULE S1: promote a pattern when it was observed in >= STYLE_MIN_EDITS
  distinct jobs AND its consistency (observed / opportunities, i.e. edits where the pattern could
  have applied) >= STYLE_MIN_CONSISTENCY.

Outcome memory (per user, per job category) - learned from confirmed marketplace events only
  RULE O1: promote "citing project P works in category C" when P was cited in >= OUTCOME_MIN_N
  proposals in C with an outcome, and its positive rate (replied/interview/hired) exceeds the
  category's base rate by >= OUTCOME_MIN_LIFT.
  RULE O2: promote "generic openings fail in C" when >= OUTCOME_MIN_N generic-opening proposals in C
  got no reply at all.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter

STYLE_MIN_EDITS = 3
STYLE_MIN_CONSISTENCY = 0.6
OUTCOME_MIN_N = 3
OUTCOME_MIN_LIFT = 0.15

WORD_RE = re.compile(r"[a-z][a-z'-]{3,}")
STOP = set("this that with from have your will would could their there about which what when been were they them "
           "into also than then such very more most some only just like make made over each".split())


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0] if text.strip() else ""


def observe_edit(original: str, edited: str) -> dict:
    """Turn one approve-with-edit into observations (and the opportunities each could have applied to)."""
    obs: list[str] = []
    opp: list[str] = ["cut_first_sentence", "shortened", "added_closing_question"]
    fs = first_sentence(original)
    if fs and fs not in edited and len(edited) > 0.4 * len(original):
        obs.append("cut_first_sentence")
    ow, ew = len(original.split()), len(edited.split())
    if ow and ew < 0.8 * ow:
        obs.append("shortened")
    if edited.strip().endswith("?") and not original.strip().endswith("?"):
        obs.append("added_closing_question")
    # word-level removals only inside sentences that SURVIVED the edit (a deleted sentence is one
    # observation, not one per word)
    o_sents = re.split(r"(?<=[.!?])\s+", original.strip())
    e_sents = re.split(r"(?<=[.!?])\s+", edited.strip())
    for s in o_sents:
        match = max(e_sents, key=lambda e: difflib.SequenceMatcher(None, s, e).ratio(), default="")
        if difflib.SequenceMatcher(None, s, match).ratio() < 0.5:
            continue
        kept_words = set(WORD_RE.findall(match.lower()))
        for w in Counter(x for x in WORD_RE.findall(s.lower()) if x not in STOP):
            opp.append(f"removed_word:{w}")
            if w not in kept_words:
                obs.append(f"removed_word:{w}")
    diff = "\n".join(difflib.unified_diff(original.splitlines(), edited.splitlines(), lineterm="", n=0))
    return {"observations": obs, "opportunities": opp, "diff": diff, "words_before": ow, "words_after": ew}


def style_promotions(observations: list[dict]) -> list[dict]:
    """Apply RULE S1 to all stored edit observations of one user. Returns promoted rules."""
    seen: Counter = Counter()
    chances: Counter = Counter()
    jobs: dict[str, set] = {}
    lengths = []
    for o in observations:
        for p in set(o["opportunities"]):
            chances[p] += 1
        for p in set(o["observations"]):
            seen[p] += 1
            jobs.setdefault(p, set()).add(o.get("job_id"))
        lengths.append(o.get("words_after", 0))
    promoted = []
    for p, n in seen.items():
        consistency = n / max(1, chances[p])
        if len(jobs[p]) >= STYLE_MIN_EDITS and consistency >= STYLE_MIN_CONSISTENCY:
            promoted.append({"pattern": p, "rule": _style_text(p, lengths), "evidence_edits": len(jobs[p]),
                             "consistency": round(consistency, 2), "promoted_by": "S1"})
    return promoted


def _style_text(pattern: str, lengths: list[int]) -> str:
    if pattern == "cut_first_sentence":
        return "Start directly with the client's problem; drop the opening pleasantry sentence."
    if pattern == "shortened":
        target = sorted(lengths)[len(lengths) // 2] if lengths else 150
        return f"Keep the cover letter to about {target} words."
    if pattern == "added_closing_question":
        return "End with one concrete question to the client."
    if pattern.startswith("removed_word:"):
        return f"Never use the word '{pattern.split(':', 1)[1]}'."
    return pattern


POSITIVE = {"replied", "interview", "hired"}


def outcome_promotions(observations: list[dict]) -> list[dict]:
    """Apply RULES O1 and O2 to confirmed outcome observations of one user, per category."""
    by_cat: dict[str, list[dict]] = {}
    for o in observations:
        by_cat.setdefault(o["category"], []).append(o)
    out = []
    for cat, obs in by_cat.items():
        base = sum(o["outcome"] in POSITIVE for o in obs) / len(obs)
        per_proj: dict[str, list[bool]] = {}
        for o in obs:
            for p in o.get("cited_projects", []):
                per_proj.setdefault(p, []).append(o["outcome"] in POSITIVE)
        for p, res in per_proj.items():
            rate = sum(res) / len(res)
            if len(res) >= OUTCOME_MIN_N and rate - base >= OUTCOME_MIN_LIFT:
                out.append({"category": cat, "insight": f"Citing project {p} in {cat} jobs got positive responses {sum(res)}/{len(res)} "
                            f"(category base rate {base:.0%}).", "project": p, "n": len(res), "rate": round(rate, 2), "promoted_by": "O1"})
        generic = [o for o in obs if o.get("generic_opening")]
        if len(generic) >= OUTCOME_MIN_N and not any(o["outcome"] in POSITIVE for o in generic):
            out.append({"category": cat, "insight": f"Generic openings got 0/{len(generic)} replies in {cat}; open with the client's problem.",
                        "n": len(generic), "promoted_by": "O2"})
    return out


def should_promote_style_edit(edit_count: int, consistent_pattern: bool) -> bool:
    """Back-compat helper from the starter kit, expressed with RULE S1's thresholds."""
    return edit_count >= STYLE_MIN_EDITS and consistent_pattern
