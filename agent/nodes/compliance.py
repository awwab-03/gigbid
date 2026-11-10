"""Compliance Guard: enforce the policy pack (data/policy_pack/rules.yaml) and the live platform
policy (GET /policy). Removes contact details, off-platform asks, guarantees and invented claims;
blocks scams, injection echoes and length violations, with the reason shown in the UI."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from agent.guardrails import output_violations
from agent.handoffs import ComplianceVerdict, ComplianceViolation
from agent.llm import CFG
from agent.nodes._runtime import node, toolbox

ROOT = Path(__file__).resolve().parents[2]


def load_rules() -> dict:
    return yaml.safe_load((ROOT / CFG["policy"]["rules_file"]).read_text(encoding="utf-8"))


def check_text(text: str, *, risk: dict, verification: dict | None, policy: dict, bid: float | None = None,
               floor: float | None = None) -> ComplianceVerdict:
    rules = load_rules()["rules"]
    violations: list[ComplianceViolation] = []
    out = text
    for r in rules:
        k = r["kind"]
        if k == "regex_remove":
            for p in r["patterns"]:
                if re.search(p, out, re.I):
                    out = re.sub(p, "", out, flags=re.I)
                    violations.append(ComplianceViolation(rule=r["id"], detail=r["message"], severity=r["severity"]))
        elif k == "regex_sentence_remove":
            sents = re.split(r"(?<=[.!?])\s+", out)
            keep = [s for s in sents if not any(re.search(p, s, re.I) for p in r["patterns"])]
            if len(keep) < len(sents):
                violations.append(ComplianceViolation(rule=r["id"], detail=r["message"], severity=r["severity"]))
                out = " ".join(keep)
        elif k == "verifier" and verification and verification.get("unsupported_before", 0) > 0:
            violations.append(ComplianceViolation(rule=r["id"], detail=f"{verification['unsupported_before']} unsupported claim(s) removed",
                                                  severity="fix"))
        elif k == "risk" and risk.get("scam_likely"):
            violations.append(ComplianceViolation(rule=r["id"], detail=r["message"], severity="block"))
        elif k == "injection":
            v = output_violations(out, injected_spans=risk.get("injection_spans", []), floor=floor, bid_amount=bid)
            for x in v:
                sev = "block" if ("echoed" in x or "leakage" in x or "below floor" in x) else "fix"
                violations.append(ComplianceViolation(rule=r["id"], detail=x, severity=sev))
        elif k == "length":
            n = len(out.split())
            lo, hi = int(policy.get("min_cover_letter_words", 0)), int(policy.get("max_cover_letter_words", 99999))
            if n < lo or n > hi:
                violations.append(ComplianceViolation(rule=r["id"], detail=f"{n} words; policy {policy.get('version')} allows {lo}-{hi}",
                                                      severity="block"))
    out = re.sub(r"\s{2,}", " ", out).strip()
    status = "block" if any(v.severity == "block" for v in violations) else ("fixed" if out != text.strip() or violations else "pass")
    return ComplianceVerdict(status=status, violations=violations, fixed_text=out, policy_version=str(policy.get("version", "")))


@node("compliance")
async def compliance(state: dict) -> dict:
    d = state["draft"]
    policy = await toolbox(state, "compliance").call("marketplace.get_policy", {})
    text = d.get("edited_text") or d.get("cover_letter_verified") or d["cover_letter"]
    price = state.get("price", {})
    v = check_text(text, risk=state.get("risk_report", {}), verification=None if d.get("edited_text") else state.get("verification"),
                   policy=policy, bid=price.get("amount"), floor=price.get("floor"))
    out = {"compliance_verdict": v.model_dump(), "_summary": f"{v.status} ({len(v.violations)} violations)"}
    if v.status == "block":
        out.update(status="blocked", status_reason="; ".join(x.detail for x in v.violations if x.severity == "block")[:300])
    return out
