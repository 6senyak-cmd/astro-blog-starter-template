"""
Hiring signals from public job boards.

Greenhouse, Lever, and Ashby all expose unauthenticated, read-only JSON
endpoints for any company with a public board. That is sanctioned access,
not scraping. LinkedIn is deliberately absent: its terms of service forbid
automated collection, so nothing here touches it.

Board tokens are guessed from company names. Guessing has two failure
modes -- a miss (no board found) and, worse, a *wrong hit* (someone else's
board under a similar token). Greenhouse and Ashby return the board's
display name, so hits are verified against the Form D entity name and
rejected unless they roughly match. Lever has no name field; Lever hits
are marked lower-trust.
"""

from __future__ import annotations

import json
import re

GREENHOUSE_BOARD = "https://boards-api.greenhouse.io/v1/boards/{t}"
GREENHOUSE_JOBS = "https://boards-api.greenhouse.io/v1/boards/{t}/jobs"
LEVER = "https://api.lever.co/v0/postings/{t}?mode=json"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{t}"

_SUFFIXES = r"\b(incorporated|corporation|holdings|technologies|technology|labs|inc|corp|llc|ltd|co)\b\.?"

ARR_PATTERN = re.compile(
    r"\$\s?(\d+(?:\.\d+)?)\s?(m|mm|million|b|billion)?\s+(?:in\s+)?"
    r"(?:arr|annual recurring revenue|revenue run.?rate)",
    re.IGNORECASE,
)


def token_variants(entity_name: str, limit: int = 3) -> list[str]:
    base = re.sub(_SUFFIXES, "", entity_name.lower())
    base = re.sub(r"[^a-z0-9 ]", "", base).strip()
    words = base.split()
    if not words:
        return []
    variants = ["".join(words), "-".join(words), words[0]]
    seen, out = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out[:limit]


def _name_matches(board_name: str, entity_name: str) -> bool:
    a = set(re.sub(_SUFFIXES, "", board_name.lower()).split())
    b = set(re.sub(_SUFFIXES, "", entity_name.lower()).split())
    a = {w for w in a if len(w) > 2}
    b = {w for w in b if len(w) > 2}
    return bool(a and b and (a & b))


def probe(session, entity_name: str, *, get, max_variants: int = 3) -> dict | None:
    """Try each provider with each token variant; return the first verified
    board with its postings, or None."""
    for token in token_variants(entity_name, max_variants):
        hit = _probe_greenhouse(session, token, entity_name, get)
        if hit:
            return hit
        hit = _probe_ashby(session, token, entity_name, get)
        if hit:
            return hit
        hit = _probe_lever(session, token, entity_name, get)
        if hit:
            return hit
    return None


def _probe_greenhouse(session, token, entity_name, get):
    resp = get(session, GREENHOUSE_BOARD.format(t=token))
    if resp is None:
        return None
    board_name = resp.json().get("name", "")
    if not _name_matches(board_name, entity_name):
        return None
    jobs_resp = get(session, GREENHOUSE_JOBS.format(t=token) + "?content=true")
    if jobs_resp is None:
        return None
    jobs = jobs_resp.json().get("jobs", [])
    return _result("greenhouse", token, f"https://boards.greenhouse.io/{token}",
                   [(j.get("title", ""), j.get("content", "")) for j in jobs], verified=True)


def _probe_ashby(session, token, entity_name, get):
    resp = get(session, ASHBY.format(t=token))
    if resp is None:
        return None
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return None
    jobs = data.get("jobs")
    if jobs is None:
        return None
    org = data.get("organizationName") or ""
    if org and not _name_matches(org, entity_name):
        return None
    return _result("ashby", token, f"https://jobs.ashbyhq.com/{token}",
                   [(j.get("title", ""), j.get("descriptionPlain", "") or "") for j in jobs],
                   verified=bool(org))


def _probe_lever(session, token, entity_name, get):
    resp = get(session, LEVER.format(t=token))
    if resp is None:
        return None
    try:
        postings = resp.json()
    except json.JSONDecodeError:
        return None
    if not isinstance(postings, list) or not postings:
        return None
    # Lever returns no company name to check the token against.
    return _result("lever", token, f"https://jobs.lever.co/{token}",
                   [(p.get("text", ""), p.get("descriptionPlain", "") or "") for p in postings],
                   verified=False)


def _result(provider, token, url, postings, *, verified):
    return {"provider": provider, "token": token, "board_url": url,
            "board_verified": verified, "postings": postings}


def summarize(hit: dict, commercial_keywords: list[str]) -> dict:
    """Reduce raw postings to the fields the pipeline stores."""
    titles = [t for t, _ in hit["postings"]]
    commercial = sum(
        1 for t in titles if any(k in t.lower() for k in commercial_keywords)
    )
    stated = None
    for title, body in hit["postings"]:
        m = ARR_PATTERN.search(f"{title} {body}")
        if m:
            amount, unit = float(m.group(1)), (m.group(2) or "").lower()
            multiplier = 1_000_000_000 if unit.startswith("b") else 1_000_000 if unit else 1
            stated = {"usd": int(amount * multiplier), "quote": m.group(0).strip()}
            break
    return {
        "board_provider": hit["provider"],
        "board_url": hit["board_url"],
        "board_verified": hit["board_verified"],
        "open_roles": len(titles),
        "commercial_roles": commercial,
        "stated_arr": stated,
        "sample_titles": titles[:15],
    }
