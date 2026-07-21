# Codex brief: build scrapers

Build all scrapers in `~/JobHunt/scrapers/`. Each must:

1. Read keyword config from `~/JobHunt/docs/keywords.md` (parse Tier-1 + Tier-2 sections + location filter).
2. Run with `--since <ISO>` flag, only return postings newer than that.
3. Output JSON array to stdout in normalised schema:
   ```json
   [{
     "source": "linkedin",
     "external_id": "<source-specific id>",
     "title": "...",
     "company": "...",
     "location": "...",
     "jd_text": "<full text>",
     "jd_url": "https://...",
     "posted_at": "<ISO>",
     "scraped_at": "<ISO>",
     "salary": "<range or null>",
     "hiring_mgr_hint": "<from JD if present, else null>",
     "experience_required": "<years range or null>"
   }, ...]
   ```
4. Exit code: 0 success, 1 transient error (n8n retries), 2 fatal (alert candidate).
5. Log to stderr in caveman style. Example: `linkedin scrape start since 2026-05-27T03:00. fetched 47 jobs. matched 12 after filter. done.`

## Per-scraper specs

### `jobspy_wrapper.py`

Wraps the `python-jobspy` library. Supports LinkedIn, Indeed, Glassdoor, ZipRecruiter. Single CLI:

```
python jobspy_wrapper.py --sites linkedin,indeed,glassdoor --keywords "..." --location "Delhi NCR" --since <ISO>
```

### `rss_parsers.py`

Generic RSS-to-normalised-JSON. Sources:
- Naukri RSS (per-search URL)
- Indeed RSS
- Hirist RSS
- YC Work at a Startup RSS

```
python rss_parsers.py --source naukri --query "business analyst BFSI" --location "Delhi NCR" --since <ISO>
```

### `wellfound.ts` (Playwright)

Headless. Login optional. Crawl `wellfound.com/jobs?role=business-analyst&location=delhi-ncr`. Pages 1-3 (newest first). Halt when posted_at < since.

### `instahyre.ts` (Playwright)

Login required (uses stored cookie). Crawl matching the keyword set. Their API rate-limits at ~30 reqs/min, Codex must implement backoff.

### `cutshort.ts` (Playwright)

Similar to Wellfound. No login needed for public listings.

### `foundit.ts` (Playwright)

ex-Monster India. Public crawl.

### `ambitionbox.ts` (Playwright)

Their jobs section. Login optional. Useful for company × salary band signal.

### `iimjobs_inbox_parse.py`

iimjobs sends daily email digests. candidate subscribed. Script reads Gmail label `JobHunt/iimjobs`, parses each email's job rows, returns normalised JSON.

```
python iimjobs_inbox_parse.py --since <ISO>
```

### `google_jobs_apify.py`

Calls Apify `dan/google-jobs-scraper` via API. Watch Apify quota, if `usage_pct > 80`, exit 0 with empty array + warning to stderr.

## Shared library

`~/JobHunt/scrapers/lib/`:

- `keywords.py`: parse keywords.md once, expose filter regex
- `normalize.py`: common JSON output helper
- `dedupe.py`: hash function for `(company, role, jd_url)`
- `cookies.py`: load LinkedIn/Naukri/Instahyre cookies from n8n credentials store

## Test plan

- Each scraper has `test_fixtures/<source>_sample.json` with 3-5 hand-curated golden outputs.
- `make test-scrapers` runs `pytest scrapers/tests/`: for each source, mocks HTTP, asserts normalised output matches golden.
- Smoke test: `make smoke-scrapers` runs each live against a 1-hour `--since` window in dry-run mode (writes to stdout, doesn't update sheet). Antigravity validates output looks sane.

## Anti-fragility

- If a source's HTML changes and selectors break: Antigravity is the on-call. Codex writes a `--debug` flag that screenshots + dumps HTML so Antigravity can regenerate selectors fast.
- All scrapers retry 3x with exponential backoff (1s, 4s, 16s).
- Rate-limiting: per-source budget (e.g. LinkedIn ≤ 30 reqs/min) enforced by token-bucket in `lib/`.
