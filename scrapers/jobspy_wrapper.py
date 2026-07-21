#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import UTC, datetime
from typing import Any

from lib.dedupe import dedupe_jobs
from lib.keywords import load_keywords, passes_keyword_filters
from lib.normalize import dump_json_array, normalize_job, parse_datetime
from lib.ratelimit import rate_limit


SITE_MAP = {
    "linkedin": "linkedin",
    "indeed": "indeed",
    "glassdoor": "glassdoor",
    "ziprecruiter": "zip_recruiter",
    "zip_recruiter": "zip_recruiter",
}


def caveman(message: str) -> None:
    print(message, file=sys.stderr)


def parse_sites(value: str) -> list[str]:
    sites: list[str] = []
    for item in value.split(","):
        key = item.strip().lower()
        if not key:
            continue
        if key not in SITE_MAP:
            raise argparse.ArgumentTypeError(f"unsupported site: {key}")
        sites.append(SITE_MAP[key])
    if not sites:
        raise argparse.ArgumentTypeError("at least one site required")
    return sites


def hours_old_from_since(since: str | None) -> int | None:
    if not since:
        return None
    since_dt = parse_datetime(since)
    if not since_dt:
        return None
    delta = datetime.now(UTC) - since_dt
    return max(1, int(math.ceil(delta.total_seconds() / 3600)))


def _dataframe_to_records(value: Any) -> list[dict[str, Any]]:
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _row_source(row: dict[str, Any], requested_sites: list[str]) -> str:
    source = str(row.get("site") or row.get("source") or "").lower()
    if source == "zip_recruiter":
        return "ziprecruiter"
    if source:
        return source
    if len(requested_sites) == 1:
        return requested_sites[0].replace("zip_recruiter", "ziprecruiter")
    return "jobspy"


_RATE_LIMIT_MARKERS = ("429", "too many requests", "rate limit", "rate-limit")
_BACKOFF_ATTEMPTS = 4


def _scrape_with_backoff(scrape_jobs, kwargs: dict[str, Any]):
    """Call scrape_jobs, retrying with exponential backoff on 429/rate-limit.

    LinkedIn JD fetch hits one extra request per posting, so 429s are likely on
    big runs. Other errors propagate immediately (retrying won't help).
    """
    for attempt in range(1, _BACKOFF_ATTEMPTS + 1):
        try:
            return scrape_jobs(**kwargs)
        except Exception as exc:
            msg = str(exc).lower()
            if not any(m in msg for m in _RATE_LIMIT_MARKERS) or attempt == _BACKOFF_ATTEMPTS:
                raise
            wait = 5 * (2 ** (attempt - 1))
            caveman(f"rate-limited (attempt {attempt}/{_BACKOFF_ATTEMPTS}); backoff {wait}s.")
            time.sleep(wait)


def run_jobspy(args: argparse.Namespace) -> list[dict[str, Any]]:
    from jobspy import scrape_jobs

    requested_sites = args.sites
    for site in requested_sites:
        rate_limit(site.replace("zip_recruiter", "ziprecruiter"))

    kwargs: dict[str, Any] = {
        "site_name": requested_sites,
        "search_term": args.keywords,
        "location": args.location,
        "results_wanted": args.results_wanted,
    }
    hours_old = hours_old_from_since(args.since)
    if hours_old:
        kwargs["hours_old"] = hours_old
    if args.country_indeed:
        kwargs["country_indeed"] = args.country_indeed
    if "linkedin" in requested_sites:
        # Fetch full JD per posting (extra request each) so scoring/tailoring
        # have real text instead of "nan". Slower, raises 429 risk.
        kwargs["linkedin_fetch_description"] = True

    records = _dataframe_to_records(_scrape_with_backoff(scrape_jobs, kwargs))
    keyword_config = load_keywords()
    normalized = []
    for row in records:
        source = _row_source(row, requested_sites)
        job = normalize_job(row, source=source)
        normalized.append(job)

    # Minimal pre-filter: drop only obvious junk (intern/fresher/dev roles) via the
    # exclude list. We deliberately DO NOT hard-gate on title-phrase (tier1) or location
    # here: the holistic AI scorer + the fit gate downstream judge relevance far better,
    # and the old regex/location gates silently dropped valid roles (e.g. "DL, IN" Delhi
    # jobs, since jobspy returns state codes, not city names). Location is a soft scoring
    # signal now, not a hard cut.
    normalized = [
        job
        for job in normalized
        if passes_keyword_filters(job, keyword_config, require_tier1=False, require_location=False)
    ]
    return dedupe_jobs(normalized, use_fingerprint=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wrap python-jobspy for LinkedIn, Indeed, Glassdoor, and ZipRecruiter."
    )
    parser.add_argument("--sites", required=True, type=parse_sites, help="Comma-separated sites.")
    parser.add_argument("--keywords", required=True, help="Search keywords.")
    parser.add_argument("--location", required=True, help="Search location.")
    parser.add_argument("--since", required=True, help="ISO timestamp. Only newer jobs are returned.")
    parser.add_argument("--results-wanted", type=int, default=50, help="Max rows requested per site.")
    parser.add_argument("--country-indeed", default="India", help="python-jobspy country_indeed value.")
    args = parser.parse_args()

    requested = ",".join(site.replace("zip_recruiter", "ziprecruiter") for site in args.sites)
    caveman(f"{requested} scrape start since {args.since}.")
    try:
        jobs = run_jobspy(args)
    except KeyboardInterrupt:
        dump_json_array([])
        caveman(f"{requested} fatal interrupted.")
        return 2
    except ImportError as exc:
        dump_json_array([])
        caveman(f"{requested} fatal python-jobspy import failed: {exc}.")
        return 2
    except Exception as exc:
        dump_json_array([])
        caveman(f"{requested} transient error {type(exc).__name__}: {exc}.")
        return 1

    dump_json_array(jobs)
    caveman(f"{requested} {len(jobs)} jobs after filters. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

