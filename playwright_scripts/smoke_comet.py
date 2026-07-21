#!/usr/bin/env python3
import os
"""
Comet + Playwright smoke test.

Goal: confirm we can drive Comet via Playwright with a dedicated user-data-dir,
load LinkedIn, and detect whether session cookies are present.

Run: ~/JobHunt/.venv/bin/python ~/JobHunt/playwright_scripts/smoke_comet.py
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT") or (Path.home() / "JobHunt"))
COMET_BIN = os.environ.get("COMET_BIN", "/Applications/Comet.app/Contents/MacOS/Comet")
PROFILE_DIR = JOBHUNT_ROOT / ".browser-profile" / "comet"
SCREENSHOT = JOBHUNT_ROOT / "screenshots" / "smoke_comet.png"

def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print(f"launch comet bin={COMET_BIN} profile={PROFILE_DIR}", file=sys.stderr)
        # Use launch_persistent_context so user-data-dir persists across runs.
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=COMET_BIN,
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        page = ctx.new_page()
        print("nav linkedin.com/feed", file=sys.stderr)
        page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # If logged in, URL stays on /feed. If not, redirects to /login or /uas/login.
        url = page.url
        title = page.title()
        print(f"final_url={url}", file=sys.stderr)
        print(f"title={title}", file=sys.stderr)

        cookies = ctx.cookies("https://www.linkedin.com")
        session_cookie_name = os.environ.get("LINKEDIN_SESSION_COOKIE_NAME", "linkedin_session_cookie")
        session_cookie = next((c for c in cookies if c["name"] == session_cookie_name), None)
        print(f"cookies_total={len(cookies)} session_cookie_present={bool(session_cookie)}", file=sys.stderr)

        page.screenshot(path=str(SCREENSHOT), full_page=False)
        print(f"screenshot_saved={SCREENSHOT}", file=sys.stderr)

        ctx.close()

        # Result line for n8n/agents (last line of stderr is parseable)
        if session_cookie:
            print("RESULT=logged_in", file=sys.stderr)
            return 0
        elif "/login" in url or "/uas/login" in url:
            print("RESULT=not_logged_in", file=sys.stderr)
            return 1
        else:
            print("RESULT=unknown_state", file=sys.stderr)
            return 2

if __name__ == "__main__":
    sys.exit(main())
