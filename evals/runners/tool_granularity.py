"""R&D question A: does tool granularity change agent behaviour?

40 freelancer-assistant tasks with a known correct first call, offered to the model with four tool surfaces:
  fine      ~36 narrow tools (one per entity/filter, single-item verification)
  coarse    3 tools (portfolio / marketplace / workspace) with an `action` enum
  ours      GigBid's real MCP tools (schemas read from the servers), original descriptions
  ours_rw   the same tools with rewritten descriptions ("use for ... / not for ...")
Scored on the FIRST tool call: tool-selection accuracy, argument accuracy (key arguments only; free-text queries
must contain the gold keywords), and prompt + completion tokens per task (from the API's usage field).

  python -m evals.runners.tool_granularity --models gpt-oss-120b qwen-3.8-27b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

os.environ.setdefault("MCP_TRANSPORT", "inproc")
ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
SYSTEM = ("You are the tool-using assistant inside GigBid, a freelancer copilot. For the user's request, call exactly ONE tool "
          "that best serves it, with precise arguments. Do not answer in text.")

# ---------------------------------------------------------------- tasks: (text, ours, fine, coarse)
# each gold is (tool, {key args}); string args ending in "~" mean "must contain these words" (case-insensitive)
S = lambda q: q + "~"  # noqa: E731
TASKS = [
    ("Do I have anything showing I've built RAG pipelines?", ("portfolio__search_evidence", {"requirement": S("RAG")}),
     ("search_all_evidence", {"query": S("RAG")}), ("portfolio", {"action": "search", "query": S("RAG")})),
    ("Find evidence that I know Kubernetes.", ("portfolio__search_evidence", {"requirement": S("Kubernetes")}),
     ("search_all_evidence", {"query": S("Kubernetes")}), ("portfolio", {"action": "search", "query": S("Kubernetes")})),
    ("What proof do I have of PyTorch model training?", ("portfolio__search_evidence", {"requirement": S("PyTorch")}),
     ("search_all_evidence", {"query": S("PyTorch")}), ("portfolio", {"action": "search", "query": S("PyTorch")})),
    ("Did any client review mention my communication?", ("portfolio__search_evidence", {"requirement": S("communication"), "types": ["review"]}),
     ("search_reviews", {"query": S("communication")}), ("portfolio", {"action": "search", "query": S("communication"), "types": ["review"]})),
    ("Show me code I've written for FastAPI services.", ("portfolio__search_evidence", {"requirement": S("FastAPI"), "types": ["code"]}),
     ("search_code", {"query": S("FastAPI")}), ("portfolio", {"action": "search", "query": S("FastAPI"), "types": ["code"]})),
    ("Which of my past winning proposals talked about dashboards?",
     ("portfolio__search_evidence", {"requirement": S("dashboard"), "types": ["proposal"], "outcome": "won"}),
     ("search_past_proposals", {"query": S("dashboard"), "outcome": "won"}),
     ("portfolio", {"action": "search", "query": S("dashboard"), "types": ["proposal"], "outcome": "won"})),
    ("Open the full case study for project ml-03.", ("portfolio__get_case_study", {"project_id": "ml-03"}),
     ("get_case_study", {"project_id": "ml-03"}), ("portfolio", {"action": "case_study", "id": "ml-03"})),
    ("I need the details of project fs-07.", ("portfolio__get_case_study", {"project_id": "fs-07"}),
     ("get_case_study", {"project_id": "fs-07"}), ("portfolio", {"action": "case_study", "id": "fs-07"})),
    ("Pull up case study da-11 so I can quote it.", ("portfolio__get_case_study", {"project_id": "da-11"}),
     ("get_case_study", {"project_id": "da-11"}), ("portfolio", {"action": "case_study", "id": "da-11"})),
    ("What skills does my portfolio actually prove?", ("portfolio__list_skills", {}), ("list_skills", {}), ("portfolio", {"action": "skills"})),
    ("List every skill I can back up with a project.", ("portfolio__list_skills", {}), ("list_skills", {}), ("portfolio", {"action": "skills"})),
    ("Show me past proposal p-ml-012 and how it went.", ("portfolio__get_proposal", {"proposal_id": "p-ml-012"}),
     ("get_past_proposal", {"proposal_id": "p-ml-012"}), ("portfolio", {"action": "proposal", "id": "p-ml-012"})),
    ("Fetch my old proposal p-da-004.", ("portfolio__get_proposal", {"proposal_id": "p-da-004"}),
     ("get_past_proposal", {"proposal_id": "p-da-004"}), ("portfolio", {"action": "proposal", "id": "p-da-004"})),
    ("For a job needing Python, SQL and Airflow, which requirements can I support with evidence?",
     ("portfolio__match_requirements", {"requirements": ["Python", "SQL", "Airflow"]}),
     ("check_requirement", {"requirement": ["Python", "SQL", "Airflow"]}),
     ("portfolio", {"action": "match", "items": ["Python", "SQL", "Airflow"]})),
    ("Build an evidence matrix for: React, TypeScript, Stripe.", ("portfolio__match_requirements", {"requirements": ["React", "TypeScript", "Stripe"]}),
     ("check_requirement", {"requirement": ["React", "TypeScript", "Stripe"]}),
     ("portfolio", {"action": "match", "items": ["React", "TypeScript", "Stripe"]})),
    ("Check my coverage of these requirements: LLM fine-tuning, vLLM serving, evaluation harness.",
     ("portfolio__match_requirements", {"requirements": ["LLM fine-tuning", "vLLM serving", "evaluation harness"]}),
     ("check_requirement", {"requirement": ["LLM fine-tuning", "vLLM serving", "evaluation harness"]}),
     ("portfolio", {"action": "match", "items": ["LLM fine-tuning", "vLLM serving", "evaluation harness"]})),
    ("Fact-check this draft before I send it: 'I cut inference latency by 40% and built a RAG system for a bank.'",
     ("portfolio__verify_claims", {"text": S("latency")}), ("verify_claim", {"claim": S("latency")}),
     ("portfolio", {"action": "verify", "text": S("latency")})),
    ("Are the claims in this paragraph supported by my portfolio? 'I have shipped 12 Shopify stores and led a team of 5.'",
     ("portfolio__verify_claims", {"text": S("Shopify")}), ("verify_claim", {"claim": S("Shopify")}),
     ("portfolio", {"action": "verify", "text": S("Shopify")})),
    ("Verify: 'My dashboards reduced reporting time from 3 days to 2 hours for a retail chain.'",
     ("portfolio__verify_claims", {"text": S("dashboards")}), ("verify_claim", {"claim": S("dashboards")}),
     ("portfolio", {"action": "verify", "text": S("dashboards")})),
    ("Find open jobs about computer vision.", ("marketplace__search_jobs", {"query": S("computer vision")}),
     ("search_jobs_by_keyword", {"query": S("computer vision")}), ("marketplace", {"action": "search_jobs", "query": S("computer vision")})),
    ("Show me the newest web development jobs.", ("marketplace__search_jobs", {"category": "web_dev"}),
     ("filter_jobs_by_category", {"category": "web_dev"}), ("marketplace", {"action": "search_jobs", "category": "web_dev"})),
    ("Any hourly jobs out there right now?", ("marketplace__search_jobs", {"budget_type": "hourly"}),
     ("filter_jobs_by_budget_type", {"budget_type": "hourly"}), ("marketplace", {"action": "search_jobs", "budget_type": "hourly"})),
    ("Open job j-00123.", ("marketplace__get_job", {"job_id": "j-00123"}), ("get_job_details", {"job_id": "j-00123"}),
     ("marketplace", {"action": "job", "id": "j-00123"})),
    ("What exactly does job j-00456 ask for?", ("marketplace__get_job", {"job_id": "j-00456"}), ("get_job_details", {"job_id": "j-00456"}),
     ("marketplace", {"action": "job", "id": "j-00456"})),
    ("Is client cl-0358 payment verified, and do they hire?", ("marketplace__get_client_history", {"client_id": "cl-0358"}),
     ("get_client_payment_verification", {"client_id": "cl-0358"}), ("marketplace", {"action": "client", "id": "cl-0358"})),
    ("How much has client cl-0102 spent on the platform?", ("marketplace__get_client_history", {"client_id": "cl-0102"}),
     ("get_client_spend", {"client_id": "cl-0102"}), ("marketplace", {"action": "client", "id": "cl-0102"})),
    ("What rating do freelancers give client cl-0777?", ("marketplace__get_client_history", {"client_id": "cl-0777"}),
     ("get_client_rating", {"client_id": "cl-0777"}), ("marketplace", {"action": "client", "id": "cl-0777"})),
    ("How many Connects do I have left?", ("marketplace__get_connects_balance", {}), ("get_connects_balance", {}),
     ("marketplace", {"action": "connects"})),
    ("What do winning bids look like for data analytics jobs?", ("marketplace__get_pricing_stats", {"category": "data_analytics"}),
     ("get_pricing_percentiles", {"category": "data_analytics"}), ("marketplace", {"action": "pricing", "category": "data_analytics"})),
    ("Typical winning price for AI/ML projects?", ("marketplace__get_pricing_stats", {"category": "ai_ml"}),
     ("get_pricing_percentiles", {"category": "ai_ml"}), ("marketplace", {"action": "pricing", "category": "ai_ml"})),
    ("What are the current platform rules on submissions and Connects?", ("marketplace__get_policy", {}), ("get_platform_rules", {}),
     ("marketplace", {"action": "policy"})),
    ("Read the conversation in thread t-0042.", ("marketplace__list_messages", {"thread_id": "t-0042"}),
     ("get_thread_messages", {"thread_id": "t-0042"}), ("marketplace", {"action": "messages", "id": "t-0042"})),
    ("What did the client say in thread t-0107?", ("marketplace__list_messages", {"thread_id": "t-0107"}),
     ("get_thread_messages", {"thread_id": "t-0107"}), ("marketplace", {"action": "messages", "id": "t-0107"})),
    ("Which of my proposals got a reply?", ("marketplace__list_proposals", {"status": "replied"}), ("list_replied_proposals", {}),
     ("marketplace", {"action": "proposals", "status": "replied"})),
    ("Show proposals that turned into interviews.", ("marketplace__list_proposals", {"status": "interview"}), ("list_interview_proposals", {}),
     ("marketplace", {"action": "proposals", "status": "interview"})),
    ("Save a draft (do not send) for job j-00050: fixed bid of 650 with the cover letter 'Hi, I built a Redis cache layer...'",
     ("marketplace__create_proposal_draft", {"job_id": "j-00050", "bid_amount": 650}),
     ("create_draft", {"job_id": "j-00050", "bid_amount": 650}), ("marketplace", {"action": "draft", "id": "j-00050", "amount": 650})),
    ("When am I free for a 30-minute interview this week?", ("workspace__free_slots", {"duration_min": 30}),
     ("free_slots_this_week", {}), ("workspace", {"action": "free_slots", "duration_min": 30})),
    ("Find free slots over the next 3 days.", ("workspace__free_slots", {"days": 3}), ("free_slots_next_n_days", {"days": 3}),
     ("workspace", {"action": "free_slots", "days": 3})),
    ("Hold 2026-11-14T15:00 for 45 minutes for an interview with Acme.", ("workspace__create_interview_hold", {"start": S("2026-11-14T15:00"), "duration_min": 45}),
     ("hold_calendar_slot", {"start": S("2026-11-14T15:00"), "duration_min": 45}),
     ("workspace", {"action": "hold", "start": S("2026-11-14T15:00"), "duration_min": 45})),
    ("Draft an email to sara@acme.test with subject 'Interview times' proposing two slots.",
     ("workspace__create_email_draft", {"to": "sara@acme.test", "subject": S("Interview")}),
     ("draft_email", {"to": "sara@acme.test", "subject": S("Interview")}),
     ("workspace", {"action": "email_draft", "to": "sara@acme.test", "subject": S("Interview")})),
]
assert len(TASKS) == 40, len(TASKS)

# ---------------------------------------------------------------- tool surfaces
def fn(name: str, desc: str, props: dict | None = None, required: list | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


STR, INT, NUM = {"type": "string"}, {"type": "integer"}, {"type": "number"}
LIST = {"type": "array", "items": {"type": "string"}}


def fine_tools() -> list[dict]:
    q = {"query": STR}
    tools = [fn(n, d, q, ["query"]) for n, d in [
        ("search_all_evidence", "Search all portfolio evidence."), ("search_case_studies", "Search case studies."),
        ("search_code", "Search code files in my repos."), ("search_readmes", "Search repo READMEs."),
        ("search_reviews", "Search client reviews."), ("search_cv", "Search my CV.")]]
    tools += [fn("search_past_proposals", "Search my past proposals.", {"query": STR, "outcome": {"type": "string", "enum": ["won", "replied", "ignored"]}}, ["query"]),
              fn("get_case_study", "Get a case study.", {"project_id": STR}, ["project_id"]),
              fn("get_project_skills", "Skills of one project.", {"project_id": STR}, ["project_id"]),
              fn("list_skills", "List skills."), fn("get_past_proposal", "Get a past proposal.", {"proposal_id": STR}, ["proposal_id"]),
              fn("check_requirement", "Check one requirement against my portfolio.", {"requirement": STR}, ["requirement"]),
              fn("verify_claim", "Verify one claim.", {"claim": STR}, ["claim"]),
              fn("search_jobs_by_keyword", "Search jobs by keyword.", q, ["query"]),
              fn("filter_jobs_by_category", "Jobs in a category.", {"category": {"type": "string", "enum": ["ai_ml", "data_science", "web_dev", "ecommerce", "data_analytics", "other"]}}, ["category"]),
              fn("filter_jobs_by_budget_type", "Jobs by budget type.", {"budget_type": {"type": "string", "enum": ["fixed", "hourly"]}}, ["budget_type"]),
              fn("get_job_details", "Get a job.", {"job_id": STR}, ["job_id"]), fn("get_job_budget", "Budget of a job.", {"job_id": STR}, ["job_id"]),
              fn("get_job_client", "Client of a job.", {"job_id": STR}, ["job_id"])]
    tools += [fn(n, d, {"client_id": STR}, ["client_id"]) for n, d in [
        ("get_client_payment_verification", "Client payment verification."), ("get_client_rating", "Client rating."),
        ("get_client_spend", "Client total spend."), ("get_client_hires", "Client hires.")]]
    tools += [fn("get_connects_balance", "Connects balance."), fn("get_connects_spend", "Connects spent."),
              fn("get_pricing_percentiles", "Winning-bid percentiles.", {"category": STR}, ["category"]),
              fn("get_connects_pricing", "Connects price per proposal."), fn("get_submission_limits", "Submission limits."),
              fn("get_platform_rules", "Platform rules."), fn("list_threads", "Message threads."),
              fn("get_thread_messages", "Messages in a thread.", {"thread_id": STR}, ["thread_id"])]
    tools += [fn(f"list_{s}_proposals", f"Proposals with status {s}.") for s in ("draft", "submitted", "replied", "interview", "hired", "lost")]
    tools += [fn("create_draft", "Create a proposal draft.", {"job_id": STR, "cover_letter": STR, "bid_amount": NUM, "bid_type": STR}, ["job_id", "bid_amount"]),
              fn("free_slots_this_week", "Free slots this week."), fn("free_slots_next_n_days", "Free slots in the next n days.", {"days": INT}, ["days"]),
              fn("hold_calendar_slot", "Hold a calendar slot.", {"start": STR, "duration_min": INT}, ["start", "duration_min"]),
              fn("draft_email", "Draft an email.", {"to": STR, "subject": STR, "body": STR}, ["to", "subject"])]
    return tools


def coarse_tools() -> list[dict]:
    return [
        fn("portfolio", "Everything about my portfolio.", {"action": {"type": "string", "enum": ["search", "case_study", "skills", "proposal", "match", "verify"]},
           "query": STR, "id": STR, "items": LIST, "text": STR, "types": LIST, "outcome": STR}, ["action"]),
        fn("marketplace", "Everything on the marketplace.", {"action": {"type": "string", "enum": ["search_jobs", "job", "client", "connects", "pricing", "policy",
           "threads", "messages", "proposals", "draft"]}, "query": STR, "id": STR, "category": STR, "budget_type": STR, "status": STR,
           "amount": NUM, "text": STR}, ["action"]),
        fn("workspace", "Calendar and email.", {"action": {"type": "string", "enum": ["free_slots", "hold", "email_draft"]}, "days": INT,
           "duration_min": INT, "start": STR, "to": STR, "subject": STR, "body": STR}, ["action"]),
    ]


REWRITTEN = {
    "portfolio__search_evidence": "Search my portfolio for proof of ONE skill or requirement. Use `types` to restrict to reviews, code, past proposals etc., and `outcome` for past proposals that were won/replied/ignored. Not for several requirements at once (use match_requirements) or for checking a draft (use verify_claims).",
    "portfolio__get_case_study": "Return the full case study for a project id such as ml-03, fs-07, da-11. Use when the user names a project id.",
    "portfolio__list_skills": "List every skill my portfolio proves and which projects prove it. Takes no arguments.",
    "portfolio__get_proposal": "Return one past proposal by id (e.g. p-ml-012) with its outcome. Use when the user names a proposal id.",
    "portfolio__match_requirements": "Given a LIST of job requirements, say which are supported by evidence (a requirement-to-evidence matrix). Use whenever there are two or more requirements.",
    "portfolio__verify_claims": "Fact-check a drafted text: splits it into claims and labels each supported/partly/unsupported against my portfolio. Pass the whole draft as `text`.",
    "marketplace__search_jobs": "Find open job posts. Use `query` for topics, `category` (ai_ml, data_science, web_dev, ecommerce, data_analytics, other) and `budget_type` (fixed/hourly) to filter.",
    "marketplace__get_job": "Return one job post by id such as j-00123.",
    "marketplace__get_client_history": "Everything about a client id such as cl-0358: payment verification, total spend, hires, ratings, disputes.",
    "marketplace__get_connects_balance": "My Connects balance and spend. No arguments.",
    "marketplace__get_pricing_stats": "Winning-bid percentiles for a job category (ai_ml, data_science, web_dev, ecommerce, data_analytics, other).",
    "marketplace__get_policy": "Current platform policy: Connects prices, submission limits and rules. No arguments.",
    "marketplace__list_threads": "List my client conversation threads (no message bodies).",
    "marketplace__list_messages": "Read all messages in one client thread by id such as t-0042.",
    "marketplace__list_proposals": "My proposals, optionally filtered by `status` (draft, submitted, viewed, replied, interview, hired, lost).",
    "marketplace__get_events": "Marketplace events after since_id (viewed, replied, hired, new messages). For sync jobs, not user questions.",
    "marketplace__create_proposal_draft": "Save a proposal DRAFT for a job; nothing is sent. Needs job_id, cover_letter, bid_amount, bid_type and an idempotency_key.",
    "marketplace__submit_proposal": "Submit an already-approved draft; spends Connects. Only after explicit human approval.",
    "marketplace__send_message": "Send a reply in a thread. Only after explicit human approval.",
    "workspace__free_slots": "Free interview slots in my working hours. `days` = how many days ahead, `duration_min` = slot length.",
    "workspace__create_interview_hold": "Block a tentative calendar slot at `start` (ISO time) for `duration_min` minutes. Sends no invite.",
    "workspace__create_email_draft": "Save an email draft (to, subject, body). Never sends.",
}


async def ours_tools(rewritten: bool) -> list[dict]:
    from mcp_servers.marketplace.server import mcp as M
    from mcp_servers.portfolio.server import mcp as P
    from mcp_servers.workspace.server import mcp as W

    out = []
    for server, s in (("portfolio", P), ("marketplace", M), ("workspace", W)):
        for t in await s.list_tools():
            name = f"{server}__{t.name}"
            out.append({"type": "function", "function": {"name": name, "description": REWRITTEN[name] if rewritten else (t.description or ""),
                                                         "parameters": t.inputSchema}})
    return out


# ---------------------------------------------------------------- scoring
def arg_ok(gold: dict, got: dict) -> bool:
    for k, v in gold.items():
        g = got.get(k)
        if isinstance(v, str) and v.endswith("~"):
            if not isinstance(g, str) or not all(w.lower() in g.lower() for w in v[:-1].split()):
                return False
        elif isinstance(v, list):
            if isinstance(g, str):  # fine-grained single-item tools: one correct item counts as a correct first call
                if g.lower() not in [x.lower() for x in v]:
                    return False
            elif not isinstance(g, list) or sorted(x.lower() for x in g) != sorted(x.lower() for x in v):
                return False
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            try:
                if float(g) != float(v):
                    return False
            except (TypeError, ValueError):
                return False
        elif str(g).lower() != str(v).lower():
            return False
    return True


_PACE = {k: float(v) for k, v in (x.split("=") for x in os.getenv("LLM_PACE", "").split(",") if "=" in x)}  # requests/minute
_LAST: dict[str, float] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


async def _pace(model: str) -> None:
    if model not in _PACE:
        return
    lock = _LOCKS.setdefault(model, asyncio.Lock())
    async with lock:
        wait = _LAST.get(model, 0) + 60 / _PACE[model] - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST[model] = time.monotonic()


async def call(client: httpx.AsyncClient, model: str, tools: list[dict], task: str) -> dict:
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}],
            "tools": tools, "tool_choice": "auto", "temperature": 0}
    for attempt in range(12):  # free tier: gpt-oss-120b allows 5 requests/minute, so wait out 429s instead of scoring them
        await _pace(model)
        r = await client.post("/chat/completions", json=body)
        if r.status_code == 429 or r.status_code >= 500:
            await asyncio.sleep(13 * (attempt + 1))
            continue
        r.raise_for_status()
        d = r.json()
        msg = d["choices"][0]["message"]
        tc = (msg.get("tool_calls") or [None])[0]
        args = {}
        if tc:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_unparsable": tc["function"].get("arguments")}
        u = d.get("usage", {})
        return {"tool": tc["function"]["name"] if tc else None, "args": args,
                "tokens": int(u.get("prompt_tokens", 0)) + int(u.get("completion_tokens", 0)), "prompt_tokens": int(u.get("prompt_tokens", 0))}
    return {"tool": None, "args": {}, "tokens": 0, "prompt_tokens": 0, "error": "rate limited"}


async def run(models: list[str], concurrency: int) -> dict:
    surfaces = {"fine": fine_tools(), "coarse": coarse_tools(), "ours": await ours_tools(False), "ours_rw": await ours_tools(True)}
    gold_idx = {"ours": 1, "ours_rw": 1, "fine": 2, "coarse": 3}
    sem = asyncio.Semaphore(concurrency)
    rows = []
    async with httpx.AsyncClient(base_url=os.environ["OPEN_LLM_BASE_URL"], timeout=90,
                                 headers={"Authorization": f"Bearer {os.environ['OPEN_LLM_API_KEY']}"}) as client:
        async def one(model: str, sname: str, i: int):
            task = TASKS[i]
            gtool, gargs = task[gold_idx[sname]]
            async with sem:
                t = time.perf_counter()
                got = await call(client, model, surfaces[sname], task[0])
            sel = got["tool"] == gtool
            rows.append({"model": model, "surface": sname, "task": i, "gold_tool": gtool, "tool": got["tool"], "tool_ok": sel,
                         "args_ok": sel and arg_ok(gargs, got["args"]), "tokens": got["tokens"], "prompt_tokens": got["prompt_tokens"],
                         "latency_s": round(time.perf_counter() - t, 2), "args": got["args"]})
        await asyncio.gather(*(one(m, s, i) for m in models for s in surfaces for i in range(len(TASKS))))
    summary = {}
    for m in models:
        for s in surfaces:
            rs = [r for r in rows if r["model"] == m and r["surface"] == s]
            summary[f"{m}|{s}"] = {"n_tools": len(surfaces[s]), "tool_selection_acc": round(sum(r["tool_ok"] for r in rs) / len(rs), 3),
                                   "argument_acc": round(sum(r["args_ok"] for r in rs) / len(rs), 3),
                                   "tokens_per_task": round(sum(r["tokens"] for r in rs) / len(rs), 1),
                                   "no_tool_call": sum(r["tool"] is None for r in rs)}
    return {"summary": summary, "rows": sorted(rows, key=lambda r: (r["model"], r["surface"], r["task"]))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gpt-oss-120b", "qwen-3.8-27b"])
    ap.add_argument("--concurrency", type=int, default=3)
    a = ap.parse_args()
    res = asyncio.run(run(a.models, a.concurrency))
    (RES / "tool_granularity.json").write_text(json.dumps({"n_tasks": len(TASKS), "summary": res["summary"]}, indent=2), encoding="utf-8")
    (RES / "tool_granularity_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in res["rows"]), encoding="utf-8")
    for k, v in res["summary"].items():
        print(f"[{k}] {v}", flush=True)


if __name__ == "__main__":
    main()
