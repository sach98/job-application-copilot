import sys
import time
import requests

def wait_for_approval(webhook_url: str, company: str, role: str, job_id: str, stage: str = "review", timeout_sec: int = 21600) -> bool:
    """Pauses form filling, sends notification to n8n, and polls for user approval."""
    if not webhook_url:
        print(f"[*] No n8n webhook configured for approval. Auto-approving (dry-run/development mode).", file=sys.stderr)
        return True

    endpoint_notify = f"{webhook_url.rstrip('/')}/approval"
    endpoint_poll = f"{webhook_url.rstrip('/')}/approval/status"
    
    payload = {
        "job_id": job_id,
        "company": company,
        "role": role,
        "stage": stage,
        "status": "paused"
    }
    
    print(f"[*] Pausing for approval at stage '{stage}'. Sending n8n notification...", file=sys.stderr)
    try:
        requests.post(endpoint_notify, json=payload, timeout=10)
    except Exception as e:
        print(f"[-] Failed to notify n8n of approval pause: {e}", file=sys.stderr)
        # Continue to poll anyway, or fallback

    start_time = time.time()
    poll_interval = 10
    
    print(f"[*] Enters polling loop (timeout: {timeout_sec}s). Waiting for candidate's swipe/approval...", file=sys.stderr)
    while time.time() - start_time < timeout_sec:
        try:
            r = requests.get(endpoint_poll, params={"job_id": job_id}, timeout=15)
            if r.status_code == 200:
                res = r.json()
                status = res.get("status")
                if status == "approved":
                    print(f"[+] Approved by user. Resuming execution.", file=sys.stderr)
                    return True
                elif status == "rejected" or status == "skipped":
                    print(f"[-] Rejected/skipped by user. Aborting.", file=sys.stderr)
                    return False
                elif status == "edit":
                    # If edited, maybe the user updated something in Google doc. The caller should reload.
                    print(f"[+] User requested EDIT. Resuming to re-check drafts.", file=sys.stderr)
                    return True
            else:
                print(f"[-] Poll status check returned {r.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"[-] Polling error: {e}", file=sys.stderr)
            
        time.sleep(poll_interval)
        
    print(f"[-] Approval timed out after {timeout_sec} seconds.", file=sys.stderr)
    return False
