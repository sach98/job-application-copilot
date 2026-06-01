#!/usr/bin/env python3
"""Fetch fresh jobs straight from companies' public ATS job boards.

This is the most reliable + fastest "as-posted" source: Greenhouse / Lever / Ashby
expose public JSON boards that update the instant a recruiter posts — no scraping, no
ban, no rate limits. Curate the target company list in TARGETS (or pass --companies a
JSON file). Output: normalized job dicts (same shape as jobspy_wrapper) to stdout.

Usage:
  ats_fetch.py                         # use built-in TARGETS
  ats_fetch.py --companies my.json     # [{"name","ats","token"}, ...]
  ats_fetch.py --india-only            # keep only India / remote roles
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Curated target list — companies whose roles fit a senior BFSI/insurance/analytics BA
# AND that use a public ATS (Greenhouse/Lever/Ashby). Workday/SuccessFactors/Taleo are
# NOT here (no clean public JSON). Edit freely; `ats` ∈ {greenhouse, lever, ashby}.
TARGETS: list[dict] = [
    # token = the board slug in the ATS URL. Verified live by --probe.
    {"name": "Razorpay", "ats": "lever", "token": "razorpay"},
    {"name": "Groww", "ats": "lever", "token": "groww"},
    {"name": "Zeta", "ats": "greenhouse", "token": "zeta"},
    {"name": "Navi", "ats": "lever", "token": "navi"},
    {"name": "PhonePe", "ats": "greenhouse", "token": "phonepe"},
    {"name": "CRED", "ats": "lever", "token": "cred"},
    {"name": "Plaid", "ats": "greenhouse", "token": "plaid"},
    {"name": "Stripe", "ats": "greenhouse", "token": "stripe"},
    {"name": "Wise", "ats": "lever", "token": "wise"},
    {"name": "Coinbase", "ats": "greenhouse", "token": "coinbase"},
]

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) JobHunt/1.0"
INDIA_HINTS = ("india", "bengaluru", "bangalore", "mumbai", "delhi", "gurgaon", "gurugram",
               "noida", "hyderabad", "pune", "chennai", "kolkata", "remote")


def log(msg: str) -> None:
    print(f"[ats] {msg}", file=sys.stderr, flush=True)


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_greenhouse(token: str) -> list[dict]:
    # content=true includes the JD HTML; absolute_url is the apply link.
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "external_id": f"gh-{token}-{j.get('id')}",
            "title": j.get("title") or "",
            "company": token,
            "location": (j.get("location") or {}).get("name") or "",
            "jd_text": _strip_html(j.get("content") or ""),
            "jd_url": j.get("absolute_url") or "",
            "posted_at": j.get("updated_at") or j.get("first_published") or "",
            "source": "ats:greenhouse",
        })
    return out


def fetch_lever(token: str) -> list[dict]:
    data = _get(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        out.append({
            "external_id": f"lv-{token}-{j.get('id')}",
            "title": j.get("text") or "",
            "company": token,
            "location": cats.get("location") or "",
            "jd_text": _strip_html(j.get("descriptionPlain") or j.get("description") or ""),
            "jd_url": j.get("hostedUrl") or j.get("applyUrl") or "",
            "posted_at": _ms_to_iso(j.get("createdAt")),
            "source": "ats:lever",
        })
    return out


def fetch_ashby(token: str) -> list[dict]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "external_id": f"ab-{token}-{j.get('id')}",
            "title": j.get("title") or "",
            "company": token,
            "location": j.get("location") or "",
            "jd_text": _strip_html(j.get("descriptionPlain") or j.get("descriptionHtml") or ""),
            "jd_url": j.get("jobUrl") or j.get("applyUrl") or "",
            "posted_at": j.get("publishedAt") or "",
            "source": "ats:ashby",
        })
    return out


_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def _strip_html(s: str) -> str:
    import re
    import html
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _ms_to_iso(ms) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _is_india(job: dict) -> bool:
    loc = (job.get("location") or "").lower()
    return any(h in loc for h in INDIA_HINTS)


def fetch_all(companies: list[dict], india_only: bool = False) -> list[dict]:
    jobs: list[dict] = []
    for c in companies:
        fetcher = _FETCHERS.get((c.get("ats") or "").lower())
        if not fetcher:
            log(f"skip {c.get('name')}: unknown ats {c.get('ats')}")
            continue
        try:
            rows = fetcher(c["token"])
            jobs.extend(rows)
            log(f"{c.get('name')}: {len(rows)} postings")
        except urllib.error.HTTPError as e:
            log(f"{c.get('name')}: HTTP {e.code} (bad token / board private?)")
        except Exception as e:
            log(f"{c.get('name')}: {type(e).__name__} {str(e)[:60]}")
    if india_only:
        jobs = [j for j in jobs if _is_india(j)]
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", help="JSON file: [{name,ats,token}, ...]")
    ap.add_argument("--india-only", action="store_true")
    ap.add_argument("--probe", action="store_true", help="Just report which boards return jobs.")
    args = ap.parse_args()

    companies = TARGETS
    if args.companies:
        companies = json.loads(open(args.companies, encoding="utf-8").read())

    jobs = fetch_all(companies, india_only=args.india_only)
    if args.probe:
        log(f"total {len(jobs)} postings across {len(companies)} boards")
        return 0
    print(json.dumps(jobs, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
