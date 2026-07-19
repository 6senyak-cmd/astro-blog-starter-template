"""
Generate a demo workbook with synthetic companies so the output format is
visible without a live network run. Every company here is INVENTED — the
names, filings, and numbers are placeholders to show the four ARR methods
(disclosed / stated / proxy / none) and the layout. Not real data.

Run from pipeline/:  python -m tests.demo
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sourcing import arr, excel  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


DEMO = [
    {
        "entity_name": "Ledgerline Software Inc. [EXAMPLE]",
        "city": "Durham", "state": "NC", "year_incorporated": 2022,
        "industry": "Other Technology", "total_sold_usd": 9_500_000,
        "revenue_range": "$1,000,001 - $5,000,000",
        "officers": "Dana Whitfield (Executive Officer, Director); Marcus Oyelaran (Executive Officer)",
        "open_roles": 11, "commercial_roles": 4,
        "board_url": "https://boards.greenhouse.io/example", "board_verified": True,
        "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        "fit_score": 9, "founder_led": True,
        "founder_evidence": "Exec officer who is also a director at a 2022-incorporated company; small officer list.",
        "business_model": "B2B SaaS (accounting)",
        "rationale": "Disclosed $1-5M revenue against a $9.5M raise in the Series A band. Hiring skews go-to-market (4 of 11 roles are commercial), consistent with a company moving from product to distribution.",
        "growth_flag": "+3 roles since 2026-07-05", "first_seen": "2026-07-12",
    },
    {
        "entity_name": "Northwind Analytics Corp. [EXAMPLE]",
        "city": "Austin", "state": "TX", "year_incorporated": 2021,
        "industry": "Computers", "total_sold_usd": 18_000_000,
        "revenue_range": "Decline to Disclose",
        "officers": "Priya Raman (Executive Officer, Director); Two Rivers Capital LLC (Promoter)",
        "open_roles": 6, "commercial_roles": 3,
        "stated_arr": {"usd": 6_000_000, "quote": "$6M in ARR"},
        "board_url": "https://jobs.lever.co/example", "board_verified": False,
        "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        "fit_score": 7, "founder_led": True,
        "founder_evidence": "Founder-CEO listed as officer+director, though a capital firm appears as promoter.",
        "business_model": "B2B SaaS (data/analytics)",
        "rationale": "Declined to disclose revenue on the filing, but a careers posting cites '$6M in ARR' — treat as medium confidence, unverified marketing copy. $18M raise is at the upper Series A / lower Series B boundary.",
        "growth_flag": "flat since 2026-07-05", "first_seen": "2026-07-08",
    },
    {
        "entity_name": "Cobalt Robotics Systems Inc. [EXAMPLE]",
        "city": "Boston", "state": "MA", "year_incorporated": 2023,
        "industry": "Other Technology", "total_sold_usd": 22_000_000,
        "revenue_range": "Decline to Disclose",
        "officers": "Sam Okafor (Executive Officer, Director)",
        "open_roles": 14, "commercial_roles": 1,
        "board_url": "https://jobs.ashbyhq.com/example", "board_verified": True,
        "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        "fit_score": 5, "founder_led": True,
        "founder_evidence": "Single officer who is founder, CEO and director at a 2023 company.",
        "business_model": "Hardware + software (robotics)",
        "rationale": "No disclosed revenue and no ARR figure in postings, so ARR is a headcount proxy only — a wide band, sort key not a number. Hiring is 13-of-14 engineering, i.e. still R&D-heavy rather than commercial. Younger and more capital-intensive than the thesis prefers.",
        "growth_flag": "+5 roles since 2026-07-05", "first_seen": "2026-07-15",
    },
    {
        "entity_name": "Harbor Compliance Cloud LLC [EXAMPLE]",
        "city": "Denver", "state": "CO", "year_incorporated": 2020,
        "industry": "Business Services", "total_sold_usd": 5_000_000,
        "revenue_range": "Decline to Disclose",
        "officers": "Elena Vasquez (Executive Officer, Director); Jordan Lee (Executive Officer)",
        "open_roles": None, "commercial_roles": None,
        "board_url": "", "board_verified": False,
        "filing_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
        "fit_score": 6, "founder_led": True,
        "founder_evidence": "Two officers, one also director, at a 2020 company — profile of a founder team.",
        "business_model": "B2B SaaS (regtech), inferred",
        "rationale": "Clean Series A raise in the thesis band, but no public job board was found under any guessed token, so there is no hiring signal and no revenue proxy. ARR is genuinely unknown here — worth a manual look rather than a pass or a fail.",
        "growth_flag": None, "first_seen": "2026-07-18",
    },
]


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for row in DEMO:
        row.update(arr.estimate(row, cfg["arr_model"]))
        row.setdefault("disqualifiers", [])
    out = ROOT / "out" / "sample_pipeline.xlsx"
    out.parent.mkdir(exist_ok=True)
    excel.write(DEMO, cfg, str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
