# Sourcing pipeline

Finds capital-efficient B2B software companies around Series A/B using only
free, public, terms-of-service-clean sources, and delivers them 50 at a
time as a two-sheet Excel workbook (Pipeline + Methodology).

## How it works

```
SEC EDGAR Form D ──► rules filter ──► job-board enrichment ──► ARR estimate
 (discovery)          (in/out)         (Greenhouse/Lever/       (disclosed /
                                        Ashby, public APIs)      stated / proxy)
                                                                     │
        Excel workbook ◄── export ◄── in-session Claude scoring ◄── batch of 50
```

- **Discovery**: every US company that raises from outside investors files
  a Form D with the SEC within 15 days. Free, structured, includes officers,
  amount raised, and sometimes a revenue range.
- **Enrichment**: public job-board JSON endpoints — hiring volume,
  go-to-market mix, occasionally a stated ARR figure in a posting.
- **Scoring**: qualitative fit is judged by Claude inside a Claude Code
  session ("morning source"), 50 companies per batch. No API key needed.
- **Not used**: LinkedIn and licensed databases (PitchBook, Crunchbase web).
  Scraping them breaches their terms of service.

## Daily use

Say **"morning source"** in a Claude Code session on this repo. Claude runs
discovery and enrichment, scores the next 50 unshown companies, and hands
you the workbook. Say **"continue"** for the next 50.

Manual equivalent, from this directory:

```
pip install -r requirements.txt
python -m sourcing.cli discover
python -m sourcing.cli enrich
python -m sourcing.cli batch --size 50   # -> out/to_score.json
# (scoring happens in-session; writes out/scores.json)
python -m sourcing.cli ingest-scores
python -m sourcing.cli export --latest-batch
python -m sourcing.cli status
```

## State

`state/` is committed to git on purpose — cloud sessions are ephemeral, and
the record of which companies you have already reviewed must survive
between mornings. `cache/` and `out/` are disposable and gitignored.

## Network requirements

The environment's egress policy must allow:

- `www.sec.gov`
- `boards-api.greenhouse.io`
- `api.lever.co`
- `api.ashbyhq.com`

## Assumptions

All tunable numbers (raise band, ARR-per-FTE benchmarks, industries,
batch size) live in `config.yaml`. The workbook's Methodology sheet prints
the assumptions used for that export.
