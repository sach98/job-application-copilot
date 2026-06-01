#!/usr/bin/env python3
import os
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse

# Add parent dir to path so we can import lib
sys.path.append(str(Path(__file__).parent))
from lib.base import FormFillBot

class WorkdayBot(FormFillBot):
    def run(self) -> bool:
        self.log(f"Workday crawl start: {self.jd_url}")
        
        # Extract Workday tenant name from URL
        parsed = urlparse(self.jd_url)
        tenant = parsed.netloc.split(".")[0]
        
        page = self.launch_browser()
        
        try:
            page.goto(self.jd_url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            self.screenshot("workday_landed")
            
            # Click apply button
            apply_btn = page.locator("a[data-automation-id='adventureButton'], [data-automation-id='applyButton'], button:has-text('Apply')").first
            if apply_btn.count() > 0:
                apply_btn.click()
                page.wait_for_timeout(3000)
                self.screenshot("workday_apply_clicked")
            
            # Select "Apply Manually"
            manual_btn = page.locator("[data-automation-id='applyManually'], button:has-text('Apply Manually')").first
            if manual_btn.count() > 0:
                manual_btn.click()
                page.wait_for_timeout(3000)
                self.screenshot("workday_apply_manually")
            
            # Check if we are on Login screen
            if "login" in page.url or page.locator("input[type='email']").count() > 0:
                self.log("Workday login screen hit.")
                # Workdays usually require account. Let's see if we should create one.
                # Generate a unique email for this Workday tenant from a configured placeholder/account.
                base_email = os.environ.get("JOBHUNT_CANDIDATE_EMAIL", "candidate@example.com")
                local, _, domain = base_email.partition("@")
                workday_email = f"{local}+{tenant}@{domain}" if domain else base_email
                workday_password = os.environ.get("JOBHUNT_WORKDAY_PASSWORD", "change-me-before-use")
                
                # Check for "Create Account" button
                create_acc_btn = page.locator("[data-automation-id='createAccountLink'], a:has-text('Create Account')").first
                if create_acc_btn.count() > 0:
                    create_acc_btn.click()
                    page.wait_for_timeout(3000)
                    self.screenshot("workday_create_account_page")
                    
                    # Fill signup form
                    self.fill_input("input[type='email'], [data-automation-id='email']", workday_email)
                    self.fill_input("[data-automation-id='password']", workday_password)
                    self.fill_input("[data-automation-id='confirmPassword']", workday_password)
                    
                    # Check any agree checkboxes
                    try:
                        page.locator("input[type='checkbox']").first.check()
                    except Exception:
                        pass
                        
                    self.screenshot("workday_signup_details")
                    # Wait for candidate to complete captcha / submit signup
                    self.wait_for_approval(stage="signup_captcha_or_otp")
                    
                    # Try to click Create Account button if candidate didn't already
                    signup_submit = page.locator("button[type='submit'], [data-automation-id='createAccountButton']").first
                    if signup_submit.count() > 0:
                        signup_submit.click()
                        page.wait_for_timeout(4000)
                else:
                    self.log("No Create Account button found. Attempting to login...")
                    self.fill_input("input[type='email']", workday_email)
                    self.fill_input("input[type='password']", workday_password)
                    page.locator("button[type='submit'], [data-automation-id='signInButton']").first.click()
                    page.wait_for_timeout(4000)
            
            # Multi-page wizard loop
            # Workday typically goes: My Information -> My Experience -> Application Questions -> Voluntary Disclosures -> Self Identify -> Review
            self.log("Starting Workday Wizard loop...")
            
            for step_num in range(1, 10):
                self.screenshot(f"workday_step_{step_num}")
                page.wait_for_timeout(2000)
                
                # Check if we are on the final Review page
                if page.locator("[data-automation-id='reviewPage'], h2:has-text('Review')").count() > 0 or page.url.endswith("review"):
                    self.log("Reached final Review page.")
                    break
                    
                # Fill step details depending on header or automation-id
                step_title = ""
                header = page.locator("h1, h2, [data-automation-id='pageHeader']").first
                if header.count() > 0:
                    step_title = header.inner_text().lower()
                
                self.log(f"Current step title: {step_title}")
                personal = self.profile.get("personal", {})
                
                if "information" in step_title or "contact" in step_title:
                    # Fill contact info
                    self.fill_input("[data-automation-id='legalNameSection_firstName']", personal.get("first_name", ""))
                    self.fill_input("[data-automation-id='legalNameSection_lastName']", personal.get("last_name", ""))
                    self.fill_input("[data-automation-id='addressSection_addressLine1']", personal.get("address_line1", ""))
                    self.fill_input("[data-automation-id='addressSection_city']", personal.get("city", ""))
                    self.fill_input("[data-automation-id='addressSection_postalCode']", personal.get("postal_code", ""))
                    self.fill_input("[data-automation-id='phone-number']", personal.get("phone_local", ""))
                    
                elif "experience" in step_title or "history" in step_title:
                    # Upload Resume
                    resume_path = self.resume_to_upload()
                    if resume_path.exists():
                        try:
                            # Workday dropzone
                            file_input = page.locator("input[type='file']").first
                            file_input.set_input_files(str(resume_path))
                            page.wait_for_timeout(3000)
                        except Exception as e:
                            self.log(f"Workday resume upload fail: {e}")
                            
                    # Experience inputs can be complex; we rely on candidate's validation and auto-parsed resume.
                    
                elif "questions" in step_title:
                    # Free text fields -> essay_lookup
                    textareas = page.locator("textarea").all()
                    for ta in textareas:
                        try:
                            # Try to find question label
                            label = page.locator(f"label[for='{ta.get_attribute('id')}']").first
                            q_text = label.inner_text() if label.count() > 0 else "Custom Question"
                            
                            val = ta.input_value()
                            if not val.strip():
                                draft = self.lookup_essay(q_text)
                                if draft:
                                    ta.fill(draft)
                        except Exception as e:
                            self.log(f"Question fill error: {e}")
                
                # Click "Save and Continue" or "Next"
                next_btn = page.locator("[data-automation-id='bottom-navigation-next-button'], button:has-text('Save and Continue'), button:has-text('Next')").first
                if next_btn.count() > 0:
                    next_btn.click()
                    page.wait_for_timeout(4000)
                else:
                    self.log("No Next button found. candidate: click next page.")
                    self.wait_for_approval(stage="next_step_manual")
            
            # Review page: Pause for candidate's final review
            approved = self.wait_for_approval(stage="review")
            if not approved:
                self.log("Workday application aborted by user.")
                return False
                
            if self.draft_only:
                self.log("[dry-run] Draft only mode. Skipping final submit click.")
                self.screenshot("workday_dry_run_done")
                return True
            else:
                self.log("clicking submit")
                submit_btn = page.locator("[data-automation-id='bottom-navigation-submit-button'], button:has-text('Submit')").first
                if submit_btn.count() > 0:
                    submit_btn.click()
                    page.wait_for_timeout(5000)
                    self.screenshot("workday_submitted")
                    return True
                else:
                    self.log("Submit button not found.")
                    return False
                    
        except Exception as e:
            self.log(f"Workday filler crashed: {e}")
            self.screenshot("workday_crash")
            return False
        finally:
            self.close_browser()

def main():
    parser = argparse.ArgumentParser(description="Workday form fill bot")
    parser.add_argument("--url", required=True, help="Workday application URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit instead of dry-run")
    args = parser.parse_args()
    
    bot = WorkdayBot(
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
