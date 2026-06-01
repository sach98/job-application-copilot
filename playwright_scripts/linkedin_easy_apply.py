#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from lib.base import FormFillBot

class LinkedInEasyApplyBot(FormFillBot):
    def run(self) -> bool:
        self.log("LinkedIn Easy Apply automation is currently under construction (ToS safety fallback).")
        self.log(f"candidate: Please apply manually to this position at {self.jd_url}")
        self.screenshot("linkedin_manual_fallback")
        self.wait_for_approval(stage="manual_fallback")
        return False

def main():
    parser = argparse.ArgumentParser(description="LinkedIn Easy Apply bot stub")
    parser.add_argument("--url", required=True, help="LinkedIn job URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit instead of dry-run")
    args = parser.parse_args()
    
    bot = LinkedInEasyApplyBot(
        jd_url=args.url,
        job_id=args.job_id,
        company=args.company,
        role=args.role,
        n8n_webhook=args.webhook,
        draft_only=not args.submit
    )
    bot.run()
    sys.exit(2)  # Exit code 2 tells apply.py/n8n to treat as manual fallback

if __name__ == "__main__":
    main()
