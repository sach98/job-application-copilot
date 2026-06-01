#!/usr/bin/env python3
import sys
import argparse
import subprocess
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Autopilot Playwright Applier Dispatcher")
    parser.add_argument("--url", required=True, help="Job description URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true", help="Submit application instead of dry-run")
    args = parser.parse_args()
    
    url = args.url.lower()
    script_dir = Path(__file__).parent
    
    # Dispatch mapping
    script_name = None
    if "myworkdayjobs.com" in url:
        script_name = "workday.py"
    elif "greenhouse.io" in url:
        script_name = "greenhouse.py"
    elif "lever.co" in url:
        script_name = "lever.py"
    elif "naukri.com" in url:
        script_name = "naukri_1click.py"
    elif "taleo.net" in url:
        script_name = "taleo.py"
    elif "smartrecruiters.com" in url:
        script_name = "smartrecruiters.py"
    elif "icims.com" in url:
        script_name = "icims.py"
    elif "linkedin.com" in url:
        script_name = "linkedin_easy_apply.py"
    else:
        print(f"[-] No specialized Playwright filler for URL: {args.url}", file=sys.stderr)
        print(f"[*] Falling back to manual apply. the candidate will receive dossier and apply by hand.", file=sys.stderr)
        sys.exit(2)  # Exit code 2 tells n8n to treat as manual fallback
        
    script_path = script_dir / script_name
    print(f"[*] Dispatching to specialized script: {script_name}", file=sys.stderr)
    
    cmd = [
        sys.executable,
        str(script_path),
        "--url", args.url,
        "--job-id", args.job_id,
        "--company", args.company,
        "--role", args.role,
        "--webhook", args.webhook
    ]
    if args.submit:
        cmd.append("--submit")
        
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
