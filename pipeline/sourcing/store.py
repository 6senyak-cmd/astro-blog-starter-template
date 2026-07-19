"""
State that survives between mornings.

Cloud sessions are ephemeral containers -- anything not committed to git is
gone by the next run. So state is plain JSONL, committed to the repo:
diffable, mergeable, and readable without tooling. One line per candidate,
keyed by Form D accession number.

`review.json` carries the batch cursor: which companies have already been
put in front of the analyst, so "continue" always surfaces 50 *new* ones.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "state"
CANDIDATES = STATE / "candidates.jsonl"
SNAPSHOTS = STATE / "snapshots.jsonl"
REVIEW = STATE / "review.json"


def load_candidates() -> dict[str, dict]:
    if not CANDIDATES.exists():
        return {}
    out = {}
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["accession"]] = row
    return out


def save_candidates(candidates: dict[str, dict]) -> None:
    STATE.mkdir(exist_ok=True)
    rows = sorted(candidates.values(), key=lambda r: r["accession"])
    CANDIDATES.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )


def upsert(candidates: dict[str, dict], row: dict) -> bool:
    """Insert a new candidate; returns False if already known."""
    if row["accession"] in candidates:
        return False
    row.setdefault("first_seen", date.today().isoformat())
    row.setdefault("status", "new")
    candidates[row["accession"]] = row
    return True


def load_rejected() -> set[str]:
    """Accessions already evaluated and filtered out, kept so discover
    never re-downloads them."""
    path = STATE / "rejected.txt"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def save_rejected(rejected: set[str]) -> None:
    STATE.mkdir(exist_ok=True)
    (STATE / "rejected.txt").write_text("\n".join(sorted(rejected)) + "\n", encoding="utf-8")


def load_review() -> dict:
    if REVIEW.exists():
        return json.loads(REVIEW.read_text(encoding="utf-8"))
    return {"shown": [], "batches": []}


def save_review(review: dict) -> None:
    STATE.mkdir(exist_ok=True)
    REVIEW.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")


def append_snapshot(accession: str, open_roles: int) -> None:
    """One line per (company, day): the raw material for the growth signal.
    Velocity needs two snapshots, so run 1 reports no growth flags."""
    STATE.mkdir(exist_ok=True)
    with SNAPSHOTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"accession": accession, "date": date.today().isoformat(),
                            "open_roles": open_roles}) + "\n")


def growth_flag(accession: str, current_roles: int) -> str | None:
    """Compare today's open-role count with the earliest prior snapshot."""
    if not SNAPSHOTS.exists():
        return None
    prior = None
    today = date.today().isoformat()
    for line in SNAPSHOTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        snap = json.loads(line)
        if snap["accession"] == accession and snap["date"] != today:
            if prior is None or snap["date"] < prior["date"]:
                prior = snap
    if prior is None:
        return None
    delta = current_roles - prior["open_roles"]
    if delta > 0:
        return f"+{delta} roles since {prior['date']}"
    if delta < 0:
        return f"{delta} roles since {prior['date']}"
    return f"flat since {prior['date']}"
