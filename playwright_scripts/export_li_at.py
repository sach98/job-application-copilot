#!/usr/bin/env python3
import os
"""
Helper script to extract the LinkedIn session cookie from the Comet profile.
Saves it to a text file for easy copy-pasting into the n8n LinkedIn node.

Run: ~/JobHunt/.venv/bin/python ~/JobHunt/playwright_scripts/export_linkedin_session_cookie.py
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

COMET_BIN = "/Applications/Comet.app/Contents/MacOS/Comet"
PROFILE_DIR = Path.home() / "JobHunt" / ".browser-profile" / "comet"
OUTPUT_FILE = Path.home() / "JobHunt" / "profile" / "linkedin_session_cookie.txt"

def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print(f"[*] Launching Comet from {COMET_BIN}...", file=sys.stderr)
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=COMET_BIN,
                headless=False,
                args=["--no-first-run", "--no-default-browser-check"],
            )
        except Exception as e:
            print(f"[-] Launch failed (Comet already running? Close it first): {e}", file=sys.stderr)
            return 1

        page = ctx.new_page()
        print("[*] Checking LinkedIn session status...", file=sys.stderr)
        page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=30000)
        
        cookies = ctx.cookies("https://www.linkedin.com")
        session_cookie_name = os.environ.get("LINKEDIN_SESSION_COOKIE_NAME", "linkedin_session_cookie")
        session_cookie = next((c for c in cookies if c["name"] == session_cookie_name), None)
        
        ctx.close()

        if session_cookie:
            cookie_value = session_cookie["value"]
            OUTPUT_FILE.write_text(cookie_value)
            print(f"[+] Found configured LinkedIn session cookie.", file=sys.stderr)
            print(f"[+] Saved LinkedIn session cookie value to: {OUTPUT_FILE}", file=sys.stderr)
            print(f"\n=======================================================", file=sys.stdout)
            print(f"YOUR LINKEDIN SESSION COOKIE VALUE:", file=sys.stdout)
            print(f"=======================================================", file=sys.stdout)
            print(cookie_value, file=sys.stdout)
            print(f"=======================================================", file=sys.stdout)
            return 0
        else:
            print("[-] Could not find LinkedIn session cookie.", file=sys.stderr)
            print("[-] Please open LinkedIn in Comet, log in, check 'Remember me', and try again.", file=sys.stderr)
            return 1

if __name__ == "__main__":
    sys.exit(main())
