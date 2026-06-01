#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add parent dir to path so we can import lib
sys.path.append(str(Path(__file__).parent))
from lib.base import FormFillBot

class GreenhouseBot(FormFillBot):
    def run(self) -> bool:
        self.log(f"Greenhouse crawl start: {self.jd_url}")
        page = self.launch_browser()
        
        try:
            # Navigate to the job page
            page.goto(self.jd_url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            self.screenshot("greenhouse_landed")
            
            # Locate fields and fill standard data
            personal = self.profile.get("personal", {})
            self.fill_input("#first_name", personal.get("first_name", ""))
            self.fill_input("#last_name", personal.get("last_name", ""))
            self.fill_input("#email", personal.get("email", ""))
            self.fill_input("#phone", personal.get("phone", ""))
            
            # Optional fields
            self.fill_input("#location_autocomplete, input[placeholder*='location' i]", personal.get("current_city", ""))
            
            # Upload Resume
            # Greenhouse often has input[type=file] for resume
            resume_path = self.resume_to_upload()
            if resume_path.exists():
                self.log(f"uploading resume from {resume_path}")
                try:
                    file_input = page.locator("input[type='file'][id*='resume'], input[type='file'][name*='resume']").first
                    file_input.set_input_files(str(resume_path))
                    page.wait_for_timeout(2000)
                except Exception as e:
                    self.log(f"Resume upload fail: {e}")
            
            # Custom fields / essays
            # Look for other text fields/areas that might be custom questions
            custom_fields = page.locator("textarea, input[type='text']:not(#first_name):not(#last_name):not(#email):not(#phone):not(#location_autocomplete)").all()
            for field in custom_fields:
                try:
                    # Get associated label
                    field_id = field.get_attribute("id")
                    label_text = ""
                    if field_id:
                        label = page.locator(f"label[for='{field_id}']").first
                        if label.count() > 0:
                            label_text = label.inner_text()
                    if not label_text:
                        # Fallback to parent text
                        label_text = field.evaluate("el => el.parentElement.innerText").split("\n")[0]
                        
                    # Skip common formatting or empty labels
                    if not label_text.strip() or any(x in label_text.lower() for x in ["first name", "last name", "email", "phone", "resume", "cover letter"]):
                        continue
                        
                    # If empty, fetch draft
                    val = field.input_value()
                    if not val.strip():
                        draft = self.lookup_essay(label_text)
                        if draft:
                            field.fill(draft)
                            self.log(f"Filled custom field '{label_text[:40]}...' with tailored draft.")
                except Exception as e:
                    self.log(f"Custom field prefill err: {e}")
            
            self.screenshot("greenhouse_filled")
            
            # Pause for candidate's Approval
            approved = self.wait_for_approval(stage="review")
            if not approved:
                self.log("Greenhouse application aborted by user.")
                return False
                
            # Submit or Skip depending on draft_only mode
            if self.draft_only:
                self.log("[dry-run] Draft only mode. Skipping final submit click.")
                self.screenshot("greenhouse_dry_run_done")
                return True
            else:
                self.log("clicking submit")
                submit_clicked = self.click_button("#submit_app, button[type='submit'], input[type='submit']")
                page.wait_for_timeout(4000)
                self.screenshot("greenhouse_submitted")
                return submit_clicked
                
        except Exception as e:
            self.log(f"Greenhouse filler crashed: {e}")
            self.screenshot("greenhouse_crash")
            return False
        finally:
            self.close_browser()

def main():
    parser = argparse.ArgumentParser(description="Greenhouse form fill bot")
    parser.add_argument("--url", required=True, help="Greenhouse application URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit instead of dry-run")
    args = parser.parse_args()
    
    bot = GreenhouseBot(
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
