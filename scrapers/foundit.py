#!/usr/bin/env python3
from __future__ import annotations

from lib.playwright_common import PlaywrightSourceConfig, run_playwright_cli


CONFIG = PlaywrightSourceConfig(
    source="foundit",
    base_url="https://www.foundit.in",
    search_url_template=(
        "https://www.foundit.in/srp/results?query={query}&locations={location}&page={page}"
    ),
    card_selector="article, li, div[class*='job' i], div[data-testid*='job' i]",
    max_pages=3,
)


if __name__ == "__main__":
    raise SystemExit(run_playwright_cli(CONFIG))

