#!/usr/bin/env python3
"""
CAPTCHA Smoke Test.
Validates the CAPTCHA detection, focus activation, and wait loop logic.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add parent/sibling dir to path so we can import lib
sys.path.append(str(Path(__file__).parent))
from lib.captcha import check_and_solve_captcha

COMET_BIN = "/Applications/Comet.app/Contents/MacOS/Comet"
PROFILE_DIR = Path.home() / "JobHunt" / ".browser-profile" / "comet"

def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as p:
        print("[*] Launching Comet...", file=sys.stderr)
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
        
        # Load a simple test page
        print("[*] Loading test page...", file=sys.stderr)
        page.goto("data:text/html,<html><body><h1>CAPTCHA Smoke Test</h1></body></html>")
        page.wait_for_timeout(1000)
        
        # Inject simulated captcha and a timer to remove it after 6 seconds
        print("[*] Injecting simulated CAPTCHA element...", file=sys.stderr)
        page.evaluate("""() => {
            const div = document.createElement('div');
            div.className = 'g-recaptcha';
            div.innerHTML = '<h3>[SIMULATED CAPTCHA] Solve me! (Auto-resolves in 6s)</h3>';
            div.setAttribute('style', 'background: orange; padding: 20px; border: 2px solid red; font-size: 20px; text-align: center;');
            document.body.appendChild(div);
            
            // Set timer to remove the captcha element to simulate a user solving it
            setTimeout(() => {
                div.remove();
                console.log('CAPTCHA solved (removed)');
            }, 6000);
        }""")
        
        print("[*] Triggering check_and_solve_captcha loop...", file=sys.stderr)
        # This should block, sound a beep/notification, and then resume after 6s
        check_and_solve_captcha(page)
        
        print("[+] check_and_solve_captcha completed successfully!", file=sys.stderr)
        
        # Verify the element is gone
        captcha_count = page.locator("div.g-recaptcha").count()
        if captcha_count == 0:
            print("[+] Smoke test PASSED: CAPTCHA successfully detected, held execution, and resumed after removal.", file=sys.stderr)
            ctx.close()
            return 0
        else:
            print("[-] Smoke test FAILED: CAPTCHA still exists on the page.", file=sys.stderr)
            ctx.close()
            return 1

if __name__ == "__main__":
    sys.exit(main())
