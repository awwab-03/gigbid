"""Model routing by node (config only), JSON-structured calls, fallbacks and usage/cost accounting.

* get_llm(node): model chosen from agent/config.yaml for the active profile (open | local | paid),
  with a fallback model for every node and per-call timeout / retries.
* call_json(node, prompt, variables, schema): renders agent/prompts/<prompt>.md, asks for JSON,
  validates with Pydantic and retries once with the validation error. Works on any chat model
  (Groq, OpenRouter, vLLM, Ollama) because it does not depend on provider-specific tool calling.
* Every call records tokens, cost and latency into a per-run UsageLedger (R8 / E5).
"""

from __future__ import annotations

import json
import os
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))
PROMPTS = ROOT / "agent" / "prompts"
T = TypeVar("T", bound=BaseModel)


def profile_name() -> str:
    return os.getenv("MODEL_PROFILE", CFG["models"]["profile"])


def profile() -> dict:
    return CFG["models"]["profiles"][profile_name()]


def model_for(node: str) -> tuple[str, str]:
    if node == "judge" and os.getenv("JUDGE_MODEL"):  # one fixed judge across every experiment arm and profile
        return os.environ["JUDGE_MODEL"], os.environ["JUDGE_MODEL"]
    p = profile()
    alias = p["nodes"].get(node) or p["nodes"].get("default", "small")
    return p["aliases"][alias], p["fallback"][alias]


@dataclass
class UsageRecord:
    node: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_s: float
    ok: bool = True


@dataclass
class UsageLedger:
    records: list[UsageRecord] = field(default_factory=list)

    def add(self, r: UsageRecord) -> None:
        self.records.append(r)

    @property
    def tokens(self) -> int:
        return sum(r.tokens_in + r.tokens_out for r in self.records)

    @property
    def cost(self) -> float:
        return round(sum(r.cost_usd for r in self.records), 6)

    def by_node(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in self.records:
            d = out.setdefault(r.node, {"calls": 0, "tokens": 0, "cost_usd": 0.0, "latency_s": 0.0})
            d["calls"] += 1
            d["tokens"] += r.tokens_in + r.tokens_out
            d["cost_usd"] = round(d["cost_usd"] + r.cost_usd, 6)
            d["latency_s"] = round(d["latency_s"] + r.latency_s, 3)
        return out


ledger_var: ContextVar[UsageLedger | None] = ContextVar("ledger", default=None)


def _price(model: str) -> dict:
    return profile().get("pricing_usd_per_mtok", {}).get(model, {"in": 0.0, "out": 0.0})


@lru_cache(maxsize=32)
def _chat(model: str, temperature: float):
    p = profile()
    timeout = CFG["models"]["timeout_s"]
    if p["provider"] == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=temperature, base_url=os.getenv(p["base_url_env"], "http://localhost:11434"),
                          num_ctx=8192, client_kwargs={"timeout": timeout})
    from langchain_openai import ChatOpenAI

    # LLM_PACE="gpt-oss-120b=2.4" paces a model client-side (requests/minute) to stay inside a free tier's limits
    pace = dict(x.split("=") for x in os.getenv("LLM_PACE", "").split(",") if "=" in x)
    limiter = None
    if model in pace:
        from langchain_core.rate_limiters import InMemoryRateLimiter

        limiter = InMemoryRateLimiter(requests_per_second=float(pace[model]) / 60, check_every_n_seconds=0.5, max_bucket_size=1)
    return ChatOpenAI(model=model, temperature=temperature, base_url=os.getenv(p["base_url_env"]), api_key=os.getenv(p["api_key_env"], "missing"),
                      timeout=timeout, max_retries=CFG["models"]["max_retries"], rate_limiter=limiter)


def get_llm(node: str):
    primary, fallback = model_for(node)
    temp = CFG["models"]["temperature"].get(node, CFG["models"]["temperature"]["default"])
    return _chat(primary, temp), _chat(fallback, temp), primary, fallback


@lru_cache(maxsize=64)
def load_prompt(name: str) -> tuple[str, str, str]:
    """Returns (version, system, user_template). Prompt files: front matter + '## system' + '## user'."""
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    version = re.search(r"^version:\s*(\S+)", raw, re.M)
    sys_part = raw.split("## system", 1)[1].split("## user", 1)[0].strip()
    user_part = raw.split("## user", 1)[1].strip()
    return (version.group(1) if version else "0"), sys_part, user_part


def render(template: str, variables: dict[str, Any]) -> str:
    def rep(m: re.Match) -> str:
        v = variables.get(m.group(1), "")
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", rep, template)


def _extract_json(text: str) -> Any:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth, end = 0, None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    in_str = esc = False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return json.loads(text[start:end])


FALLBACKS: dict[str, int] = {}  # node:primary->fallback -> count, reported by the eval runners


async def _invoke(node: str, messages: list[tuple[str, str]]) -> tuple[str, str]:
    primary, fallback, pname, fname = get_llm(node)
    for model, name in ((primary, pname), (fallback, fname)):
        t0 = time.perf_counter()
        try:
            msg = await model.ainvoke(messages)
        except Exception:  # noqa: BLE001 - fall back on any provider error (timeouts, 5xx, rate limits)
            led = ledger_var.get()
            if led:
                led.add(UsageRecord(node, name, 0, 0, 0.0, time.perf_counter() - t0, ok=False))
            if name == fname:
                raise
            FALLBACKS[f"{node}:{pname}->{fname}"] = FALLBACKS.get(f"{node}:{pname}->{fname}", 0) + 1
            continue
        um = getattr(msg, "usage_metadata", None) or {}
        tin, tout = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
        pr = _price(name)
        led = ledger_var.get()
        if led:
            led.add(UsageRecord(node, name, tin, tout, (tin * pr["in"] + tout * pr["out"]) / 1e6, time.perf_counter() - t0))
        return str(msg.content), name
    raise RuntimeError("unreachable")


def _fake() -> bool:
    return profile()["provider"] == "fake"


async def call_text(node: str, prompt: str, variables: dict[str, Any]) -> str:
    if _fake():
        from agent.fake_llm import respond

        return respond(prompt, variables)
    _, system, user = load_prompt(prompt)
    out, _ = await _invoke(node, [("system", system), ("user", render(user, variables))])
    return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()


async def call_json(node: str, prompt: str, variables: dict[str, Any], schema: type[T]) -> T:
    if _fake():
        from agent.fake_llm import respond

        return schema.model_validate(json.loads(respond(prompt, variables)))
    _, system, user = load_prompt(prompt)
    schema_hint = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    messages = [("system", system + "\n\nReturn ONLY one JSON object that validates against this JSON Schema:\n" + schema_hint),
                ("user", render(user, variables))]
    last_err = ""
    for _ in range(2):
        out, _ = await _invoke(node, messages if not last_err else messages + [("user", f"Your previous output was invalid: {last_err}. Return only the corrected JSON.")])
        try:
            return schema.model_validate(_extract_json(out))
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_err = str(e)[:400]
    raise ValueError(f"{node}: model did not return valid {schema.__name__}: {last_err}")
