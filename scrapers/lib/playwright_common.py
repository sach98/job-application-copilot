from __future__ import annotations

import os
import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from lib.dedupe import dedupe_jobs
from lib.keywords import load_keywords, passes_keyword_filters
from lib.normalize import dump_json_array, normalize_job
from lib.ratelimit import rate_limit


JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT") or (Path.home() / "JobHunt"))
COMET_EXECUTABLE_PATH = os.environ.get("COMET_BIN", "/Applications/Comet.app/Contents/MacOS/Comet")
COMET_USER_DATA_DIR = str(JOBHUNT_ROOT / ".browser-profile" / "comet")
SCRAPERS_DIR = JOBHUNT_ROOT / "scrapers"


@dataclass(frozen=True)
class PlaywrightSourceConfig:
    source: str
    base_url: str
    search_url_template: str
    card_selector: str = "article, li, div"
    max_pages: int = 3

    def search_url(self, query: str, location: str, page_number: int) -> str:
        return self.search_url_template.format(
            query=quote_plus(query),
            location=quote_plus(location),
            page=page_number,
        )


def caveman(source: str, message: str) -> None:
    print(f"{source} {message}", file=sys.stderr)


def add_common_playwright_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since", required=True, help="ISO timestamp. Hint for how far back to crawl; roles are not dropped by age.")
    parser.add_argument("--keywords", default="business analyst", help="Search keywords.")
    parser.add_argument("--location", default="Delhi NCR", help="Search location.")
    parser.add_argument("--max-pages", type=int, default=3, help="Newest-first pages to crawl.")
    parser.add_argument("--headed", action="store_true", help="Run Comet visibly.")
    parser.add_argument("--debug", action="store_true", help="Save screenshot and HTML under scrapers/debug/.")


def _looks_like_job_card(tag) -> bool:
    attrs = " ".join(
        [
            str(tag.get("class") or ""),
            str(tag.get("id") or ""),
            str(tag.get("data-testid") or ""),
            str(tag.get("aria-label") or ""),
        ]
    ).lower()
    text = tag.get_text(" ", strip=True)
    href = ""
    link = tag.find("a", href=True)
    if link:
        href = str(link.get("href") or "").lower()
    return (
        "job" in attrs
        or "opening" in attrs
        or "/job" in href
        or "/jobs" in href
        or ("business analyst" in text.lower() and link is not None)
    )


def _first_text(card, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = card.select_one(selector)
        if element:
            text = element.get_text(" ", strip=True)
            if text:
                return text
    return ""


def _posted_text(card) -> str:
    candidates = []
    for tag in card.find_all(["time", "span", "div", "p"], limit=40):
        attrs = " ".join(
            [
                str(tag.get("class") or ""),
                str(tag.get("id") or ""),
                str(tag.get("datetime") or ""),
                str(tag.get("aria-label") or ""),
            ]
        ).lower()
        text = tag.get("datetime") or tag.get_text(" ", strip=True)
        if not text:
            continue
        lowered = str(text).lower()
        if "date" in attrs or "posted" in attrs or re.search(r"\b(ago|today|yesterday)\b", lowered):
            candidates.append(str(text))
    return candidates[0] if candidates else ""


def _external_id_from_url(url: str) -> str:
    if not url:
        return ""
    clean = url.split("?", 1)[0].rstrip("/")
    tail = clean.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", tail)[:120]


def extract_jobs_from_html(html: str, config: PlaywrightSourceConfig, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    raw_cards = [tag for tag in soup.select(config.card_selector) if _looks_like_job_card(tag)]
    if not raw_cards:
        raw_cards = [
            link.parent
            for link in soup.find_all("a", href=True)
            if "job" in str(link.get("href") or "").lower()
        ]

    jobs: list[dict] = []
    seen_urls: set[str] = set()
    for card in raw_cards:
        link = card.find("a", href=True)
        href = urljoin(config.base_url, link.get("href")) if link else page_url
        if href in seen_urls:
            continue
        seen_urls.add(href)

        title = _first_text(
            card,
            [
                "[data-testid*='title']",
                "[class*='title' i]",
                "h1",
                "h2",
                "h3",
                "a",
            ],
        )
        company = _first_text(
            card,
            [
                "[data-testid*='company']",
                "[class*='company' i]",
                "[class*='employer' i]",
                "[class*='org' i]",
            ],
        )
        location = _first_text(
            card,
            [
                "[data-testid*='location']",
                "[class*='location' i]",
                "[class*='loc' i]",
                "[class*='place' i]",
            ],
        )
        card_text = card.get_text("\n", strip=True)
        jobs.append(
            {
                "source": config.source,
                "external_id": _external_id_from_url(href),
                "title": title or (link.get_text(" ", strip=True) if link else ""),
                "company": company,
                "location": location,
                "jd_text": card_text,
                "jd_url": href,
                "posted_at": _posted_text(card),
            }
        )
    return jobs


async def _save_debug_artifacts(page, source: str, page_number: int) -> None:
    debug_dir = SCRAPERS_DIR / "debug" / source
    debug_dir.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(debug_dir / f"page_{page_number}.png"), full_page=True)
    (debug_dir / f"page_{page_number}.html").write_text(await page.content(), encoding="utf-8")


async def scrape_playwright_source(config: PlaywrightSourceConfig, args: argparse.Namespace) -> list[dict]:
    from playwright.async_api import async_playwright

    keyword_config = load_keywords()
    normalized: list[dict] = []
    max_pages = min(args.max_pages, config.max_pages)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=COMET_USER_DATA_DIR,
            executable_path=COMET_EXECUTABLE_PATH,
            headless=not args.headed,
        )
        page = await context.new_page()
        try:
            for page_number in range(1, max_pages + 1):
                rate_limit(config.source)
                url = config.search_url(args.keywords, args.location, page_number)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                if args.debug:
                    await _save_debug_artifacts(page, config.source, page_number)
                html = await page.content()
                raw_jobs = extract_jobs_from_html(html, config, page.url)
                page_jobs = [normalize_job(job, source=config.source) for job in raw_jobs]
                page_jobs = [
                    job
                    for job in page_jobs
                    if passes_keyword_filters(job, keyword_config, require_location=True)
                ]
                normalized.extend(page_jobs)
                if len(raw_jobs) > 0 and len(page_jobs) == 0:
                    break
        finally:
            await context.close()

    return dedupe_jobs(normalized, use_fingerprint=True)


def run_playwright_cli(config: PlaywrightSourceConfig) -> int:
    parser = argparse.ArgumentParser(description=f"{config.source} Playwright scraper")
    add_common_playwright_args(parser)
    args = parser.parse_args()
    caveman(config.source, f"scrape start since {args.since}.")

    try:
        jobs = asyncio.run(scrape_playwright_source(config, args))
    except KeyboardInterrupt:
        dump_json_array([])
        caveman(config.source, "fatal interrupted.")
        return 2
    except Exception as exc:
        dump_json_array([])
        caveman(config.source, f"transient error {type(exc).__name__}: {exc}.")
        return 1

    dump_json_array(jobs)
    caveman(config.source, f"{len(jobs)} jobs after filters. done.")
    return 0

