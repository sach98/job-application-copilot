import subprocess
import sys
import time
from playwright.sync_api import Page

CAPTCHA_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='cloudflare']",
    "iframe[src*='arkose']",
    "iframe[title*='recaptcha']",
    "iframe[title*='hcaptcha']",
    "iframe[src*='funcaptcha']",
    "div.g-recaptcha",
    "div.h-captcha",
    "div#cf-turnstile",
    "div.cf-turnstile",
    ".cf-turnstile-wrapper",
    ".g-recaptcha",
    ".h-captcha",
    "text=Verify you are human",
    "text=Checking your browser",
    "text=Please solve the CAPTCHA",
    "text=solve the challenge",
    "text=verify that you are a human",
    "text=complete the security check"
]

def check_and_solve_captcha(page: Page, log_fn=None) -> None:
    """Detects if a CAPTCHA is present, activates the browser window, alerts the user, and blocks until solved."""
    if not log_fn:
        def log_fn(msg):
            print(f"[*] [CAPTCHA-Check] {msg}", file=sys.stderr, flush=True)

    captcha_detected = False
    detected_reason = ""

    # 1. Check page title
    try:
        title = page.title()
        if "Just a moment" in title or "Cloudflare" in title:
            captcha_detected = True
            detected_reason = f"Page title: '{title}'"
    except Exception:
        pass

    # 2. Check selectors
    if not captcha_detected:
        for selector in CAPTCHA_SELECTORS:
            try:
                loc = page.locator(selector).first
                if loc.count() > 0 and loc.is_visible(timeout=200):
                    captcha_detected = True
                    detected_reason = f"Selector: {selector}"
                    break
            except Exception:
                continue

    if captcha_detected:
        log_fn(f"ALERT: CAPTCHA detected ({detected_reason})! Bringing Comet to front.")
        
        # Bring Comet browser to focus on Mac, send notification, and beep
        try:
            # Focus browser
            subprocess.run(["osascript", "-e", 'tell application "Comet" to activate'], capture_output=True)
            # Send Notification
            subprocess.run(["osascript", "-e", 'display notification "CAPTCHA challenge detected! Please solve it in the browser window." with title "JobHunt Autopilot"'], capture_output=True)
            # Beep
            subprocess.run(["osascript", "-e", 'beep 3'], capture_output=True)
        except Exception as e:
            log_fn(f"Could not trigger macOS system alerts: {e}")

        log_fn("Waiting for user to solve CAPTCHA in the browser window...")
        
        start_time = time.time()
        last_log_time = start_time
        
        while True:
            page.wait_for_timeout(2000)
            still_captcha = False

            # Check title again
            try:
                title = page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    still_captcha = True
            except Exception:
                pass

            if not still_captcha:
                # Check selectors again
                for selector in CAPTCHA_SELECTORS:
                    try:
                        loc = page.locator(selector).first
                        if loc.count() > 0 and loc.is_visible(timeout=200):
                            still_captcha = True
                            break
                    except Exception:
                        continue

            if not still_captcha:
                log_fn("CAPTCHA solved or cleared! Resuming execution...")
                # Play success sound
                try:
                    subprocess.run(["osascript", "-e", 'display notification "CAPTCHA cleared. Resuming autopilot..." with title "JobHunt Autopilot"'], capture_output=True)
                except Exception:
                    pass
                break

            current_time = time.time()
            if current_time - last_log_time >= 15:
                log_fn("Still waiting for CAPTCHA to be solved...")
                last_log_time = current_time
