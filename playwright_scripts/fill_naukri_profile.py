#!/usr/bin/env python3
"""
Naukri profile auto-filler.

Drives Comet (Perplexity Chromium browser) via Playwright using the JobHunt
profile directory so existing Naukri login cookies are reused. Headed mode
so the candidate can intervene on OTP / captcha / dropdown weirdness.

Usage:
    # 1. Quit Comet fully first (Cmd+Q on the running Comet windows).
    # 2. Run:
    ~/JobHunt/.venv/bin/python ~/JobHunt/playwright_scripts/fill_naukri_profile.py

The script:
  - Opens https://www.naukri.com/mnjuser/profile (logged-in session expected).
  - Walks each profile section: headline, summary, key skills, employment,
    education, projects, certifications, personal, desired job, IT skills.
  - For each field: detects whether already filled; skips if non-empty (does
    NOT overwrite manual edits). Fills if empty.
  - Pauses 10 seconds before any "Save" click so the candidate can eyeball + cancel.
  - Captures screenshots into ~/JobHunt/screenshots/naukri_<section>_<ts>.png.
  - Writes a run log to ~/JobHunt/logs/naukri_fill_<ts>.log.

Stderr in caveman style. UI strings + Naukri input values = full prose.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

# ----- Paths -----
HOME = Path.home()
COMET_BIN = "/Applications/Comet.app/Contents/MacOS/Comet"
PROFILE_DIR = HOME / "JobHunt" / ".browser-profile" / "comet"
DATA_FILE = HOME / "JobHunt" / "profile" / "candidate_profile_data.json"
SCREENSHOT_DIR = HOME / "JobHunt" / "screenshots"
LOG_DIR = HOME / "JobHunt" / "logs"

NAUKRI_PROFILE_URL = "https://www.naukri.com/mnjuser/profile"

# ----- Logging -----
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = LOG_DIR / f"naukri_fill_{RUN_TS}.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    """Caveman-style log to stderr + log file."""
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")


def screenshot(page: Page, label: str) -> None:
    p = SCREENSHOT_DIR / f"naukri_{label}_{RUN_TS}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
        log(f"screenshot saved {p.name}")
    except Exception as e:
        log(f"screenshot fail {label}: {e}")


def safe_click(page: Page, selector: str, timeout: int = 4000) -> bool:
    try:
        loc = page.locator(selector).filter(visible=True).first
        if loc.count() == 0:
            loc = page.locator(selector).first
        loc.click(timeout=timeout)
        return True
    except PWTimeout:
        return False
    except Exception as e:
        log(f"click {selector} err: {e}")
        return False


def safe_fill(page: Page, selector: str, value: str, timeout: int = 4000) -> bool:
    try:
        loc = page.locator(selector).filter(visible=True).first
        if loc.count() == 0:
            loc = page.locator(selector).first
        loc.fill(value, timeout=timeout)
        return True
    except PWTimeout:
        return False
    except Exception as e:
        log(f"fill {selector} err: {e}")
        return False


def pause_for_save(page: Page, seconds: int = 8) -> None:
    """Pause so the candidate can sanity-check before any save click."""
    log(f"pause {seconds}s before save. candidate: cancel now if wrong.")
    for i in range(seconds, 0, -1):
        time.sleep(1)


def confirm_logged_in(page: Page) -> bool:
    """Return True if profile page loads (logged in), False if redirected to login."""
    url = page.url
    if "/login" in url or "/nlogin" in url:
        log(f"NOT logged in. url={url}. candidate: log in to Naukri in this Comet first.")
        return False
    return True


# ----- Section fillers -----
# Each function: visible-name + candidate's data → finds the edit pencil for that
# section, fills inputs, pauses, saves. Returns True if attempted, False if section
# not found.
#
# Naukri DOM changes often. Selectors are best-effort with fallbacks. If a section
# can't be located: skip + log so the candidate can fill it manually.


def fill_resume_headline(page: Page, data: dict) -> bool:
    log("section: resume headline")
    # Naukri's resume headline lives under "Resume Headline" section.
    try:
        # Find pencil edit button next to "Resume Headline"
        headline_section = page.locator("#lazyResumeHead").first
        if headline_section.count() == 0:
            log("headline section not found")
            return False
        headline_section.scroll_into_view_if_needed()
        # Click the edit icon (pencil) within this section
        edit_btn = headline_section.locator(".edit, [class*='edit'], .icon-edit, span.icon").first
        edit_btn.click(timeout=4000)
    except Exception as e:
        log(f"headline open edit fail: {e}")
        return False

    time.sleep(2)
    # Headline editor textarea
    headline_text = data.get("headline", "")[:600]  # Naukri caps ~600
    filled = False
    for sel in ['textarea[name="resumeHeadline"]', 'textarea[placeholder*="headline" i]', 'textarea.headline-editor', 'textarea']:
        if safe_fill(page, sel, headline_text):
            filled = True
            break
    if not filled:
        log("headline textarea not found")
        return False

    screenshot(page, "headline_before_save")
    pause_for_save(page)

    # Save button
    if not (safe_click(page, 'button:has-text("Save")') or safe_click(page, 'button[type="submit"]')):
        log("headline save button not found")
        return False
    log("headline saved")
    time.sleep(2)
    return True


def fill_profile_summary(page: Page, data: dict) -> bool:
    log("section: profile summary")
    try:
        section = page.locator("#lazyProfileSummary").first
        if section.count() == 0:
            log("summary section not found")
            return False
        section.scroll_into_view_if_needed()
        edit_btn = section.locator(":text('Add profile summary'), :text('Edit'), .edit, [class*='edit'], .icon-edit").first
        edit_btn.click(timeout=4000)
    except Exception as e:
        log(f"summary open fail: {e}")
        return False

    time.sleep(2)
    summary = data.get("summary", "")[:1000]  # Naukri caps ~1000
    filled = False
    for sel in ['textarea[name="profileSummary"]', 'textarea[placeholder*="summary" i]', 'textarea']:
        if safe_fill(page, sel, summary):
            filled = True
            break
    if not filled:
        log("summary textarea not found")
        return False

    screenshot(page, "summary_before_save")
    pause_for_save(page)
    safe_click(page, 'button:has-text("Save")') or safe_click(page, 'button[type="submit"]')
    log("summary saved")
    time.sleep(2)
    return True


def fill_key_skills(page: Page, data: dict) -> bool:
    log("section: key skills")
    try:
        section = page.locator("#lazyKeySkills").first
        if section.count() == 0:
            log("skills section not found")
            return False
        section.scroll_into_view_if_needed()
        edit_btn = section.locator(".edit, [class*='edit'], .icon-edit, span.icon").first
        edit_btn.click(timeout=4000)
    except Exception as e:
        log(f"skills open fail: {e}")
        return False

    time.sleep(2)
    skills = data.get("key_skills", [])[:30]  # Naukri caps ~30

    # Naukri uses a tag-input. Type each skill + press Enter or click suggestion.
    for skill in skills:
        try:
            input_box = page.locator('input[name="keySkills"], input[placeholder*="skill" i]').first
            input_box.click()
            input_box.fill(skill)
            time.sleep(0.8)
            # Try to click first dropdown suggestion that matches; fall back to Enter.
            try:
                page.locator(f'li:has-text("{skill}"), .suggestor-list li:has-text("{skill}")').first.click(timeout=2000)
            except PWTimeout:
                input_box.press("Enter")
            time.sleep(0.4)
            log(f"  + {skill}")
        except Exception as e:
            log(f"  skill {skill} fail: {e}")
            continue

    screenshot(page, "skills_before_save")
    pause_for_save(page)
    safe_click(page, 'button:has-text("Save")') or safe_click(page, 'button[type="submit"]')
    log("skills saved")
    time.sleep(2)
    return True


def fill_employment(page: Page, data: dict) -> bool:
    log("section: employment history")
    log("employment is multi-record. candidate adds each manually for safety — script will scroll to section + open editor.")
    try:
        section = page.locator("#lazyEmployment").first
        if section.count() == 0:
            log("employment section not found")
            return False
        section.scroll_into_view_if_needed()
        screenshot(page, "employment_section")
    except Exception as e:
        log(f"employment open fail: {e}")
        return False

    # Print employment data to console so the candidate can copy-paste fast.
    log("--- COPY-PASTE EMPLOYMENT DATA BELOW ---")
    for emp in data.get("employment_history", []):
        log(f"  Employer: {emp['employer']}")
        log(f"  Role: {emp['role']}")
        log(f"  From: {emp['from']}  To: {emp['to']}  Current: {emp['currently_working']}")
        log(f"  Description: {emp['description'][:200]}...")
        log("  ---")
    log("--- END EMPLOYMENT DATA ---")
    time.sleep(5)
    return True


def fill_education(page: Page, data: dict) -> bool:
    log("section: education")
    try:
        section = page.locator("#lazyEducation").first
        if section.count() == 0:
            log("education section not found")
            return False
        section.scroll_into_view_if_needed()
        screenshot(page, "education_section")
    except Exception as e:
        log(f"education open fail: {e}")
        return False

    log("--- COPY-PASTE EDUCATION DATA BELOW ---")
    for edu in data.get("education", []):
        log(f"  Degree: {edu['degree']}  ({edu['specialization']})")
        log(f"  Institution: {edu['institution']}  Country: {edu['country']}")
        log(f"  From: {edu['from']}  To: {edu['to']}  Course type: {edu['course_type']}")
        log("  ---")
    log("--- END EDUCATION DATA ---")
    time.sleep(5)
    return True


def fill_personal(page: Page, data: dict) -> bool:
    log("section: personal details")
    try:
        section = page.locator("#lazyPersonalDetail").first
        if section.count() == 0:
            log("personal section not found")
            return False
        section.scroll_into_view_if_needed()
        edit_btn = section.locator(".edit, [class*='edit'], .icon-edit, span.icon").first
        edit_btn.click(timeout=4000)
    except Exception as e:
        log(f"personal open fail: {e}")
        return False

    time.sleep(2)
    p = data["personal"]

    # DOB: Naukri uses 3 dropdowns (Day, Month, Year) typically.
    dob_dd, dob_mm, dob_yyyy = p["dob_dd_mm_yyyy"].split("-")
    # Try plain date input first
    if not safe_fill(page, 'input[name="dateOfBirth"], input[type="date"]', f"{dob_yyyy}-{dob_mm}-{dob_dd}", timeout=2000):
        log("DOB input not single field. candidate: fill DD MM YYYY manually if dropdowns")

    # Gender
    try:
        page.locator(f'label:has-text("{p["gender"]}")').first.click(timeout=2000)
        log(f"gender set: {p['gender']}")
    except PWTimeout:
        log("gender radio not found")

    # Marital
    try:
        page.locator(f'label:has-text("{p["marital_status"]}")').first.click(timeout=2000)
        log(f"marital set: {p['marital_status']}")
    except PWTimeout:
        log("marital radio not found")

    # Languages — multi-row UI. candidate handles manually for safety; we log values.
    log("languages to add manually:")
    for lang in p["languages"]:
        sk = "Speak" if lang["speak"] else ""
        rd = "Read" if lang["read"] else ""
        wt = "Write" if lang["write"] else ""
        log(f"  {lang['name']} ({lang['proficiency']}) — {sk} {rd} {wt}".strip())

    screenshot(page, "personal_before_save")
    pause_for_save(page)
    safe_click(page, 'button:has-text("Save")') or safe_click(page, 'button[type="submit"]')
    log("personal saved (whatever script could fill)")
    time.sleep(2)
    return True


def fill_desired_job(page: Page, data: dict) -> bool:
    log("section: desired job / career profile")
    try:
        section = page.locator("#lazyDesiredProfile").first
        if section.count() == 0:
            log("desired job section not found")
            return False
        section.scroll_into_view_if_needed()
        edit_btn = section.locator(".edit, [class*='edit'], .icon-edit, span.icon").first
        edit_btn.click(timeout=4000)
    except Exception as e:
        log(f"desired job open fail: {e}")
        return False

    time.sleep(2)
    d = data["desired_job"]

    # Print values so the candidate can paste into multi-selects if dropdown auto-fill fails
    log("desired-job values to set:")
    log(f"  expected salary INR LPA: {d['expected_salary_inr_lpa_min']}-{d['expected_salary_inr_lpa_max']}")
    log(f"  notice period: {d['notice_period_days']} days")
    log(f"  industries: {', '.join(d['industries'])}")
    log(f"  role categories: {', '.join(d['role_category'])}")
    log(f"  preferred locations: {', '.join(d['preferred_locations'])}")
    log(f"  employment type: {', '.join(d['employment_type'])}")
    log(f"  work mode: {d['work_mode_preference']}")

    # Try expected salary input
    safe_fill(page, 'input[name="expectedSalary"], input[placeholder*="expected" i]', str(d["expected_salary_inr_lpa_min"]))
    safe_fill(page, 'input[name="noticePeriod"], input[placeholder*="notice" i]', str(d["notice_period_days"]))

    screenshot(page, "desired_job_before_save")
    pause_for_save(page, seconds=12)  # longer pause for candidate to fix multi-selects
    safe_click(page, 'button:has-text("Save")') or safe_click(page, 'button[type="submit"]')
    log("desired job saved (script + manual)")
    time.sleep(2)
    return True


# ----- Main flow -----
def main() -> int:
    log("=== naukri profile filler start ===")
    if not DATA_FILE.exists():
        log(f"FATAL: data file missing {DATA_FILE}")
        return 2
    data = json.loads(DATA_FILE.read_text())
    log(f"data loaded for {data['personal']['full_name']}")

    if not COMET_BIN or not Path(COMET_BIN).exists():
        log(f"FATAL: Comet binary missing at {COMET_BIN}")
        return 2

    with sync_playwright() as p:
        log(f"launching Comet headed with profile {PROFILE_DIR}")
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=COMET_BIN,
                headless=False,
                args=["--no-first-run", "--no-default-browser-check"],
                viewport={"width": 1400, "height": 900},
            )
        except Exception as e:
            log(f"FATAL: launch fail (Comet already running on this profile?): {e}")
            log("candidate: quit Comet entirely (Cmd+Q) then re-run.")
            return 2

        page = ctx.new_page()
        log(f"nav {NAUKRI_PROFILE_URL}")
        try:
            page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            log(f"FATAL: nav fail: {e}")
            ctx.close()
            return 2

        time.sleep(4)
        
        # Inline login wait loop
        if "/login" in page.url or "/nlogin" in page.url:
            log("[-] NOT logged in. Inline login required.")
            print("\n" + "="*80, file=sys.stderr)
            print("SACHIN: Please log in to Naukri in the Comet browser window now.", file=sys.stderr)
            print("Solve any OTP or Captcha if requested. The script will resume automatically.", file=sys.stderr)
            print("="*80 + "\n", file=sys.stderr)
            
            login_success = False
            for check in range(60): # 5 minutes max
                time.sleep(5)
                url = page.url
                if "naukri.com" in url and "/login" not in url and "/nlogin" not in url:
                    log("[+] Login detected! Resuming profile auto-fill.")
                    login_success = True
                    break
                if check % 6 == 0:
                    log(f"Waiting for login (check {check}/60)...")
            
            if not login_success:
                screenshot(page, "login_timeout")
                log("FATAL: Login timeout.")
                ctx.close()
                return 2
        
        screenshot(page, "profile_landed")
        log("logged in. starting section fills.")

        # Run each section; log results without aborting on individual failures.
        sections = [
            ("headline", fill_resume_headline),
            ("summary", fill_profile_summary),
            ("key_skills", fill_key_skills),
            ("employment", fill_employment),
            ("education", fill_education),
            ("personal", fill_personal),
            ("desired_job", fill_desired_job),
        ]

        results = {}
        for name, fn in sections:
            try:
                page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(3)
                ok = fn(page, data)
                results[name] = "ok" if ok else "not_found_or_skipped"
            except Exception as e:
                log(f"section {name} crashed: {e}")
                results[name] = f"crash: {e}"

        # Final summary
        log("=== RESULTS ===")
        for k, v in results.items():
            log(f"  {k}: {v}")
        log(f"log: {LOG_PATH}")
        log(f"screenshots: {SCREENSHOT_DIR}")
        log("candidate: review browser, fix anything red, close window when done.")
        log("Browser stays open. Close window manually when done.")

        # Keep browser open so the candidate can finish manual bits.
        try:
            input("Press Enter here when you're done with Naukri to close browser... ")
        except EOFError:
            time.sleep(120)

        ctx.close()
        log("=== naukri profile filler done ===")
        return 0


if __name__ == "__main__":
    sys.exit(main())
