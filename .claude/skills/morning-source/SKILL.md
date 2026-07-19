---
name: morning-source
description: Simon's morning deal-sourcing run. Use when the user says "morning source", "source companies", or asks for the next batch of 50 companies. Runs the Form D discovery pipeline, scores the next 50 unshown candidates in-session, and delivers the two-sheet Excel workbook. "Continue" means run the next batch of 50.
---

# Morning sourcing run

The user is Simon Kushkov, a first-year analyst sourcing capital-efficient
B2B software companies around Series A/B. The pipeline lives in `pipeline/`;
its state is committed to git so it survives between sessions.

## The loop

1. **Sync state**: `git pull` on the working branch so state reflects prior runs.
2. **Setup** (once per session): `pip install -r pipeline/requirements.txt`.
3. **Refresh data** (from `pipeline/`):
   - `python -m sourcing.cli discover` — new Form Ds from EDGAR
   - `python -m sourcing.cli enrich` — job-board probes + ARR estimates
   - If either fails with proxy 403s, the environment's network policy is
     blocking `www.sec.gov` / `boards-api.greenhouse.io` / `api.lever.co` /
     `api.ashbyhq.com`. Tell Simon to allow those domains; score whatever
     is already in state instead of aborting.
4. **Select the batch**: `python -m sourcing.cli batch --size 50` →
   writes `pipeline/out/to_score.json`.
5. **Score in-session** — this is Claude's judgment step, not code. Read
   `to_score.json` and for each company write to `pipeline/out/scores.json`:
   - `accession` — copied through
   - `fit_score` — 1–10 against the thesis in `pipeline/config.yaml`
   - `founder_led` — true/false/null, judged from Form D officers
     (Executive Officer + Director on a young company suggests founder;
     a wall of investor-firm names suggests not)
   - `founder_evidence` — one sentence on why
   - `business_model` — best inference (B2B SaaS, marketplace, services…)
     from industry, hiring mix, and job titles
   - `rationale` — 2–3 sentences an analyst can read cold
   - `disqualifiers` — list of soft concerns (empty if none)
   Score only from evidence in the file; never invent revenue figures.
   Where evidence is thin, say so in the rationale.
6. **Merge and export**:
   - `python -m sourcing.cli ingest-scores`
   - `python -m sourcing.cli export --latest-batch`
7. **Deliver**: send the workbook file to Simon (SendUserFile). Lead with
   the count, the top 5 by fit, and how many remain in the queue.
8. **Persist**: commit `pipeline/state/` changes and push to the working
   branch. Never commit `pipeline/out/` or `pipeline/cache/`.

## "Continue"

When Simon says "continue", repeat steps 4–8. If the queue has fewer than
50 unshown candidates, run discover with `quarters_back` temporarily higher
(pass more quarters via config) or tell him the well is dry for today and
by how much.

## Hard rules

- Never scrape LinkedIn or licensed databases (PitchBook, Crunchbase web).
  The methodology sheet says the workbook contains none of that; keep it true.
- ARR estimates keep their method and confidence labels everywhere they
  appear. Do not present a proxy band as a point estimate.
