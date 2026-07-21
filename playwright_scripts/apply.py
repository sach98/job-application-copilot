#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
from pathlib import Path

# Nothing auto-submits. --submit alone only expresses intent; the run is downgraded to
# a dry-run unless a human has also exported AUTOSUBMIT_ENV_VAR=1 in that shell. Automated
# callers (n8n, cron) never set it, so an unattended path cannot click a real submit button.
AUTOSUBMIT_ENV_VAR = "JOBHUNT_ALLOW_AUTOSUBMIT"


def submit_allowed(requested: bool, env: dict | None = None) -> bool:
    """True only when --submit was passed AND a human opted in via the env var."""
    if not requested:
        return False
    env = os.environ if env is None else env
    return env.get(AUTOSUBMIT_ENV_VAR, "") == "1"


def main():
    parser = argparse.ArgumentParser(description="Autopilot Playwright Applier Dispatcher")
    parser.add_argument("--url", required=True, help="Job description URL")
    parser.add_argument("--job-id", required=True, help="n8n Job ID")
    parser.add_argument("--company", required=True, help="Company Name")
    parser.add_argument("--role", required=True, help="Role Name")
    parser.add_argument("--webhook", required=True, help="n8n Webhook Base URL")
    parser.add_argument("--submit", action="store_true",
                        help=f"Request a real submit. Honoured only when {AUTOSUBMIT_ENV_VAR}=1 "
                             "is exported by a human; otherwise the run stays a dry-run.")
    args = parser.parse_args()

    do_submit = submit_allowed(args.submit)
    if args.submit and not do_submit:
        print(f"[*] --submit ignored: {AUTOSUBMIT_ENV_VAR} is not set to 1. Running dry-run "
              f"(draft only). Export {AUTOSUBMIT_ENV_VAR}=1 by hand to allow a real submit.",
              file=sys.stderr)
    
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
    if do_submit:
        cmd.append("--submit")
        
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
