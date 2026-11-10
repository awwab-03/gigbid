"""PII masking for logs, traces and the audit log (R9 / E4).

Masks emails, phone numbers, payment card numbers, IBANs, crypto wallets and bearer tokens.
Applied to every string that leaves the process for logging or tracing.
"""

from __future__ import annotations

import re
from typing import Any

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("WALLET", re.compile(r"\b(0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|T[A-Za-z1-9]{33})\b")),
    ("PHONE", re.compile(r"(?<![\w$.:-])\+?\d[\d\s().-]{7,}\d(?![\w:-])")),
    ("TOKEN", re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}")),
    ("SECRET", re.compile(r"(?i)\b(sk|gsk|pk|ghp|github_pat|xox[bp])[-_][A-Za-z0-9_\-]{10,}")),
]


DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")


def _phone(m: re.Match) -> str:
    s = m.group(0)
    digits = sum(c.isdigit() for c in s)
    if DATE_LIKE.match(s.strip()) or digits < 10 or digits > 15:
        return s
    return "[PHONE]"


def mask(text: str) -> str:
    if not text:
        return text
    out = text
    for name, pat in PATTERNS:
        if name == "TOKEN":
            out = pat.sub(lambda m: m.group(1) + "[TOKEN]", out)
        elif name == "PHONE":
            out = pat.sub(_phone, out)
        elif name == "CARD":
            out = pat.sub(lambda m: m.group(0) if DATE_LIKE.match(m.group(0).strip()) else "[CARD]", out)
        else:
            out = pat.sub(f"[{name}]", out)
    return out


def mask_obj(obj: Any, depth: int = 0) -> Any:
    """Recursively mask strings inside dicts/lists; drops obvious secret keys."""
    if depth > 8:
        return "[...]"
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in {"password", "access_token", "refresh_token", "authorization", "api_key", "secret", "token"}:
                out[k] = "[REDACTED]"
            else:
                out[k] = mask_obj(v, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [mask_obj(v, depth + 1) for v in obj]
    return obj


def contains_pii(text: str) -> list[str]:
    return [name for name, pat in PATTERNS if pat.search(text or "")]
