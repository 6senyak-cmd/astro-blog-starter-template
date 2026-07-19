"""
Discovery layer: SEC EDGAR Form D.

Every US company that raises money from outside investors under Reg D --
which is nearly every priced Series A or B -- files a Form D within 15 days
of first sale. The filing is public, free, structured XML, and includes the
officers, the amount raised, and sometimes a self-reported revenue range.

This is the only discovery source in the pipeline, which has a known
consequence: a company that never raised outside capital never appears.
That caveat is written onto the Methodology sheet of every workbook.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "cache"

INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/master.idx"
ARCHIVES = "https://www.sec.gov/Archives/"


def quarters_back(n: int, today: date | None = None) -> list[tuple[int, int]]:
    today = today or date.today()
    year, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append((year, q))
        q -= 1
        if q == 0:
            year, q = year - 1, 4
    return out


def fetch_index(session, year: int, q: int, *, get) -> str:
    """Quarterly master index, cached to disk. The current quarter's index
    grows daily, so it is refetched; closed quarters are immutable."""
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / f"master_{year}_Q{q}.idx"
    cy, cq = date.today().year, (date.today().month - 1) // 3 + 1
    if cached.exists() and (year, q) != (cy, cq):
        return cached.read_text(encoding="utf-8", errors="replace")
    resp = get(session, INDEX_URL.format(year=year, q=q))
    if resp is None:
        return ""
    cached.write_text(resp.text, encoding="utf-8")
    return resp.text


def form_d_entries(index_text: str, *, include_amendments: bool = False) -> list[dict]:
    """Parse the pipe-delimited master index down to Form D rows.
    Line format: CIK|Company Name|Form Type|Date Filed|Filename"""
    wanted = {"D", "D/A"} if include_amendments else {"D"}
    out = []
    for line in index_text.splitlines():
        parts = line.split("|")
        if len(parts) != 5 or parts[2].strip() not in wanted:
            continue
        cik, name, form, filed, filename = (p.strip() for p in parts)
        out.append({"cik": cik, "name": name, "form": form, "filed": filed, "filename": filename})
    return out


def accession_of(entry: dict) -> str | None:
    m = re.search(r"(\d{10}-\d{2}-\d{6})", entry["filename"])
    return m.group(1) if m else None


def filing_urls(entry: dict) -> tuple[str, str]:
    """(primary_doc.xml URL, human-facing filing index URL)."""
    m = re.search(r"(\d{10}-\d{2}-\d{6})", entry["filename"])
    accession = m.group(1)
    nodash = accession.replace("-", "")
    base = f"{ARCHIVES}edgar/data/{int(entry['cik'])}/{nodash}"
    return f"{base}/primary_doc.xml", f"{base}/{accession}-index.htm"


def fetch_form_d(session, entry: dict, *, get) -> dict | None:
    """Download and parse one Form D into a flat candidate dict."""
    xml_url, index_url = filing_urls(entry)
    m = re.search(r"(\d{10}-\d{2}-\d{6})", entry["filename"])
    cached = CACHE / "formd" / f"{m.group(1)}.xml"
    if cached.exists():
        raw = cached.read_text(encoding="utf-8", errors="replace")
    else:
        resp = get(session, xml_url)
        if resp is None:
            return None
        raw = resp.text
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(raw, encoding="utf-8")
    parsed = parse_form_d(raw)
    if parsed is None:
        return None
    parsed.update(
        accession=m.group(1),
        cik=entry["cik"],
        date_filed=entry["filed"],
        filing_url=index_url,
    )
    return parsed


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        el.tag = el.tag.rsplit("}", 1)[-1]


def _text(root: ET.Element, path: str) -> str | None:
    el = root.find(path)
    return el.text.strip() if el is not None and el.text else None


def parse_form_d(raw_xml: str) -> dict | None:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return None
    _strip_ns(root)

    issuer = root.find(".//primaryIssuer")
    offering = root.find(".//offeringData")
    if issuer is None or offering is None:
        return None

    officers = []
    for person in root.iter("relatedPersonInfo"):
        first = _text(person, ".//firstName") or ""
        last = _text(person, ".//lastName") or ""
        rels = [r.text.strip() for r in person.iter("relationship") if r.text]
        name = f"{first} {last}".strip()
        if name:
            officers.append(f"{name} ({', '.join(rels)})" if rels else name)

    exemptions = [e.text.strip() for e in offering.iter("item") if e.text]
    total_sold = _text(offering, ".//offeringSalesAmounts/totalAmountSold")
    year_inc = _text(issuer, ".//yearOfInc/value")

    return {
        "entity_name": _text(issuer, "entityName"),
        "entity_type": _text(issuer, "entityType"),
        "city": _text(issuer, ".//issuerAddress/city"),
        "state": _text(issuer, ".//issuerAddress/stateOrCountry"),
        "year_incorporated": int(year_inc) if year_inc and year_inc.isdigit() else None,
        "industry": _text(root, ".//industryGroup/industryGroupType"),
        "revenue_range": _text(root, ".//issuerSize/revenueRange"),
        "is_equity": _text(offering, ".//typesOfSecuritiesOffered/isEquityType") == "true",
        "total_offering_usd": _int(_text(offering, ".//offeringSalesAmounts/totalOfferingAmount")),
        "total_sold_usd": _int(total_sold),
        "federal_exemptions": exemptions,
        "officers": "; ".join(officers),
        "date_of_first_sale": _text(offering, ".//dateOfFirstSale/value"),
    }


def _int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None
