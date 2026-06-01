#!/usr/bin/env python3
from __future__ import annotations

from lib.playwright_common import PlaywrightSourceConfig, run_playwright_cli


CONFIG = PlaywrightSourceConfig(
    source="cutshort",
    base_url="https://cutshort.io",
    search_url_template="https://cutshort.io/jobs/{query}-jobs-in-{location}?page={page}",
    card_selector="article, li, div[class*='job' i], div[data-testid*='job' i]",
    max_pages=3,
)


if __name__ == "__main__":
    raise SystemExit(run_playwright_cli(CONFIG))

