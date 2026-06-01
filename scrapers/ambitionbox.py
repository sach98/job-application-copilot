#!/usr/bin/env python3
from __future__ import annotations

from lib.playwright_common import PlaywrightSourceConfig, run_playwright_cli


CONFIG = PlaywrightSourceConfig(
    source="ambitionbox",
    base_url="https://www.ambitionbox.com",
    search_url_template=(
        "https://www.ambitionbox.com/jobs/search?tag={query}&location={location}&page={page}"
    ),
    card_selector="article, li, div[class*='job' i], div[class*='jobCard' i]",
    max_pages=3,
)


if __name__ == "__main__":
    raise SystemExit(run_playwright_cli(CONFIG))

