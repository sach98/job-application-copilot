#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add parent dir to path so we can import lib
sys.path.append(str(Path(__file__).parent))
from lib.base import FormFillBot

class Naukri1ClickBot(FormFillBot):
    def run(self) -> bool:
        self.log(f"Naukri Direct Apply start: {self.jd_url}")
        page = self.launch_browser()
        
        try:
            page.goto(self.jd_url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            # Check if redirect happened or if login is requested
            if "naukri.com" not in page.url:
                self.log("Not on Naukri.com anymore. Exiting.")
                return False
                
            self.screenshot("naukri_landed")
            
            # Check for direct apply button
            # direct apply button selector is usually an id or text "Apply" or "Easy Apply"
            apply_btn = page.locator("#apply-button, button:has-text('Apply'), .apply-button").first
            if apply_btn.count() == 0:
                self.log("No Direct Apply button found (might be 'Apply on Company Site' or already applied).")
                self.screenshot("naukri_no_apply_button")
                return False
                
            btn_text = apply_btn.inner_text().strip()
            self.log(f"Apply button text: '{btn_text}'")
            if "company site" in btn_text.lower() or "external" in btn_text.lower():
                self.log("Button is for external application. Handled by other fillers.")
                return False
                
            if "applied" in btn_text.lower():
                self.log("Already applied. Success.")
                return True
                
            # Pause for candidate's approval
            approved = self.wait_for_approval(stage="review")
            if not approved:
                self.log("Naukri direct apply aborted by user.")
                return False
                
            if self.draft_only:
                self.log("[dry-run] Draft only mode. Skipping direct apply click.")
                self.screenshot("naukri_dry_run_done")
                return True
            else:
                self.log("clicking apply")
                apply_btn.click()
                page.wait_for_timeout(5000)
                
                # Check for questionnaire or forms that popped up
                self.screenshot("naukri_post_apply_click")
                
                # Sometimes there's a modal asking some multiple choice questions
                # Handle it manually if it appears
                if page.locator(".questionnaire-container, .modal").count() > 0:
                    self.log("Questionnaire modal detected. Pausing for candidate to fill.")
                    self.wait_for_approval(stage="questionnaire")
                    
                self.log("Naukri direct apply clicked successfully.")
                self.screenshot("naukri_submitted")
                return True
                
        except Exception as e:
            self.log(f"Naukri direct apply crashed: {e}")
            self.screenshot("naukri_crash")
            return False
        finally:
            self.close_browser()

def main():
    parser = argparse.ArgumentParser(description="Naukri 1-click apply bot")
    parser.add_argument("--url", required=True, help="Naukri job description URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit instead of dry-run")
    args = parser.parse_args()
    
    bot = Naukri1ClickBot(
        jd_url=args.url,
        job_id=args.job_id,
        company=args.company,
        role=args.role,
        n8n_webhook=args.webhook,
        draft_only=not args.submit
    )
    success = bot.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
