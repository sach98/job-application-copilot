#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add parent dir to path so we can import lib
sys.path.append(str(Path(__file__).parent))
from lib.base import FormFillBot

class LeverBot(FormFillBot):
    def run(self) -> bool:
        self.log(f"Lever crawl start: {self.jd_url}")
        
        # Lever JDs usually require clicking "Apply to Position" first to navigate to application form
        # Or URL is already /apply
        apply_url = self.jd_url if "/apply" in self.jd_url else f"{self.jd_url.rstrip('/')}/apply"
        page = self.launch_browser()
        
        try:
            page.goto(apply_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            # If not direct, try to click apply button on page
            if "/apply" not in page.url:
                try:
                    page.locator("a:has-text('Apply for this job'), a:has-text('Apply to Position')").first.click(timeout=4000)
                    page.wait_for_timeout(3000)
                except Exception:
                    pass
            
            self.screenshot("lever_landed")
            
            personal = self.profile.get("personal", {})
            # Upload Resume first as Lever sometimes auto-parses and fills details
            resume_path = self.resume_to_upload()
            if resume_path.exists():
                self.log(f"uploading resume from {resume_path}")
                try:
                    file_input = page.locator("input[type='file'][id='resume-upload-input']").first
                    file_input.set_input_files(str(resume_path))
                    # Wait for Lever's spinner to parse resume
                    page.wait_for_timeout(4000)
                except Exception as e:
                    self.log(f"Resume upload fail: {e}")
            
            # Fill fields (only if empty to avoid overwrite)
            def fill_if_empty(sel: str, val: str):
                try:
                    el = page.locator(sel).first
                    if el.count() > 0 and not el.input_value().strip():
                        el.fill(val)
                except Exception:
                    pass
            
            fill_if_empty("input[name='name']", personal.get("full_name", ""))
            fill_if_empty("input[name='email']", personal.get("email", ""))
            fill_if_empty("input[name='phone']", personal.get("phone", ""))
            fill_if_empty("input[name='org']", self.profile.get("current_employment", {}).get("last_employer", ""))
            fill_if_empty("input[name='urls[LinkedIn]']", personal.get("linkedin", ""))
            
            # Look for other text inputs (custom questions)
            custom_text_fields = page.locator("textarea, input[type='text']:not([name='name']):not([name='email']):not([name='phone']):not([name='org']):not([name*='urls'])").all()
            for field in custom_text_fields:
                try:
                    name_attr = field.get_attribute("name") or ""
                    # Skip common things
                    if not name_attr or any(x in name_attr.lower() for x in ["name", "email", "phone", "company", "linkedin", "resume"]):
                        continue
                        
                    # Find label text
                    label_text = field.evaluate("el => { const lbl = el.closest('.application-question').querySelector('.application-label'); return lbl ? lbl.innerText : ''; }")
                    if not label_text:
                        label_text = name_attr
                        
                    val = field.input_value()
                    if not val.strip():
                        draft = self.lookup_essay(label_text)
                        if draft:
                            field.fill(draft)
                            self.log(f"Filled custom field '{label_text[:40]}...' with tailored draft.")
                except Exception as e:
                    self.log(f"Custom field err: {e}")
            
            self.screenshot("lever_filled")
            
            # Pause for candidate's Approval
            approved = self.wait_for_approval(stage="review")
            if not approved:
                self.log("Lever application aborted by user.")
                return False
                
            if self.draft_only:
                self.log("[dry-run] Draft only mode. Skipping final submit click.")
                self.screenshot("lever_dry_run_done")
                return True
            else:
                self.log("clicking submit")
                # Lever submit button is usually #post-button or input[type=submit] or button[type=submit]
                submit_clicked = self.click_button("#post-button, button[type='submit'], input[type='submit']")
                page.wait_for_timeout(4000)
                self.screenshot("lever_submitted")
                return submit_clicked
                
        except Exception as e:
            self.log(f"Lever filler crashed: {e}")
            self.screenshot("lever_crash")
            return False
        finally:
            self.close_browser()

def main():
    parser = argparse.ArgumentParser(description="Lever form fill bot")
    parser.add_argument("--url", required=True, help="Lever application URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit instead of dry-run")
    args = parser.parse_args()
    
    bot = LeverBot(
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
