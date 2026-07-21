#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests

from lib.dedupe import dedupe_jobs
from lib.keywords import load_keywords, passes_keyword_filters
from lib.normalize import dump_json_array, normalize_job
from lib.ratelimit import rate_limit


SOURCE = "google_jobs"
ACTOR_ENDPOINT = "https://api.apify.com/v2/acts/orgupdate~google-jobs-scraper/run-sync-get-dataset-items"
USER_ENDPOINT = "https://api.apify.com/v2/users/me"

# Apify is a paid platform and the free $5/month cap is exhausted. Free-only
# mode: never call Apify (no cost). Flip to True to re-enable once on a paid plan.
APIFY_ENABLED = False


def caveman(message: str) -> None:
    print(f"{SOURCE} {message}", file=sys.stderr)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def apify_usage_pct(token: str) -> float:
    response = requests.get(USER_ENDPOINT, headers=_headers(token), timeout=20)
    response.raise_for_status()
    data = response.json().get("data", response.json())
    usage = data.get("usage") or data.get("currentUsage") or {}
    limits = data.get("limits") or data.get("usageLimits") or {}

    used = (
        usage.get("monthlyUsageUsd")
        or usage.get("totalUsageUsd")
        or usage.get("computeUnits")
        or data.get("monthlyUsageUsd")
    )
    limit = (
        limits.get("monthlyUsageUsd")
        or limits.get("monthlyUsageLimitUsd")
        or limits.get("computeUnits")
        or data.get("monthlyUsageLimitUsd")
    )
    try:
        if used is None or not limit:
            return 0.0
        return float(used) / float(limit) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def call_apify(token: str, query: str, location: str, max_items: int) -> list[dict[str, Any]]:
    rate_limit(SOURCE)
    payload = {
        "queries": [query],
        "location": location,
        "maxItems": max_items,
        "language": "en",
    }
    response = requests.post(ACTOR_ENDPOINT, headers=_headers(token), json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items") or data.get("jobs") or data.get("data") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def normalize_apify_item(item: dict[str, Any]) -> dict[str, Any]:
    detected = item.get("detected_extensions")
    detected_posted_at = detected.get("posted_at") if isinstance(detected, dict) else None
    return normalize_job(
        {
            "source": SOURCE,
            "external_id": item.get("job_id")
            or item.get("id")
            or item.get("jobId")
            or item.get("apply_link")
            or item.get("link")
            or item.get("URL"),
            "title": item.get("title") or item.get("job_title"),
            "company": item.get("company_name") or item.get("company"),
            "location": item.get("location"),
            "jd_text": item.get("description") or item.get("snippet") or item.get("extensions"),
            "jd_url": item.get("apply_link") or item.get("link") or item.get("share_link") or item.get("URL"),
            "posted_at": detected_posted_at or item.get("posted_at") or item.get("date_posted") or item.get("date"),
            "salary": item.get("salary"),
        },
        source=SOURCE,
    )


def run_google_jobs(args: argparse.Namespace) -> tuple[list[dict], bool]:
    if not APIFY_ENABLED:
        caveman("apify disabled (free-only mode). returning empty.")
        return [], True

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        from pathlib import Path
        # Same JOBHUNT_ROOT convention as lib/playwright_common.py.
        env_path = Path(os.environ.get("JOBHUNT_ROOT") or (Path.home() / "JobHunt")) / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == "APIFY_TOKEN":
                        os.environ["APIFY_TOKEN"] = v.strip().strip('"').strip("'")
                        token = os.environ["APIFY_TOKEN"]
                        break
    if not token:
        raise RuntimeError("APIFY_TOKEN missing")

    try:
        usage_pct = apify_usage_pct(token)
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 0
        if status_code in (401, 402, 403):
            caveman(f"quota exceeded checking usage (HTTP {status_code}). returning empty.")
            return [], True
        usage_pct = 0.0
    except Exception:
        usage_pct = 0.0

    if usage_pct > 80:
        caveman(f"quota usage {usage_pct:.1f} pct over 80. returning empty.")
        return [], True

    try:
        raw_items = call_apify(token, args.query, args.location, args.max_items)
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 0
        if status_code in (401, 402, 403):
            caveman(f"quota exceeded running actor (HTTP {status_code}). returning empty.")
            return [], True
        raise
    normalized = [normalize_apify_item(item) for item in raw_items]
    keyword_config = load_keywords()
    normalized = [
        job
        for job in normalized
        if passes_keyword_filters(job, keyword_config, require_location=True)
    ]
    return dedupe_jobs(normalized, use_fingerprint=True), False


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Jobs scraper through Apify.")
    parser.add_argument("--since", required=True, help="ISO timestamp. Hint for how far back to crawl; roles are not dropped by age.")
    parser.add_argument("--query", default="business analyst BFSI", help="Google Jobs query.")
    parser.add_argument("--location", default="Delhi NCR", help="Search location.")
    parser.add_argument("--max-items", type=int, default=50, help="Max items requested from Apify.")
    args = parser.parse_args()

    caveman(f"scrape start since {args.since}.")
    try:
        jobs, quota_skip = run_google_jobs(args)
    except KeyboardInterrupt:
        dump_json_array([])
        caveman("fatal interrupted.")
        return 2
    except Exception as exc:
        dump_json_array([])
        caveman(f"transient error {type(exc).__name__}: {exc}.")
        return 1

    dump_json_array(jobs)
    status = "quota skip done" if quota_skip else "done"
    caveman(f"{len(jobs)} jobs after filters. {status}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
