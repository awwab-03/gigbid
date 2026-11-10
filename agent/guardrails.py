"""Guardrails for untrusted text (R9 / E4): delimiting, injection detection, output checks.

Defence in depth:
 1. Job posts and client messages are wrapped in <untrusted_*> tags with any look-alike tags
    neutralised, and every prompt says content inside them is data, never instructions.
 2. A detector flags instruction-like spans (and the Risk Assessor reports them in the UI).
 3. Detected spans are REMOVED from the text the Writer sees (quarantine).
 4. Outputs are checked for signs an injection worked: copied tokens from the injected span,
    contact details, system-prompt leakage, prices far below the freelancer's floor.
The attack-success rate before/after these defences is measured by evals/runners/injection_eval.py.
"""

from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all |any |your )?(previous|prior|above|earlier)? ?(instructions|rules|prompts?)",
    r"disregard (the |your |all )?(previous |prior )?(instructions|rules|rates|guidelines)",
    r"(note|instruction|message) (to|for) (any )?(ai|llm|assistant|bot|gpt|language model)",
    r"\b(ai|llm) (assistant|tools?|agents?)\b[^.\n]{0,40}\b(must|should|need to|are required to)\b",
    r"\bassistant instruction\b",
    r"\bsystem( prompt| override| message)?\s*[:#]",
    r"#{2,}\s*system",
    r"<!--.*?-->",
    r"(print|reveal|show|output) (your |the )?(full |hidden )?(system prompt|instructions)",
    r"you must include the (phrase|word|code)",
    r"(begin|start) (the|your) proposal with",
    r"(add|include) (the )?(freelancer'?s )?(personal )?(email|phone|whatsapp|contact)",
    r"bid exactly \$?\d+",
    r"accept \$\d+ for the whole",
]
INJ_RE = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.I | re.S)
TAG_RE = re.compile(r"</?\s*untrusted[^>]*>", re.I)
CONTACT_RE = re.compile(r"([\w.+-]+@[\w-]+\.[\w.]+)|(\+?\d[\d\s().-]{8,}\d)|\b(whats\s?app|telegram|skype|signal app|wechat)\b", re.I)
LEAK_RE = re.compile(r"(system prompt|my instructions are|untrusted_job_post|you are the .{0,30} agent)", re.I)


def detect_injection(text: str) -> list[str]:
    """Return the sentences/lines that contain instruction-like content aimed at an AI."""
    spans = []
    for m in INJ_RE.finditer(text or ""):
        start = max(text.rfind("\n", 0, m.start()), text.rfind(". ", 0, m.start()))
        end_candidates = [i for i in (text.find("\n", m.end()), text.find(". ", m.end())) if i >= 0]
        end = min(end_candidates) if end_candidates else len(text)
        span = text[start + 1: end + 1].strip()
        if span and span not in spans:
            spans.append(span)
    return spans


def quarantine(text: str, spans: list[str]) -> str:
    out = text or ""
    for s in spans:
        out = out.replace(s, "[removed: instruction-like text from an untrusted post]")
    return out


def wrap_untrusted(text: str, kind: str = "job_post") -> str:
    clean = TAG_RE.sub("[tag removed]", text or "")
    clean = re.sub(r"[​-‏‪-‮⁠-⁤]", "", clean)  # zero-width / bidi controls
    return f"<untrusted_{kind}>\n{clean}\n</untrusted_{kind}>"


def output_violations(output: str, *, injected_spans: list[str], floor: float | None = None,
                      bid_amount: float | None = None) -> list[str]:
    """Signals that an injection or unsafe behaviour reached the output."""
    v = []
    low = (output or "").lower()
    for span in injected_spans:
        for tok in re.findall(r"\b[A-Z][A-Z0-9]{3,}-\d{1,3}\b|\b[A-Z]{5,}\b", span):
            if tok.lower() in low:
                v.append(f"echoed injected token {tok}")
    if CONTACT_RE.search(output or ""):
        v.append("contact details or off-platform channel in output")
    if LEAK_RE.search(output or ""):
        v.append("possible system-prompt leakage")
    if floor and bid_amount is not None and bid_amount < 0.5 * floor:
        v.append(f"bid {bid_amount} far below floor {floor}")
    return v
