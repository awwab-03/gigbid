"""Pricing Strategist: bid from market statistics, client budget and spend, and the user's floor;
decide whether the Connects cost is worth it (expected value)."""

from __future__ import annotations

from agent.handoffs import PriceQuote
from agent.mcp_client import ToolError
from agent.nodes._runtime import node, toolbox

USD_PER_CONNECT = 0.15  # Upwork's published price per Connect; GigSim mirrors it


def quote(job: dict, client: dict, stats: dict | None, profile: dict, fit: float, connects_cost: int,
          connects_multiplier: float = 1.0, connects_flat_fee: int = 0) -> PriceQuote:
    b = job.get("budget", {})
    btype = b.get("type", "fixed")
    floor = float(profile.get("hourly_floor", 20) if btype == "hourly" else profile.get("min_fixed", 150))
    target = float(profile.get("hourly_target", floor * 1.4)) if btype == "hourly" else None
    lo, hi = float(b.get("min") or 0), float(b.get("max") or 0)
    p25, p50, p75 = (stats or {}).get("p25"), (stats or {}).get("p50"), (stats or {}).get("p75")
    if btype == "hourly":
        amount = min(hi, max(floor, target or floor)) if hi else target or floor
    else:
        # fixed: aim at 85-95% of the client's ceiling, nudged by market median and client spend
        spend_factor = 0.95 if (client.get("total_spent_usd") or 0) > 5000 else 0.88
        amount = hi * spend_factor if hi else (p50 or floor)
        if p50 and hi and p50 < amount * 0.6:
            amount = max(floor, (amount + p50) / 2)
        amount = max(floor, min(amount, hi or amount))
    amount = round(amount, 0 if btype == "fixed" else 1)
    cost = int(round(connects_cost * connects_multiplier + connects_flat_fee))  # same formula as the platform (policy v2 fee)
    p_reply = 0.05 + 0.35 * fit + 0.1 * (client.get("hire_rate") or 0)
    job_value = amount * (40 if btype == "hourly" else 1)
    ev = p_reply * 0.35 * job_value - cost * USD_PER_CONNECT
    rationale = (f"{btype} bid {amount} vs client range {lo}-{hi}; your floor {floor}"
                 + (f"; market winning bids p25/p50/p75 {p25}/{p50}/{p75}" if p50 else "; no market statistics")
                 + f"; {cost} Connects (${cost * USD_PER_CONNECT:.2f}) vs expected value ${ev:.0f}")
    return PriceQuote(bid_type=btype, amount=amount, floor=floor, market_p25=p25, market_p50=p50, market_p75=p75,
                      client_budget_max=hi or None, connects_cost=cost, connects_worth_it=ev > 0, expected_value_usd=round(ev, 2),
                      rationale=rationale)


@node("pricing")
async def pricing(state: dict) -> dict:
    job = state["job"]
    tb = toolbox(state, "pricing")
    try:
        stats = await tb.call("marketplace.get_pricing_stats", {"category": job.get("category", "other"),
                                                                "budget_type": job.get("budget", {}).get("type", "fixed")})
    except ToolError:
        stats = None  # live mode has no market statistics
    policy = await tb.call("marketplace.get_policy", {})
    balance = await tb.call("marketplace.get_connects_balance", {})
    q = quote(job, state.get("client", {}), stats, state.get("profile", {}), state.get("fit_report", {}).get("score", 0.5),
              job.get("connects_cost", 0), float(policy.get("connects_multiplier", 1.0)), int(policy.get("connects_flat_fee", 0)))
    out = {"price": {**q.model_dump(), "connects_balance": balance["balance"], "policy_version": policy.get("version")},
           "_summary": q.rationale}
    if balance["balance"] < q.connects_cost:
        out.update(status="needs_attention", status_reason=f"not enough Connects ({balance['balance']} < {q.connects_cost})")
    return out
