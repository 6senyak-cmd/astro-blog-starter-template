"""
Orchestrator. The morning loop is four commands:

    discover        pull new Form Ds from EDGAR, filter, add to state
    enrich          probe job boards for candidates that lack hiring data
    batch           select the next 50 unshown candidates -> out/to_score.json
    ingest-scores   merge Claude's in-session scores back into state
    export          write the two-sheet workbook
    status          counts, so you can see where the funnel stands

Run from the pipeline/ directory:  python -m sourcing.cli <command>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

from . import arr, edgar, jobs, rules, store
from .http import get, make_session

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def cmd_discover(args) -> None:
    cfg = load_cfg()
    dcfg = cfg["discovery"]
    session = make_session(cfg)
    candidates = store.load_candidates()
    rejected = store.load_rejected()
    added = skipped = 0

    for year, q in edgar.quarters_back(dcfg["quarters_back"]):
        index = edgar.fetch_index(session, year, q, get=get)
        entries = edgar.form_d_entries(index, include_amendments=dcfg["include_amendments"])
        print(f"{year} Q{q}: {len(entries)} Form D filings in index")
        for entry in entries:
            accession = edgar.accession_of(entry)
            if accession is None:
                continue
            if accession in candidates or accession in rejected:
                skipped += 1
                continue
            parsed = edgar.fetch_form_d(session, entry, get=get)
            if parsed is None:
                continue
            reasons = rules.disqualify(parsed, dcfg)
            if reasons:
                rejected.add(parsed["accession"])
                continue
            parsed["disqualifiers"] = []
            store.upsert(candidates, parsed)
            added += 1
            if args.limit and added >= args.limit:
                break
        if args.limit and added >= args.limit:
            break

    store.save_candidates(candidates)
    store.save_rejected(rejected)
    print(f"added {added} new candidates ({skipped} already known); total {len(candidates)}")


def cmd_enrich(args) -> None:
    cfg = load_cfg()
    jcfg = cfg["jobs"]
    session = make_session(cfg)
    candidates = store.load_candidates()
    today = date.today().isoformat()
    probed = 0

    for row in candidates.values():
        if probed >= args.limit:
            break
        last = row.get("board_probed")
        if last and (date.fromisoformat(today) - date.fromisoformat(last)).days < jcfg["probe_ttl_days"]:
            continue
        hit = jobs.probe(session, row["entity_name"], get=get,
                         max_variants=jcfg["max_probe_variants"])
        row["board_probed"] = today
        probed += 1
        if hit:
            summary = jobs.summarize(hit, jcfg["commercial_title_keywords"])
            row.update(summary)
            store.append_snapshot(row["accession"], summary["open_roles"])
            row["growth_flag"] = store.growth_flag(row["accession"], summary["open_roles"])
        row.update(arr.estimate(row, cfg["arr_model"]))

    # Candidates never probed still need an ARR verdict (usually "unknown"
    # or "disclosed" straight off the filing).
    for row in candidates.values():
        if "arr_band" not in row:
            row.update(arr.estimate(row, cfg["arr_model"]))

    store.save_candidates(candidates)
    found = sum(1 for r in candidates.values() if r.get("board_url"))
    print(f"probed {probed} companies; {found}/{len(candidates)} have a job board")


def cmd_batch(args) -> None:
    cfg = load_cfg()
    candidates = store.load_candidates()
    review = store.load_review()
    shown = set(review["shown"])

    pending = [r for r in candidates.values() if r["accession"] not in shown]
    pending.sort(key=rules.prescore, reverse=True)
    batch = pending[:args.size]
    if not batch:
        print("no unshown candidates left — run discover to widen the net")
        sys.exit(1)

    OUT.mkdir(exist_ok=True)
    payload = [
        {k: r.get(k) for k in (
            "accession", "entity_name", "city", "state", "year_incorporated",
            "industry", "total_sold_usd", "revenue_range", "officers",
            "date_filed", "date_of_first_sale", "arr_band", "arr_method",
            "arr_confidence", "arr_basis", "open_roles", "commercial_roles",
            "sample_titles", "board_url", "board_verified", "growth_flag",
        )}
        for r in batch
    ]
    (OUT / "to_score.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print(f"wrote {len(batch)} candidates to out/to_score.json "
          f"({len(pending) - len(batch)} remain in queue)")


def cmd_ingest_scores(args) -> None:
    """Scores file: [{accession, fit_score, founder_led, founder_evidence,
    business_model, rationale, disqualifiers}]"""
    candidates = store.load_candidates()
    review = store.load_review()
    scores = json.loads(Path(args.file).read_text(encoding="utf-8"))
    merged = 0
    for s in scores:
        row = candidates.get(s["accession"])
        if row is None:
            continue
        row.update({k: s.get(k) for k in (
            "fit_score", "founder_led", "founder_evidence",
            "business_model", "rationale", "disqualifiers",
        )})
        row["status"] = "shown"
        if s["accession"] not in review["shown"]:
            review["shown"].append(s["accession"])
        merged += 1
    review["batches"].append({"date": date.today().isoformat(), "count": merged})
    store.save_candidates(candidates)
    store.save_review(review)
    print(f"merged {merged} scores; {len(review['shown'])} companies shown to date")


def cmd_export(args) -> None:
    cfg = load_cfg()
    candidates = store.load_candidates()
    rows = [r for r in candidates.values() if r.get("status") == "shown"]
    if args.latest_batch:
        review = store.load_review()
        last_n = review["batches"][-1]["count"] if review["batches"] else 0
        rows = [candidates[a] for a in review["shown"][-last_n:] if a in candidates]
    OUT.mkdir(exist_ok=True)
    path = args.out or str(OUT / f"pipeline_{date.today().isoformat()}.xlsx")
    from . import excel
    excel.write(rows, cfg, path)
    print(f"wrote {len(rows)} companies to {path}")


def cmd_status(args) -> None:
    candidates = store.load_candidates()
    review = store.load_review()
    shown = set(review["shown"])
    print(f"candidates:  {len(candidates)}")
    print(f"shown:       {len(shown)}")
    print(f"in queue:    {len([r for r in candidates.values() if r['accession'] not in shown])}")
    print(f"with board:  {len([r for r in candidates.values() if r.get('board_url')])}")
    for method in ("disclosed", "stated", "proxy", "none"):
        n = len([r for r in candidates.values() if r.get("arr_method") == method])
        print(f"arr {method:<10} {n}")


def main() -> None:
    p = argparse.ArgumentParser(prog="sourcing")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="pull new Form Ds from EDGAR")
    d.add_argument("--limit", type=int, default=0, help="stop after N new candidates (0 = no cap)")
    d.set_defaults(fn=cmd_discover)

    e = sub.add_parser("enrich", help="probe job boards for hiring signals")
    e.add_argument("--limit", type=int, default=200, help="max companies to probe this run")
    e.set_defaults(fn=cmd_enrich)

    b = sub.add_parser("batch", help="select next unshown candidates for scoring")
    b.add_argument("--size", type=int, default=50)
    b.set_defaults(fn=cmd_batch)

    i = sub.add_parser("ingest-scores", help="merge in-session scores into state")
    i.add_argument("file", nargs="?", default=str(OUT / "scores.json"))
    i.set_defaults(fn=cmd_ingest_scores)

    x = sub.add_parser("export", help="write the two-sheet workbook")
    x.add_argument("--out", default=None)
    x.add_argument("--latest-batch", action="store_true", help="only the most recent batch")
    x.set_defaults(fn=cmd_export)

    s = sub.add_parser("status", help="funnel counts")
    s.set_defaults(fn=cmd_status)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
