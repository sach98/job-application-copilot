#!/usr/bin/env python3
"""Parse iimjobs Gmail digests into JobHunt normalized JSON.

Setup notes for the real Gmail wiring:
1. Create/choose a Google Cloud project and enable the Gmail API.
2. Create an OAuth desktop-client credential for candidate's Google account.
3. Store the OAuth client JSON outside this repo, for example:
   ~/.config/jobhunt/google_oauth_client.json
4. Keep the user token outside this repo, for example:
   ~/.config/jobhunt/gmail_token.json
5. In Gmail, route iimjobs digest mail to label: JobHunt/iimjobs.

TODO(OAuth): add google-auth-oauthlib + google-api-python-client flow.
TODO(OAuth): query label JobHunt/iimjobs after --since and fetch message HTML parts.
TODO(OAuth): refresh tokens in memory only; never write secrets from this script unless candidate
explicitly approves the token-store implementation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from lib.dedupe import dedupe_jobs
from lib.keywords import load_keywords, passes_keyword_filters
from lib.normalize import dump_json_array, normalize_job
from lib.ratelimit import rate_limit


SOURCE = "iimjobs"
BASE_URL = "https://www.iimjobs.com"


def caveman(message: str) -> None:
    print(f"{SOURCE} {message}", file=sys.stderr)


def _title_from_link(link) -> str:
    text = link.get_text(" ", strip=True)
    if text:
        return text
    return str(link.get("title") or "").strip()


def parse_iimjobs_digest_html(html: str, *, received_at: str | None = None) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "")
        if "iimjobs.com" not in href and not href.startswith("/j/"):
            continue
        title = _title_from_link(link)
        if not title or title.lower() in {"view job", "apply"}:
            continue
        url = urljoin(BASE_URL, href)
        if url in seen:
            continue
        seen.add(url)
        container = link.find_parent(["tr", "li", "div"]) or link.parent
        text = container.get_text("\n", strip=True) if container else title
        jobs.append(
            {
                "source": SOURCE,
                "external_id": url.rstrip("/").rsplit("/", 1)[-1],
                "title": title,
                "company": "",
                "location": text,
                "jd_text": text,
                "jd_url": url,
                "posted_at": received_at,
            }
        )
    return jobs


def load_gmail_digest_messages(label: str, since: str) -> list[dict[str, str]]:
    rate_limit(SOURCE)
    raise NotImplementedError(
        "Gmail OAuth wiring is intentionally stubbed. Use --html-file for local parsing."
    )


def run_iimjobs(args: argparse.Namespace) -> list[dict]:
    if args.html_file:
        html = Path(args.html_file).expanduser().read_text(encoding="utf-8")
        raw_jobs = parse_iimjobs_digest_html(html, received_at=args.since)
    else:
        messages = load_gmail_digest_messages(args.label, args.since)
        raw_jobs = []
        for message in messages:
            raw_jobs.extend(
                parse_iimjobs_digest_html(
                    message.get("html", ""),
                    received_at=message.get("received_at") or args.since,
                )
            )

    normalized = [normalize_job(job, source=SOURCE) for job in raw_jobs]
    keyword_config = load_keywords()
    normalized = [
        job
        for job in normalized
        if passes_keyword_filters(job, keyword_config, require_location=True)
    ]
    return dedupe_jobs(normalized, use_fingerprint=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse iimjobs Gmail digests.")
    parser.add_argument("--since", required=True, help="ISO timestamp. Hint for how far back to crawl; roles are not dropped by age.")
    parser.add_argument("--label", default="JobHunt/iimjobs", help="Gmail label to parse.")
    parser.add_argument("--html-file", help="Local digest HTML file for parser testing.")
    args = parser.parse_args()

    caveman(f"scrape start since {args.since}.")
    try:
        jobs = run_iimjobs(args)
    except NotImplementedError as exc:
        dump_json_array([])
        caveman(f"transient oauth stub not wired: {exc}.")
        return 1
    except KeyboardInterrupt:
        dump_json_array([])
        caveman("fatal interrupted.")
        return 2
    except Exception as exc:
        dump_json_array([])
        caveman(f"transient error {type(exc).__name__}: {exc}.")
        return 1

    dump_json_array(jobs)
    caveman(f"{len(jobs)} jobs after filters. done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

