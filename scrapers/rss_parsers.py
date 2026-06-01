#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from typing import Any
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

from lib.dedupe import dedupe_jobs
from lib.keywords import load_keywords, passes_keyword_filters
from lib.normalize import dump_json_array, normalize_job
from lib.ratelimit import rate_limit


SOURCE_URLS = {
    "indeed": "https://in.indeed.com/rss?q={query}&l={location}",
    "hirist": "https://www.hirist.tech/rss/jobs?query={query}&location={location}",
    "yc": "https://www.ycombinator.com/companies/jobs/rss",
}


def caveman(source: str, message: str) -> None:
    print(f"{source} {message}", file=sys.stderr)


def build_feed_url(source: str, query: str, location: str) -> str:
    template = SOURCE_URLS[source]
    return template.format(query=quote_plus(query), location=quote_plus(location))


def source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "naukri" in host:
        return "naukri"
    if "indeed" in host:
        return "indeed"
    if "hirist" in host:
        return "hirist"
    if "ycombinator" in host or "workatastartup" in host:
        return "yc"
    return "rss"


def fetch_feed(url: str, source: str) -> Any:
    rate_limit(source)
    response = requests.get(url, timeout=30, headers={"User-Agent": "JobHuntScraper/1.0"})
    response.raise_for_status()
    return feedparser.parse(response.content)


def _entry_company(entry: Any) -> str:
    for key in ("author", "publisher", "company", "source"):
        value = entry.get(key)
        if isinstance(value, dict):
            value = value.get("title")
        if value:
            return str(value)
    title = str(entry.get("title") or "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return ""


def _entry_title(entry: Any) -> str:
    title = str(entry.get("title") or "").strip()
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title


def _entry_location(entry: Any, default_location: str) -> str:
    for key in ("location", "job_location", "where"):
        if entry.get(key):
            return str(entry.get(key))
    for tag in entry.get("tags", []) or []:
        term = tag.get("term") if isinstance(tag, dict) else None
        if term and any(token in term.lower() for token in ("delhi", "remote", "gurgaon", "noida")):
            return term
    return default_location


def parse_feed_entries(feed: Any, source: str, default_location: str = "") -> list[dict]:
    raw_jobs: list[dict] = []
    for entry in feed.entries:
        summary = entry.get("summary") or entry.get("description") or ""
        link = entry.get("link") or ""
        raw_jobs.append(
            {
                "source": source,
                "external_id": entry.get("id") or entry.get("guid") or link,
                "title": _entry_title(entry),
                "company": _entry_company(entry),
                "location": _entry_location(entry, default_location),
                "jd_text": summary,
                "jd_url": link,
                "posted_at": entry.get("published") or entry.get("updated"),
            }
        )
    return raw_jobs


def run_rss(args: argparse.Namespace) -> list[dict]:
    source = args.source or source_from_url(args.feed_url)
    feed_url = args.feed_url or build_feed_url(source, args.query, args.location)
    feed = fetch_feed(feed_url, source)
    raw_jobs = parse_feed_entries(feed, source, args.location)
    normalized = [normalize_job(job, source=source) for job in raw_jobs]
    keyword_config = load_keywords()
    normalized = [
        job
        for job in normalized
        if passes_keyword_filters(job, keyword_config, require_location=bool(args.location))
    ]
    return dedupe_jobs(normalized, use_fingerprint=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse job RSS feeds into normalized JSON.")
    parser.add_argument("--feed-url", help="RSS feed URL.")
    parser.add_argument("--source", choices=sorted(SOURCE_URLS), help="Known source.")
    parser.add_argument("--query", default="business analyst BFSI", help="Search query for source feeds.")
    parser.add_argument("--location", default="Delhi NCR", help="Search/default location.")
    parser.add_argument("--since", required=True, help="ISO timestamp. Only newer jobs are returned.")
    args = parser.parse_args()
    if not args.feed_url and not args.source:
        parser.error("one of --feed-url or --source is required")

    source = args.source or source_from_url(args.feed_url)
    caveman(source, f"scrape start since {args.since}.")
    try:
        jobs = run_rss(args)
    except KeyboardInterrupt:
        dump_json_array([])
        caveman(source, "fatal interrupted.")
        return 2
    except Exception as exc:
        dump_json_array([])
        caveman(source, f"transient error {type(exc).__name__}: {exc}.")
        return 1

    dump_json_array(jobs)
    caveman(source, f"{len(jobs)} jobs after filters. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

