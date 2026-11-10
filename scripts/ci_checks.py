"""Repository rules enforced in CI:
  1. no secrets in the repo
  2. nothing under gigsim/ changed (checksums in gigsim/CHECKSUMS.sha256)
  3. every prompt lives in agent/prompts/ (no inline system prompts in Python)
  4. every results file the README cites exists in evals/results/

  python scripts/ci_checks.py            # check
  python scripts/ci_checks.py --freeze   # regenerate gigsim checksums (deliberate simulator release only)
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|lsv2_[a-z]{2}_[A-Za-z0-9]{20,}"
                    r"|hf_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)")
PROMPT = re.compile(r"""["'](You are (the|an?) [A-Z][^"']{10,})""")


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    return [ROOT / p for p in out if p]


def gigsim_files() -> list[Path]:
    return sorted(p for p in tracked() if p.relative_to(ROOT).parts[0] == "gigsim" and p.name != "CHECKSUMS.sha256" and p.is_file())


def checksums() -> str:
    # hash with LF line endings so Windows working copies and Linux CI agree
    lines = []
    for p in gigsim_files():
        digest = hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        lines.append(f"{digest}  {p.relative_to(ROOT).as_posix()}\n")
    return "".join(lines)


def main() -> int:
    if "--freeze" in sys.argv:
        (ROOT / "gigsim" / "CHECKSUMS.sha256").write_text(checksums(), encoding="utf-8")
        print("gigsim checksums frozen")
        return 0
    errors = []
    for p in tracked():
        if not p.is_file() or p.suffix in (".pdf", ".png", ".jpg", ".npz") or "package-lock" in p.name:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if SECRET.search(text):
            errors.append(f"possible secret in {p.relative_to(ROOT)}")
        if p.suffix == ".py" and "agent/prompts" not in p.as_posix() and PROMPT.search(text) and "fake_llm" not in p.name:
            errors.append(f"inline prompt in {p.relative_to(ROOT)} (move it to agent/prompts/)")
        if p.name in (".env",) or (p.name.startswith(".env.") and p.name != ".env.example"):
            errors.append(f"env file committed: {p.relative_to(ROOT)}")
    frozen = ROOT / "gigsim" / "CHECKSUMS.sha256"
    if not frozen.exists() or frozen.read_text(encoding="utf-8") != checksums():
        errors.append("gigsim/ changed without a deliberate re-freeze (python scripts/ci_checks.py --freeze)")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for ref in set(re.findall(r"evals/results/[\w./-]+\.(?:json|csv|jsonl)", readme)):
        if not (ROOT / ref).exists():
            errors.append(f"README cites missing results file {ref}")
    for e in errors:
        print("FAIL:", e)
    print("ci checks:", "FAILED" if errors else "ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
