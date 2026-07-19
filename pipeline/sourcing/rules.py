"""
Deterministic filter and pre-score.

The rules decide who gets *into* the pipeline; the qualitative fit score
(assigned by Claude in-session, 50 companies at a time) decides who rises
to the top of the workbook. Rules are cheap and run on every filing;
judgment is expensive and runs only on survivors.
"""

from __future__ import annotations


def disqualify(candidate: dict, discovery_cfg: dict) -> list[str]:
    """Hard reasons a Form D filer is out of scope. Empty list = in."""
    reasons = []

    exemptions = candidate.get("federal_exemptions") or []
    prefix = discovery_cfg["fund_exemption_prefix"]
    if any(e.startswith(prefix) for e in exemptions):
        reasons.append("investment fund (3C exemption)")

    industry = candidate.get("industry")
    if industry == "Pooled Investment Fund":
        reasons.append("pooled investment fund")
    elif industry not in discovery_cfg["industry_include"]:
        reasons.append(f"industry out of scope ({industry})")

    sold = candidate.get("total_sold_usd")
    if sold is None or sold == 0:
        reasons.append("no amount sold reported")
    elif sold < discovery_cfg["min_amount_sold_usd"]:
        reasons.append(f"raise too small (${sold:,.0f})")
    elif sold > discovery_cfg["max_amount_sold_usd"]:
        reasons.append(f"raise too large (${sold:,.0f})")

    if candidate.get("is_equity") is False:
        reasons.append("non-equity offering")

    if candidate.get("state") and len(candidate["state"]) != 2:
        reasons.append(f"non-US issuer ({candidate['state']})")

    return reasons


def prescore(candidate: dict) -> float:
    """Deterministic ordering for who gets scored first. Not the fit score —
    just a queue priority. Higher = sooner."""
    score = 0.0
    if candidate.get("arr_confidence") == "high":
        score += 3
    elif candidate.get("arr_confidence") == "medium":
        score += 2
    elif candidate.get("arr_confidence") == "low":
        score += 1
    if candidate.get("board_verified"):
        score += 1.5
    if (candidate.get("commercial_roles") or 0) > 0:
        score += 1.5
    if candidate.get("industry") in ("Other Technology", "Computers"):
        score += 1
    filed = candidate.get("date_filed") or ""
    if filed >= "2026-04":
        score += 1
    return score
