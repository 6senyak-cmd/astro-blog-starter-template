"""
ARR estimation, three methods, in strict order of trust.

disclosed  Form D Item 5 revenue range. Self-reported, but on a federal
           filing with liability attached. High confidence.
stated     A revenue figure found in the company's own job postings.
           Marketing copy; nobody audits it. Medium confidence.
proxy      Open roles -> implied headcount -> ARR-per-FTE benchmark.
           Two stacked assumptions produce a wide band. Low confidence,
           useful as a sort key and nothing else.

Whichever method fires, the basis -- the actual evidence string -- is kept
next to the number all the way into the workbook.
"""

from __future__ import annotations

# Form D Item 5 checkbox values, verbatim.
_DISCLOSED = {
    "No Revenues": ("$0 (disclosed: no revenues)", "pre-revenue per Form D Item 5"),
    "$1 - $1,000,000": ("$0–$1M (disclosed)", "Form D Item 5 revenue range $1 – $1,000,000"),
    "$1,000,001 - $5,000,000": ("$1M–$5M (disclosed)", "Form D Item 5 revenue range $1,000,001 – $5,000,000"),
    "$5,000,001 - $25,000,000": ("$5M–$25M (disclosed)", "Form D Item 5 revenue range $5,000,001 – $25,000,000"),
    "$25,000,001 - $100,000,000": ("$25M–$100M (disclosed)", "Form D Item 5 revenue range $25,000,001 – $100,000,000"),
    "Over $100,000,000": (">$100M (disclosed)", "Form D Item 5 revenue range over $100,000,000"),
}


def estimate(candidate: dict, model: dict) -> dict:
    revenue_range = candidate.get("revenue_range")
    if revenue_range in _DISCLOSED:
        band, basis = _DISCLOSED[revenue_range]
        return {"arr_band": band, "arr_method": "disclosed", "arr_confidence": "high",
                "arr_basis": basis}

    stated = candidate.get("stated_arr")
    if stated:
        return {
            "arr_band": f"~${stated['usd'] / 1e6:.1f}M (stated)",
            "arr_method": "stated",
            "arr_confidence": "medium",
            "arr_basis": f"company job posting states \"{stated['quote']}\" — unverified",
        }

    open_roles = candidate.get("open_roles")
    if open_roles:
        hc_low = open_roles / model["open_roles_pct_of_headcount_high"]
        hc_high = open_roles / model["open_roles_pct_of_headcount_low"]
        low = hc_low * model["arr_per_fte_low"]
        high = hc_high * model["arr_per_fte_high"]
        return {
            "arr_band": f"${low / 1e6:.1f}M–${high / 1e6:.1f}M (proxy)",
            "arr_method": "proxy",
            "arr_confidence": "low",
            "arr_basis": (
                f"{open_roles} open roles → implied headcount {hc_low:.0f}–{hc_high:.0f} "
                f"× ${model['arr_per_fte_low'] / 1e3:.0f}k–${model['arr_per_fte_high'] / 1e3:.0f}k ARR/FTE. "
                "Sort key, not a number."
            ),
        }

    return {"arr_band": "unknown", "arr_method": "none", "arr_confidence": "none",
            "arr_basis": "revenue not disclosed on Form D; no job board found for proxy"}
