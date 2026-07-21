from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

# playwright is imported lazily in launch_browser() so this module's path constants and
# helpers stay importable without the browser dependency installed.
if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

from lib.profile import load_profile
from lib.screenshots import take_screenshot
from lib.essay_lookup import lookup_essay_answer
from lib.approval import wait_for_approval

from lib.paths import APPLICATIONS_DIR, BROWSER_PROFILE_DIR, PROFILE_DIR as _PROFILE_ROOT

COMET_BIN = "/Applications/Comet.app/Contents/MacOS/Comet"
PROFILE_DIR = BROWSER_PROFILE_DIR
MASTER_RESUME_PDF = _PROFILE_ROOT / "master_resume.pdf"

class FormFillBot:
    def __init__(self, jd_url: str, job_id: str, company: str, role: str, n8n_webhook: str = None, draft_only: bool = True):
        self.jd_url = jd_url
        self.job_id = job_id
        self.company = company
        self.role = role
        self.n8n_webhook = n8n_webhook
        self.draft_only = draft_only
        self.profile = load_profile()
        
        self.playwright = None
        self.context: BrowserContext = None
        self.page: Page = None
        self._in_captcha_check = False

    def log(self, message: str) -> None:
        """Log message in caveman style to stderr."""
        import datetime
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [{self.company} - {self.role}] {message}", file=sys.stderr, flush=True)

    def launch_browser(self) -> Page:
        self.log("launch comet browser")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                executable_path=COMET_BIN,
                headless=False,  # Headed so the candidate can see/intervene
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1400, "height": 900}
            )
        except Exception as e:
            self.log(f"FATAL: Comet launch fail: {e}")
            self.log("Ensure Comet is fully closed (Cmd+Q) and try again.")
            self.playwright.stop()
            raise e

        self.page = self.context.new_page()
        # Set default timeout to 15s for stability
        self.page.set_default_timeout(15000)

        # Wrap page.goto and page.wait_for_timeout to automatically trigger CAPTCHA checks
        original_goto = self.page.goto
        original_wait = self.page.wait_for_timeout

        def wrapped_goto(*args, **kwargs):
            self.check_and_solve_captcha()
            res = original_goto(*args, **kwargs)
            self.check_and_solve_captcha()
            return res

        def wrapped_wait(*args, **kwargs):
            self.check_and_solve_captcha()
            res = original_wait(*args, **kwargs)
            self.check_and_solve_captcha()
            return res

        self.page.goto = wrapped_goto
        self.page.wait_for_timeout = wrapped_wait

        return self.page

    def close_browser(self) -> None:
        self.log("close browser")
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def screenshot(self, label: str) -> Path:
        """Capture screenshot."""
        return take_screenshot(self.page, self.company, self.role, label)

    def _safe_job_id(self) -> str:
        return re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.job_id or "")).strip("_")

    def _local_essay_answer(self, question: str) -> str:
        """Match a portal question to a pre-generated per-role draft.

        tailor.py writes 10 keyed drafts to applications/<job_id>/essays.json.
        Common portal questions map onto those keys; using them is zero-cost,
        zero-latency, and already polished. Returns "" if no draft or no match.
        """
        safe_id = self._safe_job_id()
        if not safe_id:
            return ""
        path = APPLICATIONS_DIR / safe_id / "essays.json"
        if not path.exists():
            return ""
        try:
            drafts = (json.loads(path.read_text(encoding="utf-8")) or {}).get("essay_answer_drafts") or {}
        except (ValueError, OSError):
            return ""
        if not drafts:
            return ""

        q = question.lower()

        def has(*words: str) -> bool:
            return any(w in q for w in words)

        key = None
        if has("strength", "greatest asset"):
            key = "biggest_strength"
        elif has("weakness", "area of improvement", "development area", "improve about"):
            key = "biggest_weakness"
        elif has("challenge", "difficult", "obstacle", "accomplishment", "proud"):
            key = "biggest_challenge_solved"
        elif has("notice period", "when can you join", "availability to start"):
            key = "notice_period"
        elif has("relocat", "willing to move", "open to moving"):
            key = "open_to_relocation"
        elif has("salary", "compensation", "ctc", "expected pay", "expected package"):
            key = "salary_expectation"
        elif has("leaving", "why are you looking", "reason for change", "leave your current"):
            key = "why_leaving_current"
        elif has("five years", "5 years", "three years", "3 years", "see yourself", "career goal", "long term"):
            key = "where_3_years"
        elif has("why this role", "why are you interested in this", "why this position", "why do you want this job"):
            key = "why_this_role"
        elif has("why this company", "why do you want to work", "why us", "why join", "why our"):
            key = "why_this_company"

        return drafts.get(key, "") if key else ""

    def lookup_essay(self, question: str) -> str:
        """Resolve a custom portal answer: local draft first, then n8n Sonnet."""
        local = self._local_essay_answer(question)
        if local:
            self.log(f"essay answered from local draft: '{question[:40]}'")
            return local
        return lookup_essay_answer(self.n8n_webhook, question, self.company, self.role, self.jd_url, self.job_id)

    def resume_to_upload(self) -> Path:
        """Resume file to upload for this role.

        Prefer a per-role tailored PDF written by tailor.py
        (applications/<safe_job_id>/resume.pdf) once a PDF converter exists;
        until then no tailored PDF is produced and we fall back to the master
        resume PDF. The safe_id derivation must match tailor.py._safe_id.
        """
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.job_id or "")).strip("_")
        if safe_id:
            tailored = APPLICATIONS_DIR / safe_id / "resume.pdf"
            if tailored.exists():
                return tailored
        return MASTER_RESUME_PDF

    def check_and_solve_captcha(self) -> None:
        """Helper to invoke CAPTCHA checks on the active page.

        Re-entrancy guard: the CAPTCHA wait loop calls page.wait_for_timeout,
        which is wrapped to re-trigger this check. Without the guard that
        recurses until the stack overflows whenever a CAPTCHA is present.
        """
        if self._in_captcha_check or not self.page:
            return
        from lib.captcha import check_and_solve_captcha
        self._in_captcha_check = True
        try:
            check_and_solve_captcha(self.page, log_fn=self.log)
        finally:
            self._in_captcha_check = False

    def wait_for_approval(self, stage: str = "review") -> bool:
        """Block and wait for approval from n8n."""
        self.check_and_solve_captcha()
        return wait_for_approval(self.n8n_webhook, self.company, self.role, self.job_id, stage)

    def fill_input(self, selector: str, value: str, timeout: int = 5000) -> bool:
        self.check_and_solve_captcha()
        try:
            el = self.page.locator(selector).first
            el.scroll_into_view_if_needed(timeout=timeout)
            el.fill(value, timeout=timeout)
            return True
        except Exception as e:
            self.log(f"Fill fail on '{selector}': {e}")
            return False

    def click_button(self, selector: str, timeout: int = 5000) -> bool:
        self.check_and_solve_captcha()
        try:
            el = self.page.locator(selector).first
            el.scroll_into_view_if_needed(timeout=timeout)
            el.click(timeout=timeout)
            return True
        except Exception as e:
            self.log(f"Click fail on '{selector}': {e}")
            return False

    def run(self) -> bool:
        """To be implemented by subclasses. Returns True on success, False on fail."""
        raise NotImplementedError("Subclasses must implement run()")
