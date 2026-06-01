#!/usr/bin/env python3
from __future__ import annotations

from lib.playwright_common import PlaywrightSourceConfig, run_playwright_cli


CONFIG = PlaywrightSourceConfig(
    source="instahyre",
    base_url="https://www.instahyre.com",
    search_url_template=(
        "https://www.instahyre.com/search-jobs/?skills={query}&locations={location}&page={page}"
    ),
    card_selector="div[class*='job' i], li, article",
    max_pages=3,
)


if __name__ == "__main__":
    raise SystemExit(run_playwright_cli(CONFIG))

