#!/usr/bin/env python3
import os
"""
LinkedIn Referral and Followup outreach bot.
Drives Comet via Playwright to send connection invites, direct messages,
or InMails to hiring managers, team members, or referral contacts.
"""
import sys
import argparse
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Add script directory to sys.path to import lib
sys.path.append(str(Path(__file__).parent))
from lib.captcha import check_and_solve_captcha

JOBHUNT_ROOT = Path(os.environ.get("JOBHUNT_ROOT", str(Path.home() / "JobHunt")))
COMET_BIN = os.environ.get("COMET_BIN", "/Applications/Comet.app/Contents/MacOS/Comet")
PROFILE_DIR = JOBHUNT_ROOT / ".browser-profile" / "comet"

def log(msg: str) -> None:
    print(f"[*] [LinkedIn-Outreach] {msg}", file=sys.stderr, flush=True)

def main():
    parser = argparse.ArgumentParser(description="LinkedIn Outreach Script")
    parser.add_argument("--target-url", required=True, help="Profile URL of target contact")
    parser.add_argument("--message", required=True, help="Message/Invite note text")
    parser.add_argument("--type", default="auto", choices=["auto", "connect", "message", "inmail"], help="Outreach type")
    args = parser.parse_args()

    # Clean target URL
    target_url = args.target_url.split("?")[0].rstrip("/")
    if target_url.startswith("/"):
        target_url = "https://www.linkedin.com" + target_url
    message = args.message.strip()

    with sync_playwright() as p:
        log(f"Launching Comet with profile {PROFILE_DIR}")
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=COMET_BIN,
                headless=False,
                args=["--no-first-run", "--no-default-browser-check"],
                viewport={"width": 1400, "height": 900},
            )
        except Exception as e:
            log(f"Launch failed (Comet already running?): {e}")
            return 1

        page = ctx.new_page()
        
        # 1. Nav to target profile
        log(f"Navigating to: {target_url}")
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            check_and_solve_captcha(page, log_fn=log)
            time.sleep(5)
        except Exception as e:
            log(f"Navigation failed: {e}")
            ctx.close()
            return 1

        # Check if login required
        if "/login" in page.url or "/uas/login" in page.url:
            log("NOT logged in to LinkedIn. Please log in to LinkedIn first.")
            ctx.close()
            return 1

        # Determine connection degree
        degree_text = ""
        try:
            # Look for badge containing "1st", "2nd", "3rd" next to member's name
            badge = page.locator(".dist-value, span.dist-value").first
            if badge.count() > 0:
                degree_text = badge.inner_text().strip()
                log(f"Connection degree detected: {degree_text}")
        except Exception:
            pass

        outreach_type = args.type
        if outreach_type == "auto":
            if "1st" in degree_text:
                outreach_type = "message"
            else:
                outreach_type = "connect"
        
        success = False
        log(f"Selected outreach channel: {outreach_type}")

        if outreach_type == "message":
            success = send_direct_message(page, message)
        elif outreach_type == "connect":
            # LinkedIn connection notes are hard-capped at 300 chars
            note_text = message[:300]
            success = send_connection_invite(page, note_text)
        elif outreach_type == "inmail":
            success = send_inmail_message(page, message)

        # Take screenshot of final state
        safe_name = target_url.split("/in/")[-1].replace("-", "_")
        screenshot_dir = JOBHUNT_ROOT / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / f"linkedin_outreach_{safe_name}.png"))
        
        time.sleep(3)
        ctx.close()
        
        if success:
            log("Outreach succeeded!")
            return 0
        else:
            log("Outreach failed.")
            return 1

def send_direct_message(page, message: str) -> bool:
    check_and_solve_captcha(page, log_fn=log)
    log("Attempting direct message (1st-degree flow)...")
    try:
        # Search for primary 'Message' button
        # Usually inside top card actions: button contains 'Message'
        msg_btn = page.locator('button:has-text("Message"), a:has-text("Message")').filter(visible=True).first
        if msg_btn.count() == 0:
            log("Direct Message button not found. Trying 'More' dropdown...")
            # Click More
            more_btn = page.locator('button:has-text("More")').filter(visible=True).first
            if more_btn.count() > 0:
                more_btn.click()
                time.sleep(1.5)
                # Click Message from dropdown list
                msg_dropdown_item = page.locator('div[role="button"]:has-text("Message"), span:has-text("Message")').filter(visible=True).first
                if msg_dropdown_item.count() > 0:
                    msg_dropdown_item.click()
                    time.sleep(2)
                else:
                    log("Message item not in More dropdown.")
                    return False
            else:
                return False
        else:
            msg_btn.click()
            time.sleep(3)

        # Message box is now open (typically in a floating chat window)
        # Find active contenteditable or textarea
        textbox = page.locator('div[role="textbox"], .msg-form__contenteditable, textarea').filter(visible=True).first
        if textbox.count() == 0:
            log("Could not find message text area.")
            return False
            
        textbox.click()
        textbox.fill(message)
        time.sleep(1.5)
        
        # Click send
        send_btn = page.locator('button[type="submit"], .msg-form__send-button').filter(visible=True).first
        if send_btn.count() > 0:
            send_btn.click()
            time.sleep(2)
            log("Direct message sent successfully.")
            return True
        else:
            log("Could not find Send button.")
            return False
            
    except Exception as e:
        log(f"Direct message exception: {e}")
        return False

def send_connection_invite(page, note: str) -> bool:
    check_and_solve_captcha(page, log_fn=log)
    log("Attempting connection invitation note...")
    try:
        # 1. Click Connect
        connect_btn = page.locator('button:has-text("Connect")').filter(visible=True).first
        if connect_btn.count() == 0:
            log("Connect button not visible on main profile card. Searching 'More' dropdown...")
            more_btn = page.locator('button:has-text("More"), button[aria-label*="actions"]').filter(visible=True).first
            if more_btn.count() > 0:
                more_btn.click()
                time.sleep(1.5)
                # Click Connect from dropdown
                connect_dropdown_item = page.locator('span:has-text("Connect"), div[role="button"]:has-text("Connect")').filter(visible=True).first
                if connect_dropdown_item.count() > 0:
                    connect_dropdown_item.click()
                    time.sleep(2)
                else:
                    log("Connect not found in More dropdown.")
                    return False
            else:
                log("Connect and More action buttons not found.")
                return False
        else:
            connect_btn.click()
            time.sleep(2)

        # 2. Check if connection invite dialog opened
        # It typically has buttons: "Add a note" and "Send without a note" or "Send"
        add_note_btn = page.locator('button:has-text("Add a note")').filter(visible=True).first
        if add_note_btn.count() > 0:
            add_note_btn.click()
            time.sleep(1.5)
            
        # 3. Locate note textarea
        # Selector is typically #custom-message or textarea
        textarea = page.locator('textarea#custom-message, textarea[name="message"], textarea').filter(visible=True).first
        if textarea.count() == 0:
            log("Could not find connection note textarea.")
            return False
            
        textarea.click()
        textarea.fill(note)
        time.sleep(1.5)
        
        # 4. Click Send
        # Typically a button containing "Send" or class msg-invite-modal__send-btn
        send_btn = page.locator('button:has-text("Send"), button:has-text("Send invitation")').filter(visible=True).first
        if send_btn.count() > 0:
            send_btn.click()
            time.sleep(2)
            log("Connection invite note sent successfully.")
            return True
        else:
            log("Could not find Send Invitation button.")
            return False
            
    except Exception as e:
        log(f"Connection invite exception: {e}")
        return False

def send_inmail_message(page, message: str) -> bool:
    check_and_solve_captcha(page, log_fn=log)
    log("Attempting InMail message (Hiring Manager/Premium flow)...")
    try:
        # InMail typically opens when you click Message on a 2nd/3rd degree profile
        # Check if Message button exists
        msg_btn = page.locator('button:has-text("Message")').filter(visible=True).first
        if msg_btn.count() > 0:
            msg_btn.click()
            time.sleep(3)
        else:
            log("Message button not found for InMail.")
            return False

        # InMail dialog usually has a Subject line input and a Message body input
        subject_input = page.locator('input[placeholder="Subject"], input[name="subject"]').filter(visible=True).first
        if subject_input.count() > 0:
            subject_input.click()
            subject_input.fill("Regarding Business Analyst role")
            time.sleep(1)

        body_textarea = page.locator('textarea, div[role="textbox"], .msg-form__contenteditable').filter(visible=True).first
        if body_textarea.count() == 0:
            log("Could not find InMail body textarea.")
            return False
            
        body_textarea.click()
        body_textarea.fill(message)
        time.sleep(1.5)
        
        send_btn = page.locator('button[type="submit"], button:has-text("Send")').filter(visible=True).first
        if send_btn.count() > 0:
            send_btn.click()
            time.sleep(2)
            log("InMail sent successfully.")
            return True
        else:
            log("Could not find Send button for InMail.")
            return False
            
    except Exception as e:
        log(f"InMail exception: {e}")
        return False

if __name__ == "__main__":
    sys.exit(main())
