from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

# `Page` is only a type annotation here, so playwright is not needed at import time.
if TYPE_CHECKING:
    from playwright.sync_api import Page

from lib.paths import JOBHUNT_ROOT, SCREENSHOTS_DIR

SCREENSHOT_DIR = SCREENSHOTS_DIR

def take_screenshot(page: Page, company: str, role: str, label: str) -> Path:
    """Takes a screenshot and saves it to a designated subdirectory for the company/role."""
    # Clean the directory and file names
    safe_company = "".join([c if c.isalnum() else "_" for c in company]).strip("_")
    safe_role = "".join([c if c.isalnum() else "_" for c in role]).strip("_")
    
    subdir = SCREENSHOT_DIR / f"{safe_company}_{safe_role}"
    subdir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%H%M%S")
    filepath = subdir / f"{label}_{timestamp}.png"
    
    try:
        page.screenshot(path=str(filepath), full_page=False)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] screenshot saved: {filepath.relative_to(JOBHUNT_ROOT)}", file=sys.stderr)
        return filepath
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] screenshot fail {label}: {e}", file=sys.stderr)
        return filepath
